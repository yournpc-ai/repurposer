"""Film edit ops — the patch path's ONE application seat (设计见
docs/tasks/film-storyboard-orchestration.md §7.1/§7.2).

The model authors ops; the SYSTEM applies them. Laws:

- **ordered & atomic**: ops apply in list order to an in-memory copy; any
  rejection aborts the whole batch — the base version is never mutated and
  nothing partial survives (there is nothing to "roll back": the caller
  simply keeps the base it still holds);
- **base-version matching**: ``expected_base_digest`` is the READ-TIME
  reference the server minted when the model read the version it edited
  against (content + params + scene-id binding); apply-time the current
  base must still match it, a stale or foreign base rejects before the
  first op;
- **whole-batch change judgment**: after the LAST op, the batch must still
  carry a real content / param / timing-intent difference — cancelling or
  empty batches reject as ``unchanged`` (no version, no run, no charge);
- **content/identity separation**: ``scene_id`` is a handle, never content —
  digests exclude it (storyboard.py's ``_scene_content_dump`` law), so a
  reorder moves the whole-board digest but never a scene's content digest;
- **change_set is COMPUTED, never op-echo**: the presented diff comes from
  system comparison keyed by scene_id (base vs result), so "everything else
  stayed the same" is backed by construction, not by the model's say-so;
- **grounding is delegated**: this seat enforces structural integrity (id
  existence, permutation completeness, per-type re-validation, no-op
  rejection); semantic law (grounding, bands, chapter substance) plugs in
  via the ``validate`` callable — ``prepare_film_patch`` wires the real
  ``validate_storyboard`` there.

Two layers: the pure core (apply_film_edits & friends — no DB, no LLM) and
the DB-aware patch beat (``prepare_film_patch`` — the chat wiring's one
call: pages load, real validation, music gate, execution snapshot, dock
fingerprint, change_set presentation).
"""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    FilmChangeAdded,
    FilmChangeEdited,
    FilmChangeMoved,
    FilmChangeMusic,
    FilmChangeRemoved,
    FilmChangeRetimed,
    FilmChangeSet,
    FilmEditOp,
    FilmEditRemoveScene,
    FilmEditReorderScenes,
    FilmEditSetMusic,
    FilmEditSetVoiceover,
    FilmEditUpdateScene,
    FilmScene,
    FilmStoryboard,
)
from app.models.tables import Project
from app.tools.film.storyboard import (
    DockStoryboard,
    build_film_execution_snapshot,
    canonical_film_params,
    draft_reveal_onsets,
    execution_frames,
    film_snapshot_track,
    load_storyboard_pages,
    resolve_named_film_track,
    scene_content_digest,
    storyboard_content_digest,
    storyboard_fingerprint,
    valid_kept_cut,
    valid_kept_reveal_onsets,
    validate_storyboard,
)

_SCENE_ADAPTER = TypeAdapter(FilmScene)

# The prose slots ``update_scene.copy_slots`` may address, per scene type (ui
# scenes have no copy — their content is the view/focuses fields).
_COPY_SLOTS: dict[str, set[str]] = {
    "hero": {"word", "sub"},
    "words": {"lines"},
    "divider": {"label", "roll"},
    "reveal": {"lead", "word", "sub"},
    "plate": {"title"},
    "end": {"name", "tagline"},
    "ui": set(),
}


class FilmEditError(Exception):
    """A structured op rejection. The design seat (chat wiring) echoes this
    to the MODEL as the repair echo — it is not user-facing copy."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        scene_id: str | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.scene_id = scene_id
        self.field = field


def film_edit_repair_echo(exc: "FilmEditError") -> str:
    """The patch rejection's model-facing repair echo (both chat paths' ONE
    echo seat): the structured code + the reason + the ONE next move. The
    base version always stands untouched; the loop repairs and re-issues —
    a rejection is NEVER a redesign license and never a system failure."""
    if exc.code == "base_mismatch":
        return (
            "the film's current version moved since these edits were minted "
            "(base_mismatch) — re-read the current version (get_output_spec "
            "on the film output) and re-issue the edits with its base_ref. "
            "The current version stands untouched."
        )
    if exc.code == "unchanged":
        return (
            "the batch changes nothing (unchanged) — no content, parameter, "
            "or timing difference survives the whole batch, so no version was "
            "created (no run, no charge). If the user asked for a real "
            "change, re-issue the ops with the actual delta."
        )
    if exc.code == "validation_failed":
        return (
            "the edited board fails validation (validation_failed) — adjust "
            "the ops and re-issue the batch; the base_ref still holds:\n"
            f"{exc.detail}"
        )
    if exc.code == "keep_cut_incompatible":
        return (
            "keep_cut keeps the current cut exactly — the batch also changes "
            "the timeline (keep_cut_incompatible). Re-issue with "
            "retime=recut, or split the batch; the base version stands "
            "untouched."
        )
    if exc.code == "base_cut_unreadable":
        return (
            "the edit keeps the film's timeline, but the base version's "
            "established cut could not be recovered (base_cut_unreadable) — "
            "the run never silently re-cuts what the user already saw:\n"
            f"{exc.detail}\n"
            "Re-read the current version (get_output_spec on the film "
            "output) and re-issue; if the cut stays unreadable, allow a "
            "re-cut explicitly (set_music with retime=recut) or change the "
            "timeline. The current version stands untouched."
        )
    return (
        f"the edit batch was rejected ({exc.code}): {exc.detail}\n"
        "Fix the ops and re-issue — the base version stands untouched."
    )


@dataclass
class FilmEditResult:
    """The applied batch. Digest kinds are deliberately distinct in name —
    never compare across them:

    - ``base_identity_digest``: the base version's IDENTITY (content +
      canonical params + ordered scene ids — see
      ``film_version_identity_digest``), the 目标版本匹配 anchor;
    - ``result_content_digest``: the result board's CONTENT digest — the
      ADR-129 presented/executed chain's truth (params and ids never enter
      it).

    ``board``/``params`` are fresh objects — the caller's base stays
    byte-identical."""

    board: FilmStoryboard
    params: dict
    change_set: FilmChangeSet
    base_identity_digest: str
    result_content_digest: str


def film_version_identity_digest(
    board: FilmStoryboard, params: dict, *, version: int | None = None
) -> str:
    """An edit base's full identity: content digest + canonical params +
    the ordered scene-id binding + the VERSION number. Two versions with
    identical CONTENT but different params, id assignments, or version
    numbers are different edit bases — a patch minted against one must
    never land on the other. The version binds the reference to the
    world's actual movement: a recut-only new version (same content, same
    params — retime is an execution instruction, never a param) still
    invalidates earlier references, because the timeline state the read
    showed has moved.

    This is also the READ-TIME reference: the read seat mints it when the
    model reads a version, and the model echoes it back verbatim with the
    edit batch (it cannot fabricate one — a forged or stale reference
    simply never matches the current version at apply time). The CONTENT
    reuse digest (``storyboard_content_digest``) never takes the version —
    the two digest kinds stay incomparable by construction."""
    ensured = ensure_scene_ids(board)
    payload = json.dumps(
        {
            "content": storyboard_content_digest(ensured),
            "params": canonical_film_params(params),
            "scene_ids": [s.scene_id for s in ensured.scenes],
            "version": version,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_scene_ids(board: FilmStoryboard) -> FilmStoryboard:
    """Return a copy of ``board`` with every scene carrying a stable id.

    Existing ids are kept (and must be unique — duplicates are a corrupt
    board, not a patch target); missing ones derive positionally (``s1..``,
    skipping taken ids), which is the legacy-board one-time upgrade path.
    """
    dump = board.model_dump(mode="json")
    scenes = dump["scenes"]
    existing = [s.get("scene_id") for s in scenes if s.get("scene_id")]
    if len(set(existing)) != len(existing):
        raise FilmEditError(
            "duplicate_scene_id",
            "the board carries duplicate scene ids — not a valid edit base",
        )
    taken = set(existing)
    for index, scene in enumerate(scenes):
        if scene.get("scene_id"):
            continue
        n = index + 1
        while f"s{n}" in taken:
            n += 1
        scene["scene_id"] = f"s{n}"
        taken.add(f"s{n}")
    return FilmStoryboard.model_validate(dump)


def _find(work: FilmStoryboard, scene_id: str) -> int:
    for index, scene in enumerate(work.scenes):
        if scene.scene_id == scene_id:
            return index
    raise FilmEditError(
        "unknown_scene",
        f"no scene with id '{scene_id}' in the base version",
        scene_id=scene_id,
    )


def _apply_update_scene(work: FilmStoryboard, op: FilmEditUpdateScene) -> None:
    index = _find(work, op.scene_id)
    dump = work.scenes[index].model_dump(mode="json")
    scene_type = dump["type"]

    if op.view is not None:
        if scene_type != "ui":
            raise FilmEditError(
                "field_not_applicable",
                f"'view' only edits ui scenes — {op.scene_id} is a {scene_type}",
                scene_id=op.scene_id,
                field="view",
            )
        dump["page"] = op.view.page
        dump["shot"] = op.view.shot
        if op.view.frame is not None:
            dump["frame"] = op.view.frame
    if op.focuses is not None:
        if scene_type != "ui":
            raise FilmEditError(
                "field_not_applicable",
                f"'focuses' only edits ui scenes — {op.scene_id} is a {scene_type}",
                scene_id=op.scene_id,
                field="focuses",
            )
        dump["focuses"] = [f.model_dump(mode="json") for f in op.focuses]
    if op.seconds is not None:
        if op.seconds <= 0:
            raise FilmEditError(
                "invalid_field",
                f"seconds must be positive (got {op.seconds})",
                scene_id=op.scene_id,
                field="seconds",
            )
        dump["seconds"] = op.seconds
    if "narration" in op.model_fields_set:
        # Presence semantics: an explicit null CLEARS the line; an absent
        # key keeps it. The value alone could never say which.
        dump["narration"] = op.narration
    if op.copy_slots:
        allowed = _COPY_SLOTS[scene_type]
        for key, value in op.copy_slots.items():
            if key not in allowed:
                raise FilmEditError(
                    "unknown_copy_field",
                    f"{scene_type} scenes have no copy slot '{key}' "
                    f"(slots: {sorted(allowed) or 'none'})",
                    scene_id=op.scene_id,
                    field=key,
                )
            dump[key] = value

    try:
        work.scenes[index] = _SCENE_ADAPTER.validate_python(dump)
    except ValidationError as exc:
        raise FilmEditError(
            "invalid_field",
            "; ".join(
                f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            ),
            scene_id=op.scene_id,
        ) from exc


def _apply_op(
    work: FilmStoryboard, work_params: dict, op: FilmEditOp
) -> str | None:
    """One op onto the working copy. Returns the music retime directive when
    the op carried one (the change_set's music entry reports it)."""
    if isinstance(op, FilmEditUpdateScene):
        _apply_update_scene(work, op)
        return None
    if isinstance(op, FilmEditReorderScenes):
        current = [s.scene_id for s in work.scenes]
        # Exact permutation = same set + no duplicates (ids are unique by
        # ensure_scene_ids, so set equality is the full multiset check).
        if len(set(op.order)) != len(op.order) or set(op.order) != set(current):
            raise FilmEditError(
                "order_mismatch",
                "order must be an exact permutation of the current scene ids "
                f"(current: {current})",
            )
        by_id = {s.scene_id: s for s in work.scenes}
        work.scenes = [by_id[scene_id] for scene_id in op.order]
        return None
    if isinstance(op, FilmEditRemoveScene):
        if len(work.scenes) <= 1:
            raise FilmEditError(
                "last_scene", "a film cannot lose its only scene"
            )
        index = _find(work, op.scene_id)
        del work.scenes[index]
        return None
    if isinstance(op, FilmEditSetMusic):
        mood = op.mood.strip()
        if not mood:
            raise FilmEditError("invalid_field", "mood must be non-empty", field="mood")
        current = canonical_film_params(work_params).get("music_mood")
        # Selection change and timing intent are SEPARATE facts: re-cutting
        # to the CURRENT track's grid (same mood + recut) is a real edit —
        # only "same mood + keep the cuts" changes nothing.
        if current == mood and op.retime == "keep_cut":
            raise FilmEditError(
                "noop", f"the film already uses the '{mood}' mood with these cuts"
            )
        work_params["music_mood"] = mood
        return op.retime
    if isinstance(op, FilmEditSetVoiceover):
        if canonical_film_params(work_params)["voiceover"] is False:
            raise FilmEditError("noop", "the film already has no voiceover")
        work_params["voiceover"] = False
        return None
    raise FilmEditError("unknown_op", f"unsupported op {getattr(op, 'op', None)!r}")


def compute_change_set(
    before: FilmStoryboard,
    after: FilmStoryboard,
    params_before: dict,
    params_after: dict,
    *,
    music_retime: str | None = None,
) -> FilmChangeSet:
    """The system-computed diff (never the op list echoed back). Scene facts
    key by ``scene_id``; seconds deltas land in ``retimed`` only; param
    deltas compare canonical forms (a default spelled once never reads as a
    change)."""
    base_by_id = {s.scene_id: s for s in before.scenes}
    result_by_id = {s.scene_id: s for s in after.scenes}
    base_index = {s.scene_id: i for i, s in enumerate(before.scenes)}
    result_index = {s.scene_id: i for i, s in enumerate(after.scenes)}

    moved: list[FilmChangeMoved] = []
    edited: list[FilmChangeEdited] = []
    retimed: list[FilmChangeRetimed] = []
    for scene_id, scene in result_by_id.items():
        base = base_by_id.get(scene_id)
        if base is None:
            continue  # added below
        if base_index[scene_id] != result_index[scene_id]:
            moved.append(
                FilmChangeMoved(
                    scene_id=scene_id,
                    from_index=base_index[scene_id],
                    to_index=result_index[scene_id],
                )
            )
        if scene_content_digest(base) != scene_content_digest(scene):
            base_dump = base.model_dump(mode="json")
            result_dump = scene.model_dump(mode="json")
            fields = sorted(
                k
                for k in set(base_dump) | set(result_dump)
                if k not in {"scene_id", "seconds"}
                and base_dump.get(k) != result_dump.get(k)
            )
            if fields:
                edited.append(FilmChangeEdited(scene_id=scene_id, fields=fields))
            if base.seconds != scene.seconds:
                retimed.append(
                    FilmChangeRetimed(
                        scene_id=scene_id,
                        seconds_before=base.seconds,
                        seconds_after=scene.seconds,
                    )
                )

    return FilmChangeSet(
        moved=moved,
        edited=edited,
        added=[
            FilmChangeAdded(scene_id=s.scene_id or "", scene_type=s.type)
            for s in after.scenes
            if s.scene_id not in base_by_id
        ],
        removed=[
            FilmChangeRemoved(scene_id=s.scene_id or "", scene_type=s.type)
            for s in before.scenes
            if s.scene_id not in result_by_id
        ],
        retimed=retimed,
        music=(
            FilmChangeMusic(
                mood_before=canonical_film_params(params_before).get("music_mood"),
                mood_after=canonical_film_params(params_after).get("music_mood") or "",
                retime=music_retime or "keep_cut",
            )
            # The entry carries a SELECTION change or a surviving timing
            # directive — a batch whose ops cancel out (mood back to start,
            # keep_cut) reports nothing here and rejects as unchanged at the
            # batch gate below.
            if canonical_film_params(params_before).get("music_mood")
            != canonical_film_params(params_after).get("music_mood")
            or music_retime == "recut"
            else None
        ),
        voiceover=(
            canonical_film_params(params_after)["voiceover"]
            if canonical_film_params(params_before)["voiceover"]
            != canonical_film_params(params_after)["voiceover"]
            else None
        ),
    )


def apply_film_edits(
    board: FilmStoryboard,
    params: dict,
    ops: list[FilmEditOp],
    *,
    expected_base_digest: str | None = None,
    base_version: int | None = None,
    validate: Callable[[FilmStoryboard, dict], list] | None = None,
) -> FilmEditResult:
    """Apply ``ops`` to ``board``/``params`` — ordered, atomic, non-mutating.

    ``expected_base_digest`` (目标版本匹配): the READ-TIME reference — minted
    by the server when the model read the version it based this batch on
    (``film_version_identity_digest`` at read/presentation time) and echoed
    back verbatim with the ops. **Never recompute it from the just-resolved
    base at apply time — that self-comparison always matches and protects
    nothing.** The check proves the base resolved NOW is still the version
    the edits were formed against; a stale or foreign reference rejects as
    ``base_mismatch`` BEFORE any op applies. (``None`` = the caller asserts
    base freshness out-of-band — the chat wiring never does this.)
    ``base_version`` = the resolved base's version number — it binds the
    identity to the world's movement (a recut-only new version shares its
    content but never its references).

    ``validate`` (optional) is the semantic-law seat: it receives the
    PATCHED board + params and returns violations (the design beat wires
    ``validate_storyboard`` there); any violation rejects the batch as
    ``validation_failed``. On ANY FilmEditError the caller's base version
    stands untouched — the failure carries nothing partial.
    """
    if not ops:
        raise FilmEditError("empty_ops", "an edit batch holds at least one op")
    base_identity = film_version_identity_digest(board, params, version=base_version)
    if expected_base_digest is not None and expected_base_digest != base_identity:
        raise FilmEditError(
            "base_mismatch",
            "the edit was minted against a different base version — "
            "re-read the current version and re-issue the edit",
        )
    before = ensure_scene_ids(board)
    work = FilmStoryboard.model_validate(before.model_dump(mode="json"))
    work_params = dict(params)

    music_retime: str | None = None
    for op in ops:
        retime = _apply_op(work, work_params, op)
        if retime is not None:
            music_retime = retime

    # Whole-batch change judgment (never per-op): ops may cancel out — only
    # a real content, param, or surviving timing-intent difference earns a
    # new version. An unchanged batch creates no version, no run, no charge.
    if (
        storyboard_content_digest(work) == storyboard_content_digest(before)
        and canonical_film_params(work_params) == canonical_film_params(params)
        and music_retime != "recut"
    ):
        raise FilmEditError(
            "unchanged",
            "the batch changes nothing — no content, parameter, or timing "
            "difference survives the whole batch",
        )

    if validate is not None:
        violations = validate(work, work_params)
        if violations:
            raise FilmEditError(
                "validation_failed",
                "; ".join(str(v) for v in violations),
            )

    return FilmEditResult(
        board=work,
        params=work_params,
        change_set=compute_change_set(
            before, work, params, work_params, music_retime=music_retime
        ),
        base_identity_digest=base_identity,
        result_content_digest=storyboard_content_digest(work),
    )


# ---------------------------------------------------------------------------
# The DB-aware patch beat (the chat wiring's one call). The pure core above
# decides WHETHER the batch stands; this seat prepares everything a version
# publish needs around it — pages for the real validator, the music gate,
# the execution snapshot, the dock fingerprint, the presented change lines.
# ---------------------------------------------------------------------------


@dataclass
class FilmPatchPrepared:
    """The publish unit the chat wiring stamps: the new version's
    DockStoryboard-shaped handoff (``film.presentation`` = the change lines
    — a patch NEVER re-prints the whole table), the patched params, the
    system-computed change_set, the apply result, and ``next_base_ref`` —
    THIS version's identity digest, minted at presentation time (the next
    edit's read-time reference)."""

    film: DockStoryboard
    params: dict
    change_set: FilmChangeSet
    result: FilmEditResult
    next_base_ref: str
    # The version's frozen cut (冻结时间轴 = 版本状态): the base version's
    # own established per-scene frames — carried by a keep_cut swap AND by
    # any timeline-preserving batch inheriting an established cut; None when
    # the batch re-establishes the timeline (a structural change or a
    # surviving recut) or the base never had an established cut. The design
    # seat stamps it into the version envelope (``film_kept_frames``) and
    # the run consumes it fail-closed whenever present.
    kept_frames: list[int] | None = None
    # The frozen cut's other half (冻结场内切点同一继承律): the reveal
    # words' landing beats — the base spec's ``lead_frames`` / a kept
    # envelope's inherited onsets / a draft freeze's presented-timeline
    # onsets (computed by the ONE onset seat on the base grid); None when
    # the frozen cut is absent or the board carries no reveal scene. The
    # envelope field is ``film_kept_reveal_onsets``; the run consumes it
    # fail-closed whenever the kept cut covers a reveal scene.
    kept_reveal_onsets: list[int | None] | None = None


def change_set_presentation(change_set: FilmChangeSet, board: FilmStoryboard) -> str:
    """The patch's fact block (system-computed, never the op echo): ONLY the
    change lines + the new totals — the model's presentation message renders
    these verbatim-ish and never re-prints the whole table (呈现只带变化行).
    Scene numbers are 1-based to match the fact sheet's ``scene N``
    numbering; the id in brackets is the edit path's handle."""
    by_id = {s.scene_id: s for s in board.scenes}

    def label(scene_id: str) -> str:
        scene = by_id.get(scene_id)
        return (
            f"scene [{scene_id}] ({scene.type})"
            if scene is not None
            else f"scene [{scene_id}]"
        )

    lines: list[str] = []
    for moved in change_set.moved:
        lines.append(
            f"- {label(moved.scene_id)}: moved {moved.from_index + 1} → {moved.to_index + 1}"
        )
    for edited in change_set.edited:
        lines.append(
            f"- {label(edited.scene_id)}: edited — fields: {', '.join(edited.fields)}"
        )
    for retimed in change_set.retimed:
        lines.append(
            f"- {label(retimed.scene_id)}: {retimed.seconds_before:g}s → "
            f"{retimed.seconds_after:g}s"
        )
    for removed in change_set.removed:
        lines.append(f"- scene [{removed.scene_id}] ({removed.scene_type}): removed")
    for added in change_set.added:
        lines.append(f"- scene [{added.scene_id}] ({added.scene_type}): added")
    if change_set.music is not None:
        music = change_set.music
        retime = (
            "re-cut to the track's beat grid"
            if music.retime == "recut"
            else "existing cuts kept"
        )
        if (music.mood_before or "") == music.mood_after:
            lines.append(f'- music: "{music.mood_after}" (same track) — {retime}')
        else:
            before = f'"{music.mood_before}"' if music.mood_before else "none"
            lines.append(f"- music: {before} → \"{music.mood_after}\" — {retime}")
    if change_set.voiceover is not None:
        lines.append(
            f"- voiceover: now {'off' if change_set.voiceover is False else 'on'}"
        )
    for warning in change_set.warnings:
        lines.append(f"- heads-up: {warning}")
    total = round(sum(s.seconds for s in board.scenes), 1)
    lines.append(f"New totals: {len(board.scenes)} scenes · {total:g}s.")
    return "\n".join(lines)


def film_music_retime_of(pending: Any) -> str | None:
    """The confirmed version's surviving music retime instruction
    (``set_music``'s retime is an EXECUTION instruction — it never enters
    params/the fingerprint; it travels through the version's change_set).
    The Start stamp projects this onto run.context (``film_music_retime``)
    as the instruction's PROVENANCE — and as the half-written-envelope
    tripwire: a keep_cut instruction whose frozen frames went missing fails
    the run closed. The frame seat itself keys on ``film_kept_frames``
    presence (the frozen cut is version state — a timeline-preserving edit
    inherits it without naming set_music again). None = no surviving
    instruction. Pure + read-tolerant: a malformed change_set reads as
    None."""
    change_set = getattr(pending, "film_change_set", None) if pending is not None else None
    if not isinstance(change_set, dict):
        return None
    music = change_set.get("music")
    if not isinstance(music, dict):
        return None
    retime = music.get("retime")
    return retime if retime in ("keep_cut", "recut") else None


async def prepare_film_patch(
    db: AsyncSession,
    project: Project,
    *,
    base: Any,
    ops: list[FilmEditOp],
    base_ref: str,
    instruction: str | None,
) -> FilmPatchPrepared:
    """The patch beat (chat wiring 唯一调用座): apply ``ops`` onto ``base``
    (the resolved revision base namespace) and prepare the publish unit.

    - the base board must parse (a corrupt stored version rejects honestly
      as ``base_unreadable``, never a silent re-design);
    - the project's captured pages are the validator's grounding universe —
      gone, the edit cannot stand (``pages_missing``);
    - semantic law = the REAL ``validate_storyboard`` over the patched
      board + params (narration_required follows the patched voiceover
      flag) — a rejection surfaces as ``validation_failed`` with the
      violations verbatim (the model repairs in-loop, never a director
      re-design, never a 500);
    - the ``set_music`` op's own 校验 (曲目可解/节拍网格可得): a CHANGED mood
      must resolve by name (never the silent fallback chain) and carry an
      analyzable grid — otherwise ``music_unavailable`` / ``music_no_rhythm``;
      untouched music re-resolves best-effort (the design beat's snapshot
      law, one seat);
    - the execution snapshot REBUILDS from the current pages + the version's
      track, so the run's drift gate compares this version's own world;
    - the fingerprint keys on the PATCHED canonical params + the plan's
      birth narrative — the approval dock recomputes the same key and
      REUSES this patched board (never a redraft).

    Raises FilmEditError on any rejection (the caller maps it to the repair
    echo); the base version stands untouched on every failure path."""
    try:
        board = FilmStoryboard.model_validate(base.film_storyboard)
    except (TypeError, ValueError) as exc:
        raise FilmEditError(
            "base_unreadable",
            "the stored base version no longer parses — re-read the current "
            "version (get_output_spec on the film output) before editing",
        ) from exc
    params = dict(base.film_storyboard_params or {})
    pages = await load_storyboard_pages(db, project)
    if not pages:
        raise FilmEditError(
            "pages_missing",
            "the project's captured pages are gone — the edit's grounding "
            "universe is missing; re-capture the site, then re-issue the edit",
        )

    def _validate(b: FilmStoryboard, p: dict) -> list:
        return validate_storyboard(
            b, pages, narration_required=canonical_film_params(p)["voiceover"]
        )

    result = apply_film_edits(
        board,
        params,
        ops,
        expected_base_digest=base_ref,
        base_version=getattr(base, "film_storyboard_version", None),
        validate=_validate,
    )

    # 冻结时间轴 = 版本状态 (ADR-137): the established cut inherits across
    # versions by ACTUAL CHANGE — never by whether THIS batch happens to
    # name set_music. Invalidation follows the timeline's dependencies:
    # a batch that changes the timeline (scenes moved/removed/added/retimed)
    # or carries a surviving recut instruction re-establishes the cut fresh
    # at run time (allocate + snap — old frames are never blindly reused);
    # every other batch INHERITS the base version's established cut:
    # - base executed → its run's spec frames (the flex-baked truth, read by
    #   the revision-base seat as ``film_cut_frames``, state "spec");
    # - base a frozen draft → its kept frames (state "kept") — the freeze
    #   survives the chain (a keep_cut swap followed by a voiceover-off
    #   edit keeps the original cut);
    # - base a plain draft (state "draft": never executed, never frozen) →
    #   no established cut exists to inherit; an EXPLICIT keep_cut freezes
    #   its PRESENTED timeline (the base board snapped to the base bed's
    #   grid — the cut the fact sheet showed; never a fresh allocation,
    #   never the new bed's grid), while an uninstructed batch carries no
    #   kept frames and the run's allocate+snap reproduces the same plan
    #   (narration flex stays alive);
    # - base executed but its cut unreadable (state "unreadable": spec
    #   missing/corrupt) → a timeline-keeping batch CANNOT stand on a
    #   recomputed guess — structured refusal (``base_cut_unreadable``):
    #   re-read the version, or explicitly allow a recut. Never a silent
    #   recompute, never a full re-design, never a 500.
    # keep_cut's compatibility law stands on top: a surviving keep_cut
    # instruction with a timeline-changing batch rejects
    # (``keep_cut_incompatible`` — re-issue with recut, or split the batch).
    kept_frames: list[int] | None = None
    kept_reveal_onsets: list[int | None] | None = None
    music_change = result.change_set.music
    keep_cut = music_change is not None and music_change.retime == "keep_cut"
    recut = music_change is not None and music_change.retime == "recut"
    timeline_changed = bool(
        result.change_set.moved
        or result.change_set.removed
        or result.change_set.added
        or result.change_set.retimed
    )
    if keep_cut and timeline_changed:
        raise FilmEditError(
            "keep_cut_incompatible",
            "keep_cut keeps the current cut exactly — the batch also "
            "changes the timeline (scenes moved/removed/added/retimed). "
            "Re-issue with retime=recut, or split the batch",
        )
    if not timeline_changed and not recut:
        base_cut = getattr(base, "film_cut_frames", None)
        base_onsets = getattr(base, "film_cut_reveal_onsets", None)
        if base_cut is None:
            cut_state = getattr(base, "film_cut_state", None)
            if cut_state == "unreadable":
                raise FilmEditError(
                    "base_cut_unreadable",
                    "the base version was executed, but its render spec is "
                    "missing or corrupt — the cut it actually rendered with "
                    "is unrecoverable, and an edit that keeps the timeline "
                    "never stands on a recomputed guess",
                )
            if keep_cut:
                base_execution = getattr(base, "film_storyboard_execution", None)
                base_music = (
                    (base_execution.get("music") or {})
                    if isinstance(base_execution, dict)
                    else {}
                )
                base_beats = base_music.get("beats")
                base_cut = execution_frames(board, base_beats)
                # The draft freeze's in-scene cut points ride the SAME
                # presented timeline (the ONE onset seat on the base grid —
                # the spec build never re-derives them differently).
                base_onsets = draft_reveal_onsets(board, base_cut, base_music)
        if base_cut is not None:
            if not valid_kept_cut(result.board, base_cut):
                raise FilmEditError(
                    "base_cut_unreadable",
                    "the base version's recovered cut no longer fits the "
                    "patched board (scene floors/count moved) — re-read the "
                    "current version before editing",
                )
            kept_frames = list(base_cut)
            # 冻结场内切点同一继承律: the reveal words' landing beats freeze
            # alongside the scene lengths — a frozen cut over a board WITH
            # reveal scenes must carry its onsets (a half-written frozen
            # state refuses, never a silent re-snap onto the new grid).
            if base_onsets is not None:
                if not valid_kept_reveal_onsets(result.board, base_onsets, kept_frames):
                    raise FilmEditError(
                        "base_cut_unreadable",
                        "the base version's frozen reveal timing no longer "
                        "fits the patched board — re-read the current "
                        "version before editing",
                    )
                kept_reveal_onsets = list(base_onsets)
            elif any(s.type == "reveal" for s in result.board.scenes):
                raise FilmEditError(
                    "base_cut_unreadable",
                    "the base version's frozen cut is missing its reveal "
                    "timing (the word's landing beats) — re-read the "
                    "current version before editing; an edit that keeps "
                    "the timeline never stands on a recomputed guess",
                )

    canonical = canonical_film_params(result.params)
    mood = canonical.get("music_mood")
    if result.change_set.music is not None and mood:
        # The op table's 校验 for a CHANGED bed: the named ref itself must
        # resolve (a mistyped mood surfaces, never silently falls back) and
        # the grid must exist (the run's own gates, moved to edit time).
        track, beats = await resolve_named_film_track(db, project, mood)
        if track is None:
            raise FilmEditError(
                "music_unavailable",
                f"no music track resolves the '{mood}' mood — name one of the "
                "library's moods (or drop the music change from the batch)",
                field="mood",
            )
        if beats is None:
            raise FilmEditError(
                "music_no_rhythm",
                f"the '{mood}' track carries no analyzable beat grid — pick "
                "another mood; the film never fakes a beat",
                field="mood",
            )
    else:
        track = await film_snapshot_track(db, project, result.params)

    return FilmPatchPrepared(
        film=DockStoryboard(
            presentation=change_set_presentation(result.change_set, result.board),
            storyboard=result.board.model_dump(mode="json"),
            fingerprint=storyboard_fingerprint(
                [{"tool": "launch_film", "params": result.params}], instruction
            ),
            reused=False,
            execution=build_film_execution_snapshot(pages=pages, track=track),
        ),
        params=result.params,
        change_set=result.change_set,
        result=result,
        next_base_ref=film_version_identity_digest(
            result.board,
            result.params,
            version=(getattr(base, "film_storyboard_version", None) or 0) + 1,
        ),
        kept_frames=kept_frames,
        kept_reveal_onsets=kept_reveal_onsets,
    )
