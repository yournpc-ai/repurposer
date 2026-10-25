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
fingerprint, system change summary and the shared full-version fact sheet).
"""

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import re
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
    FilmEditSetSubtitles,
    FilmEditSetVoiceover,
    FilmEditUpdateElement,
    FilmEditUpdateScene,
    FilmScene,
    FilmStoryboard,
)
from app.models.tables import Project
from app.tools.film.storyboard import (
    FILM_FPS,
    FILM_MUSIC_OFF,
    FILM_WORDS_STYLE_FIELDS,
    FILM_WORDS_TIMING_FIELDS,
    TEXT_CAPS,
    DockStoryboard,
    StoryboardMedia,
    _LIST_CAPS,
    _screen_strings,
    _text_source_note,
    _text_style_clause,
    _track_beats,
    _track_bpm,
    build_film_execution_snapshot,
    build_text_manifest,
    canonical_film_params,
    draft_reveal_onsets,
    element_timing_clause,
    execution_frames,
    film_seconds_to_frames,
    film_snapshot_track,
    film_text_line_cap,
    film_text_source_from_params,
    load_storyboard_media,
    load_storyboard_pages,
    resolve_named_film_track,
    scene_content_digest,
    storyboard_content_digest,
    storyboard_fingerprint,
    storyboard_presentation,
    valid_kept_cut,
    valid_kept_reveal_onsets,
    validate_storyboard,
    words_timing_clause,
)

_SCENE_ADAPTER = TypeAdapter(FilmScene)
_ELEMENT_TIMING_FIELDS = frozenset(
    {
        "enter_start",
        "enter_interval",
        "enter_duration",
        "motion_start",
        "motion_end",
        "exit_duration",
        "motion_scale",
    }
)

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
    # A composite's copy lives on ELEMENTS — addressed by element_id via
    # update_element, never by the scene-level copy_slots (ADR-140).
    "composite": set(),
}


def film_edit_copy_constraints() -> str:
    """Project the edit path's real copy bounds onto its wire schema.

    The slot whitelist belongs to this module; character/list caps and the
    text-film display-unit rule belong to the storyboard validator. Read them
    at spec time so the model-facing declaration cannot drift into a second
    set of numbers.
    """
    scene_rules: list[str] = []
    for scene_type in ("words", "hero", "divider", "reveal", "plate", "end"):
        slot_rules: list[str] = []
        for slot in sorted(_COPY_SLOTS[scene_type]):
            cap = TEXT_CAPS.get((scene_type, slot))
            if cap is None:
                continue
            list_cap = _LIST_CAPS.get(f"{scene_type}.{slot}")
            if list_cap is not None:
                slot_rules.append(
                    f"{slot}: 1..{list_cap} entries, each ≤{cap} characters"
                )
            else:
                slot_rules.append(f"{slot}: ≤{cap} characters")
        if slot_rules:
            scene_rules.append(f"{scene_type}[" + "; ".join(slot_rules) + "]")
    tier_caps = ", ".join(
        f"{label}={film_text_line_cap(size, seat='words')} units"
        for label, size in (
            ("default/medium", None),
            ("small", "small"),
            ("large", "large"),
        )
    )
    return (
        "Validator-derived update_scene.copy_slots bounds: "
        + "; ".join(scene_rules)
        + ". Character caps exclude '*' emphasis marks. For TEXT films, each "
        "words line must ALSO fit its size tier's display-unit cap ("
        + tier_caps
        + "); a CJK character counts 2 units and any other character counts "
        "1. These are hard bounds, never instructions to trim the copy."
    )


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
    if exc.code == "voiceover_needs_narration":
        return (
            "voiceover was switched on, but the version's board carries NO "
            "narration lines (voiceover_needs_narration) — a content gap, "
            "never a synthesis or voice problem: author the narration lines "
            "first (update_scene with narration on the speech-carrying "
            "scenes, in the same batch or an earlier one), then re-issue "
            "set_voiceover. The base version stands untouched."
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
    board: FilmStoryboard,
    params: dict,
    *,
    version: int | None = None,
    cut: tuple[str | None, list[int] | None, list[int | None] | None] | None = None,
) -> str:
    """An edit base's full identity: content digest + canonical params +
    the ordered scene-id binding + the VERSION number + the FROZEN TIMELINE
    state (冻结时间轴 = 版本状态 — cut_state/frames/reveal-onsets; a plain
    draft's derived plan timeline is NOT version state and binds nothing).
    Two versions with identical CONTENT but different params, id
    assignments, version numbers, or frozen cuts are different edit bases —
    a patch minted against one must never land on the other. The version
    binds the reference to the world's actual movement: a recut-only new
    version (same content, same params — retime is an execution
    instruction, never a param) still invalidates earlier references,
    because the timeline state the read showed has moved. The frozen cut
    binds it further: branch lineages can mint SAME-numbered versions with
    identical content (a pinned branch re-applying the base's own patch)
    whose TIMELINE state differs — the cut triple is what still tells them
    apart.

    This is also the READ-TIME reference: the read seat mints it when the
    model reads a version, and the model echoes it back verbatim with the
    edit batch (it cannot fabricate one — a forged or stale reference
    simply never matches the current version at apply time). The CONTENT
    reuse digest (``storyboard_content_digest``) never takes the version —
    the two digest kinds stay incomparable by construction."""
    ensured = ensure_scene_ids(board)
    cut_state, cut_frames, cut_onsets = cut if cut is not None else (None, None, None)
    payload = json.dumps(
        {
            "content": storyboard_content_digest(ensured),
            "params": canonical_film_params(params),
            "scene_ids": [s.scene_id for s in ensured.scenes],
            # update_element's addressing handles ride the identity too
            # (the scene_ids law one level down): the CONTENT digest's
            # element-id exclusion is content law; an IDENTITY that cannot
            # tell two element numberings apart would let a reference
            # minted against one silently edit the other's same-named
            # handle. Order-sensitive, scene order aligned.
            "element_ids": [
                [el.element_id for el in s.elements]
                for s in ensured.scenes
                if s.type == "composite"
            ],
            "version": version,
            "cut": (
                [cut_state, cut_frames, cut_onsets]
                if cut_state is not None and cut_state != "draft"
                else None
            ),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def film_base_cut(
    base,
) -> tuple[str | None, list[int] | None, list[int | None] | None]:
    """The version's frozen-timeline triple for the identity digest (ONE
    extraction seat — the read mint, the turn fast-reject and the apply
    recheck all derive it the same way, so a ref minted by one always
    matches the recompute at another). Accepts either the resolved-base
    object (attribute surface — PendingPlan properties / the revision-base
    namespace) or the design-state envelope dict (``film_design_state``'s
    PendingPlan field kwargs, where the cut derives from the kept frames —
    the read surface's same law)."""
    if isinstance(base, dict):
        kept = base.get("film_kept_frames")
        if isinstance(kept, list):
            onsets = base.get("film_kept_reveal_onsets")
            # The namespace seat's same isinstance law — a corrupt envelope
            # field never rides the digest as-is.
            return ("kept", kept, onsets if isinstance(onsets, list) else None)
        return ("draft", None, None)
    return (
        getattr(base, "film_cut_state", None),
        getattr(base, "film_cut_frames", None),
        getattr(base, "film_cut_reveal_onsets", None),
    )


def committed_film_state_identity(film_state: dict) -> str | None:
    """The publish guard's committed-world half (base 引用协议 step 4): mint
    the identity reference of the COMMITTED pending's film envelope through
    the same seats as the read-time reference, so the guard compares FULL
    identity (content + canonical params + ordered scene ids + version +
    frozen cut) — never a version-number or content-digest handshake
    (branch lineages can mint same-numbered versions; same-content drafts
    can differ in params or frozen timeline).

    Returns None when the committed state cannot PROVE an identity — a
    missing/unparsable board, a params field that is not a dict, a version
    that is not an int. An unprovable world is never identity-equal (fail
    closed: the patch discards and the model re-reads); a legacy row whose
    board/params/version ARE present still proves itself — the content
    digest recomputes from the board itself and legacy scene ids derive
    positionally, so a missing stored digest field is no obstacle."""
    board = film_state.get("film_storyboard")
    params = film_state.get("film_storyboard_params")
    version = film_state.get("film_storyboard_version")
    if not isinstance(board, dict) or not isinstance(params, dict):
        return None
    if not isinstance(version, int) or isinstance(version, bool):
        return None
    try:
        return film_version_identity_digest(
            FilmStoryboard.model_validate(board),
            params,
            version=version,
            cut=film_base_cut(film_state),
        )
    except (TypeError, ValueError):
        return None


def ensure_scene_ids(board: FilmStoryboard) -> FilmStoryboard:
    """Return a copy of ``board`` with every scene carrying a stable id.

    Existing ids are kept (and must be unique — duplicates are a corrupt
    board, not a patch target); missing ones derive positionally (``s1..``,
    skipping taken ids), which is the legacy-board one-time upgrade path.

    Composite elements ride the SAME law one level down (ADR-140): every
    element carries a stable ``element_id`` (``e1..``, scene-scoped) — the
    update_element op's addressing handle, never content (the digest's
    element-id exclusion makes assigning ids digest-neutral)."""
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
    for scene in scenes:
        if scene.get("type") != "composite":
            continue
        elements = scene.get("elements") or []
        el_existing = [e.get("element_id") for e in elements if e.get("element_id")]
        if len(set(el_existing)) != len(el_existing):
            raise FilmEditError(
                "duplicate_element_id",
                f"scene {scene.get('scene_id') or '?'} carries duplicate "
                "element ids — not a valid edit base",
                scene_id=scene.get("scene_id"),
            )
        el_taken = set(el_existing)
        for el_index, element in enumerate(elements):
            if element.get("element_id"):
                continue
            n = el_index + 1
            while f"e{n}" in el_taken:
                n += 1
            element["element_id"] = f"e{n}"
            el_taken.add(f"e{n}")
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


_ACCENT_SPAN = re.compile(r"\*([^*]+)\*")


def _preserve_accents(old_lines: list[str], new_lines: list[str]) -> list[str]:
    """Emphasis survives a copy edit when it still corresponds EXACTLY: an
    accent whose phrase appears verbatim in the new copy is re-marked —
    editing the words is not a licence to silently strip the presentation
    the user already saw. New lines carrying ANY mark of their own are
    taken as authored (the editor owns the emphasis). At most one chip is
    auto-preserved per line; whatever cannot correspond drops, and the
    change set says so (``_dropped_emphasis_notes``) — never a silent loss
    dressed as "只改文案"."""
    if any("*" in line for line in new_lines):
        return new_lines
    phrases = [m.group(1) for line in old_lines for m in _ACCENT_SPAN.finditer(line)]
    out = list(new_lines)
    for phrase in phrases:
        for i, line in enumerate(out):
            pos = line.find(phrase)
            if pos >= 0 and "*" not in line:
                out[i] = f"{line[:pos]}*{phrase}*{line[pos + len(phrase):]}"
                break
    return out


def _dropped_emphasis_notes(old_lines: list[str], new_lines: list[str]) -> list[str]:
    """The honest report of an emphasis that did NOT survive: the phrase
    still exists in the new copy but is no longer marked. A phrase that
    vanished WITH the words needs no note — the copy change itself is the
    report."""
    new_text = "\n".join(new_lines)
    new_plain = new_text.replace("*", "")
    notes: list[str] = []
    seen: set[str] = set()
    for line in old_lines:
        for m in _ACCENT_SPAN.finditer(line):
            phrase = m.group(1)
            if phrase in seen:
                continue
            seen.add(phrase)
            if f"*{phrase}*" not in new_text and phrase in new_plain:
                notes.append(
                    f"emphasis «{phrase}» is no longer marked in the new copy"
                )
    return notes


def _apply_update_scene(work: FilmStoryboard, op: FilmEditUpdateScene) -> None:
    index = _find(work, op.scene_id)
    dump = work.scenes[index].model_dump(mode="json")
    scene_type = dump["type"]
    previous_enter = dump.get("enter") or "lines"

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
    for key, value in (("motion", op.motion), ("enter", op.enter), ("dark", op.dark)):
        if value is None:
            continue
        # dark is the scene's background polarity — the words plane AND the
        # composition scene carry it (ADR-140); motion/enter stay words-only.
        allowed_types = {"words", "composite"} if key == "dark" else {"words"}
        if scene_type not in allowed_types:
            raise FilmEditError(
                "field_not_applicable",
                f"'{key}' only edits {'words and composite' if key == 'dark' else 'words'} scenes — {op.scene_id} is a "
                f"{scene_type} (motion/enter/dark are the text plane's own "
                "presentation knobs)",
                scene_id=op.scene_id,
                field=key,
            )
        dump[key] = value
    # Timing fields are presence-sensitive: absent keeps the current value,
    # explicit null restores the default, explicit zero stays zero.
    for key in sorted(FILM_WORDS_TIMING_FIELDS):
        if key not in op.model_fields_set:
            continue
        if scene_type != "words":
            raise FilmEditError(
                "field_not_applicable",
                f"'{key}' only edits words scenes — {op.scene_id} is a "
                f"{scene_type} (the precise entrance/motion window belongs "
                "to the words plane)",
                scene_id=op.scene_id,
                field=key,
            )
        dump[key] = getattr(op, key)
    next_enter = dump.get("enter") or "lines"
    if next_enter != previous_enter:
        stale_timing = [
            key
            for key in ("enter_start", "enter_interval", "enter_duration", "enter_hold_until")
            if key not in op.model_fields_set and dump.get(key) is not None
        ]
        if stale_timing:
            raise FilmEditError(
                "timing_unit_change",
                "switching between word and line entrances changes the timing "
                f"unit — explicitly set or clear {', '.join(stale_timing)} in "
                "the same edit; never reinterpret the old token cadence "
                "silently as a line cadence",
                scene_id=op.scene_id,
                field=stale_timing[0],
            )
    # Style fields ride the same presence law (absent = keep, explicit null
    # = restore the default, which IS null for all of them).
    for key in sorted(FILM_WORDS_STYLE_FIELDS):
        if key not in op.model_fields_set:
            continue
        if scene_type != "words":
            raise FilmEditError(
                "field_not_applicable",
                f"'{key}' only edits words scenes — {op.scene_id} is a "
                f"{scene_type} (alignment/size tier/emphasis style are the "
                "text plane's own presentation knobs)",
                scene_id=op.scene_id,
                field=key,
            )
        dump[key] = getattr(op, key)
    if any(
        key in op.model_fields_set and getattr(op, key) is not None
        for key in ("enter_start", "enter_interval", "enter_duration", "enter_hold_until")
    ) and dump.get("enter") not in ("words", "lines", None):
        raise FilmEditError(
            "field_not_applicable",
            "enter timing needs enter='words' or enter='lines' — set the "
            "entrance rhythm in the same edit (or clear the timing fields)",
            scene_id=op.scene_id,
            field="enter_start",
        )
    if any(
        key in op.model_fields_set and getattr(op, key) is not None
        for key in ("motion_start", "motion_end", "motion_scale")
    ) and dump.get("motion") not in ("push", "pull"):
        raise FilmEditError(
            "field_not_applicable",
            "motion timing/scale needs motion='push' or 'pull' — set the "
            "move in the same edit (or clear the timing fields)",
            scene_id=op.scene_id,
            field="motion_start",
        )
    if op.copy_slots:
        allowed = _COPY_SLOTS[scene_type]
        old_lines = list(dump.get("lines") or []) if scene_type == "words" else None
        for key, value in op.copy_slots.items():
            if key not in allowed:
                raise FilmEditError(
                    "unknown_copy_field",
                    f"{scene_type} scenes have no copy slot '{key}' "
                    f"(slots: {sorted(allowed) or 'none'})",
                    scene_id=op.scene_id,
                    field=key,
                )
            if scene_type == "words" and key == "lines" and not isinstance(value, list):
                raise FilmEditError(
                    "invalid_field",
                    "words copy_slots.lines must be a JSON array of strings "
                    '(for example {"lines":["first line","second line"]}), '
                    "not one string and not a nested 'words' object",
                    scene_id=op.scene_id,
                    field=key,
                )
            dump[key] = value
        if old_lines is not None and "lines" in op.copy_slots:
            dump["lines"] = _preserve_accents(old_lines, dump["lines"])
            # Re-anchor the edited scene's pre-wrap corpus: the authored
            # lines ARE its new source (one paragraph per entry, accents
            # stripped) — the pinned text keeps deriving from sources,
            # never from a wrap.
            dump["copy_text"] = "\n".join(
                stripped
                for line in dump["lines"]
                if (stripped := line.replace("*", "").strip())
            ) or None

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


def _apply_update_element(work: FilmStoryboard, op: FilmEditUpdateElement) -> None:
    """One field-level edit of ONE element inside a composite scene
    (ADR-140). Presence law (the timing fields' own): absent = keep;
    explicit null = restore the field's DEFAULT; explicit zero stays zero.
    ``lines`` / ``source_start`` / ``source_end`` have no default — an
    explicit null on them is an error. The asset IDENTITY is never editable
    (a different video is a different composition)."""
    index = _find(work, op.scene_id)
    scene = work.scenes[index]
    if scene.type != "composite":
        raise FilmEditError(
            "field_not_applicable",
            f"update_element addresses composite scenes — {op.scene_id} is a "
            f"{scene.type}",
            scene_id=op.scene_id,
        )
    dump = scene.model_dump(mode="json")
    elements = dump.get("elements") or []
    target = next(
        (i for i, e in enumerate(elements) if e.get("element_id") == op.element_id),
        None,
    )
    if target is None:
        raise FilmEditError(
            "unknown_element",
            f"no element '{op.element_id}' in scene {op.scene_id} — address "
            "elements by their stable id (the fact sheet/read carries them)",
            scene_id=op.scene_id,
        )
    el = elements[target]
    kind = el["kind"]
    previous_enter = el.get("enter") or "lines"

    # Kind applicability: which op fields may address which element kind.
    text_only = {
        "lines", "tone", "enter", "motion",
        "enter_start", "enter_interval", "enter_duration",
        "motion_start", "motion_end",
        "exit_duration", "motion_scale", "align", "size", "accent_style",
        "enter_style",
    }
    media_only = {"fit"}
    video_only = {"source_start", "source_end", "duration", "keep_audio"}
    shared_all = {"at", "rect", "z"}
    windowed = {"until"}  # image + text (a video element's leave is at+play)
    editable = (
        shared_all
        | (text_only if kind == "text" else set())
        | (media_only if kind in ("video", "image") else set())
        | (video_only if kind == "video" else set())
        | (windowed if kind in ("image", "text") else set())
    )

    # Restore-default values for an explicit null (the schema's own
    # defaults; ``lines``/source bounds have none — handled below).
    defaults: dict[str, Any] = {
        "at": 0.0,
        "until": None,
        "rect": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "z": 0,
        "fit": "cover",
        "tone": "light",
        "keep_audio": False,
        "enter": None,
        "motion": None,
        "duration": None,
        "enter_start": None,
        "enter_interval": None,
        "enter_duration": None,
        "motion_start": None,
        "motion_end": None,
        "exit_duration": None,
        "motion_scale": None,
        "align": None,
        "size": None,
        "accent_style": None,
        "enter_style": None,
    }
    no_default = {"lines", "source_start", "source_end"}

    for key in sorted(op.model_fields_set - {"op", "scene_id", "element_id"}):
        if key not in editable:
            raise FilmEditError(
                "field_not_applicable",
                f"'{key}' does not edit a {kind} element "
                f"(scene {op.scene_id}, element {op.element_id})",
                scene_id=op.scene_id,
                field=key,
            )
        value = getattr(op, key)
        if value is None:
            if key in no_default:
                raise FilmEditError(
                    "invalid_field",
                    f"'{key}' has no default to restore — pass the new value "
                    "or leave the field out",
                    scene_id=op.scene_id,
                    field=key,
                )
            el[key] = defaults[key]
            continue
        el[key] = value.model_dump(mode="json") if key == "rect" else value

    next_enter = el.get("enter") or "lines"
    if kind == "text" and next_enter != previous_enter:
        stale_timing = [
            key
            for key in ("enter_start", "enter_interval", "enter_duration")
            if key not in op.model_fields_set and el.get(key) is not None
        ]
        if stale_timing:
            raise FilmEditError(
                "timing_unit_change",
                "switching between word and line entrances changes the timing "
                f"unit — explicitly set or clear {', '.join(stale_timing)} in "
                "the same edit; never reinterpret the old token cadence "
                "silently as a line cadence",
                scene_id=op.scene_id,
                field=stale_timing[0],
            )

    # Enter/motion gates (the words plane's own law, element-scoped): a
    # timed entrance uses the selected word/line unit; a timed move needs push/pull.
    if any(
        key in op.model_fields_set and getattr(op, key) is not None
        for key in ("enter_start", "enter_interval", "enter_duration")
    ) and el.get("enter") not in ("words", "lines", None):
        raise FilmEditError(
            "field_not_applicable",
            "enter timing needs enter='words' or enter='lines' — set the "
            "entrance rhythm in the same edit (or clear the timing fields)",
            scene_id=op.scene_id,
            field="enter_start",
        )
    if any(
        key in op.model_fields_set and getattr(op, key) is not None
        for key in ("motion_start", "motion_end", "motion_scale")
    ) and el.get("motion") not in ("push", "pull"):
        raise FilmEditError(
            "field_not_applicable",
            "motion timing/scale needs motion='push' or 'pull' — set the "
            "move in the same edit (or clear the timing fields)",
            scene_id=op.scene_id,
            field="motion_start",
        )

    if "lines" in op.model_fields_set and kind == "text":
        old_lines = list(
            (work.scenes[index].model_dump(mode="json")["elements"])[target].get("lines")
            or []
        )
        el["lines"] = _preserve_accents(old_lines, el["lines"])
        # Re-anchor the element's pre-wrap corpus (the words scene's
        # copy-edit law, element-scoped): the authored lines ARE the new
        # source.
        el["copy_text"] = "\n".join(
            stripped
            for line in el["lines"]
            if (stripped := line.replace("*", "").strip())
        ) or None

    elements[target] = el
    dump["elements"] = elements
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
    if isinstance(op, FilmEditSetSubtitles):
        work.scenes[_find(work, op.scene_id)].subtitle_track = op.track
        return None
    if isinstance(op, FilmEditUpdateElement):
        _apply_update_element(work, op)
        return None
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
        current = canonical_film_params(work_params)["voiceover"]
        if op.enabled is False:
            if current is False:
                raise FilmEditError("noop", "the film already has no voiceover")
            work_params["voiceover"] = False
            return None
        # 重开配音 (音频三态): re-open synthesis of the version's OWN
        # narration lines — zero redesign, never a director call. The
        # board must CARRY lines to synthesize: the existence law fires on
        # the POST-batch board in apply_film_edits (order-independent — a
        # batch may author the lines and re-enable in one pass).
        if current is not False:
            raise FilmEditError("noop", "the film already has voiceover on")
        work_params["voiceover"] = True
        return None
    raise FilmEditError("unknown_op", f"unsupported op {getattr(op, 'op', None)!r}")


def _composite_changed_fields(
    base_dump: dict, result_dump: dict
) -> tuple[list[str], list[str]]:
    """A composite scene's change as PER-ELEMENT fields (ADR-140):
    ``elements.<eid>.<field>`` keyed by the stable element id — never one
    opaque ``elements`` blob (the confirmation beat must be able to say
    WHICH element moved). Nested ``copy_text`` is lines' derived shadow
    (the scene-level law's twin: it moves the digest, never gets its own
    change line); a lines edit reports dropped emphasis per element."""
    fields: list[str] = []
    notes: list[str] = []
    for k in set(base_dump) | set(result_dump):
        if k in {"scene_id", "seconds", "elements"}:
            continue
        if base_dump.get(k) != result_dump.get(k):
            fields.append(k)
    base_els = {e.get("element_id"): e for e in base_dump.get("elements") or []}
    result_els = {e.get("element_id"): e for e in result_dump.get("elements") or []}
    for eid, el in result_els.items():
        bel = base_els.get(eid)
        if bel is None:
            fields.append(f"elements.{eid} (new)")
            continue
        for k in set(bel) | set(el):
            if k in {"element_id", "copy_text"}:
                continue
            if bel.get(k) != el.get(k):
                fields.append(f"elements.{eid}.{k}")
        if bel.get("lines") != el.get("lines") and el.get("kind") == "text":
            notes.extend(
                f"[{eid}] {note}"
                for note in _dropped_emphasis_notes(
                    bel.get("lines") or [], el.get("lines") or []
                )
            )
    for eid in base_els:
        if eid not in result_els:
            fields.append(f"elements.{eid} (removed)")
    return sorted(fields), notes


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
            if base.type == "composite" and scene.type == "composite":
                # ADR-140: the diff reads per element, keyed by element_id.
                fields, notes = _composite_changed_fields(base_dump, result_dump)
            else:
                fields = sorted(
                    k
                    for k in set(base_dump) | set(result_dump)
                    # copy_text is lines' derived shadow (re-anchored by every
                    # copy edit) — it moves the DIGEST (the corpus anchor is
                    # content) but never gets its own change line.
                    if k not in {"scene_id", "seconds", "copy_text"}
                    and base_dump.get(k) != result_dump.get(k)
                )
                notes = (
                    _dropped_emphasis_notes(base.lines, scene.lines)
                    if "lines" in fields
                    and base.type == "words"
                    and scene.type == "words"
                    else []
                )
            if fields:
                edited.append(FilmChangeEdited(scene_id=scene_id, fields=fields, notes=notes))
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


def _board_copy_text(board: FilmStoryboard) -> str:
    """The board's on-screen words as a corpus text (the text film's 文字来源
    projection). A words scene contributes its PRE-WRAP ``copy_text`` (the
    assembly-time anchor) — the display lines are a layout result, so
    re-deriving the corpus from them would mistake a visual wrap for a
    paragraph break (折行污染). Legacy boards without the anchor fall back
    to the display strings. Accent marks stripped (emphasis is
    presentation); narration never enters; code-baked chrome never appears
    (``_screen_strings``' own law)."""
    parts: list[str] = []
    for s in board.scenes:
        source = getattr(s, "copy_text", None)
        if isinstance(source, str) and source.strip():
            parts.append(source.strip())
            continue
        for _slot, text in _screen_strings(s):
            if stripped := text.replace("*", "").strip():
                parts.append(stripped)
    return "\n".join(parts)


def _sync_text_source(
    before: FilmStoryboard, work: FilmStoryboard, work_params: dict
) -> None:
    """逐字律的版本侧 (文字片编辑): a text film's pinned ``text`` FOLLOWS its
    board — an explicit copy edit re-declares the corpus, so the new
    version's text source IS what the board now says: the next redraft
    drafts from the user's current words (never silently resurrecting
    replaced ones), and the run's re-validation grounds the version against
    its own declared corpus. Mutation is op-scoped (an op writes only the
    scene it names), so untouched scenes' words carry over byte-identical
    (未修改场景保持). No-op for web films (no text pin) and when the
    on-screen words did not change — a seconds/motion/narration-only batch
    keeps the pinned text byte-stable (修改只影响声明范围)."""
    if not work_params.get("text"):
        return
    new_text = _board_copy_text(work)
    if new_text == _board_copy_text(before):
        return
    work_params["text"] = new_text


def apply_film_edits(
    board: FilmStoryboard,
    params: dict,
    ops: list[FilmEditOp],
    *,
    expected_base_digest: str | None = None,
    base_version: int | None = None,
    base_cut: tuple[str | None, list[int] | None, list[int | None] | None] | None = None,
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
    content but never its references). ``base_cut`` = the resolved base's
    frozen-timeline triple (``film_base_cut``) — it binds the identity to
    the version's TIMELINE state, so same-content same-number branch
    versions with different frozen cuts never share a reference.

    ``validate`` (optional) is the semantic-law seat: it receives the
    PATCHED board + params and returns violations (the design beat wires
    ``validate_storyboard`` there); any violation rejects the batch as
    ``validation_failed``. On ANY FilmEditError the caller's base version
    stands untouched — the failure carries nothing partial.
    """
    if not ops:
        raise FilmEditError("empty_ops", "an edit batch holds at least one op")
    base_identity = film_version_identity_digest(
        board, params, version=base_version, cut=base_cut
    )
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

    try:
        work = FilmStoryboard.model_validate(work.model_dump(mode="json"))
    except ValidationError as exc:
        raise FilmEditError("validation_failed", str(exc)) from exc

    # 文字来源同步 (逐字律版本侧): an explicit copy edit re-declares a text
    # film's corpus — the version's pinned text follows its board, so the
    # validation below (and later the redraft / the run's re-validation)
    # reads the user's CURRENT words, never the replaced ones.
    _sync_text_source(before, work, work_params)

    # 旁白存在律 (音频三态): a batch that turns voiceover ON must leave the
    # board carrying narration lines to synthesize — the refusal names a
    # CONTENT gap (author the lines first), never a synthesis/voice
    # problem. Judged on the POST-batch board (order-independent — one
    # batch may author the lines and re-enable in the same pass); the run's
    # own fail-closed seat (a promised-voice film never ships silent) stays
    # the last line of defense for every other birth path.
    if (
        canonical_film_params(params)["voiceover"] is False
        and canonical_film_params(work_params)["voiceover"] is True
        and not any(
            (getattr(s, "narration", None) or "").strip() for s in work.scenes
        )
    ):
        raise FilmEditError(
            "voiceover_needs_narration",
            "voiceover was switched on but the board carries NO narration "
            "lines — author the lines first (update_scene with narration on "
            "the speech-carrying scenes), then re-issue set_voiceover",
        )

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
    """The publish unit the chat wiring stamps.

    ``film.presentation`` is the shared FULL fact sheet for the saved
    version. ``change_presentation`` is the separate system-computed delta
    summary; a patch presents both, never asks the model to reconstruct the
    current table from an old table plus a diff. ``next_base_ref`` is THIS
    version's identity digest, minted at presentation time (the next edit's
    read-time reference).
    """

    film: DockStoryboard
    change_presentation: str
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


def _change_value(value: Any) -> str:
    """One exact, compact value for the model-facing before/after fact."""
    if value is None:
        return "(none)"
    if isinstance(value, list):
        return " / ".join(str(v).replace("\n", "<br>") for v in value)
    return str(value).replace("\n", "<br>")


_COPY_CHANGE_FIELDS = frozenset(
    {"narration", "word", "sub", "lines", "label", "roll", "lead", "title", "name", "tagline"}
)


def _copy_change_lines(
    base_scene: FilmScene,
    result_scene: FilmScene,
    fields: list[str],
) -> list[str]:
    """Show the actual copy delta, not just the field name.

    The full board remains the authority for the complete version; these
    companion lines make an unaccepted text difference reviewable without
    asking the model to infer it from a punctuation/re-segmentation diff.
    """
    out: list[str] = []
    for field in fields:
        if field in _COPY_CHANGE_FIELDS:
            before = getattr(base_scene, field, None)
            after = getattr(result_scene, field, None)
            if before != after:
                out.append(
                    f"{field}: \"{_change_value(before)}\" → \"{_change_value(after)}\""
                )
            continue
        parts = field.split(".")
        if len(parts) != 3 or parts[0] != "elements" or parts[2] != "lines":
            continue
        before_el = next(
            (e for e in getattr(base_scene, "elements", []) if e.element_id == parts[1]),
            None,
        )
        after_el = next(
            (e for e in getattr(result_scene, "elements", []) if e.element_id == parts[1]),
            None,
        )
        if before_el is not None and after_el is not None and before_el.lines != after_el.lines:
            out.append(
                f"text [{parts[1]}] lines: \"{_change_value(before_el.lines)}\" → "
                f"\"{_change_value(after_el.lines)}\""
            )
    return out


def change_set_presentation(
    change_set: FilmChangeSet,
    board: FilmStoryboard,
    base_board: FilmStoryboard | None = None,
) -> str:
    """The patch's system-computed DELTA companion to the full fact sheet.

    ``base_board`` is optional for legacy callers; when supplied, changed
    copy also carries exact before/after values. Scene numbers are 1-based
    to match the fact sheet's ``scene N`` numbering; bracketed ids remain
    internal edit handles for the model, never user-facing copy.
    """
    by_id = {s.scene_id: s for s in board.scenes}
    base_by_id = {s.scene_id: s for s in (base_board.scenes if base_board else [])}

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
        for note in edited.notes:
            lines.append(f"  · {note}")
        scene = by_id.get(edited.scene_id)
        base_scene = base_by_id.get(edited.scene_id)
        if scene is not None and base_scene is not None:
            for copy_line in _copy_change_lines(base_scene, scene, edited.fields):
                lines.append(f"  · {copy_line}")
        if scene is not None and FILM_WORDS_TIMING_FIELDS.intersection(edited.fields):
            timing = words_timing_clause(scene)
            if timing:
                # The confirmation beat's cumulative fact: values, not only
                # field names (and seconds carry their quantized frame landing).
                lines.append(f"  · now: {timing}")
        if scene is not None and FILM_WORDS_STYLE_FIELDS.intersection(edited.fields):
            style = _text_style_clause(scene)
            if style:
                lines.append(f"  · now: {style}")
        if scene is not None and scene.type == "composite":
            # ADR-140: an element window/timing edit shows the element's
            # NOW line — the same cumulative-fact law, one level down.
            frames = film_seconds_to_frames(scene.seconds)
            shown: set[str] = set()
            for field in edited.fields:
                if not field.startswith("elements."):
                    continue
                parts = field.split(".")
                if len(parts) < 3:
                    continue  # "(new)" / "(removed)" lines carry no now-state
                eid, leaf = parts[1], parts[2]
                if eid in shown or (
                    leaf not in _ELEMENT_TIMING_FIELDS
                    and leaf not in {"at", "until", "tone"}
                    and leaf not in FILM_WORDS_STYLE_FIELDS
                ):
                    continue
                el = next(
                    (e for e in scene.elements if e.element_id == eid), None
                )
                if el is None or el.kind != "text":
                    continue
                shown.add(eid)
                leave = (
                    f"{el.until:g}s" if el.until is not None else "the scene's end"
                )
                clause = element_timing_clause(el, frames)
                style = _text_style_clause(el)
                extras = [c for c in (clause, style) if c]
                lines.append(
                    f"  · [{eid}] now: on screen {el.at:g}s–{leave} ({el.tone})"
                    + (f" · {' · '.join(extras)}" if extras else "")
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
        # 明确关闭的呈现 (音频三态): OFF is a state, never a track name —
        # unquoted; a recut with the bed off re-times on NO grid.
        if music.mood_after == FILM_MUSIC_OFF:
            retime = (
                "re-cut without a beat grid"
                if music.retime == "recut"
                else "existing cuts kept"
            )
            if (music.mood_before or "") == music.mood_after:
                lines.append(f"- music: off (no bed) — {retime}")
            else:
                before = f'"{music.mood_before}"' if music.mood_before else "none"
                lines.append(f"- music: {before} → off (no bed) — {retime}")
        else:
            retime = (
                "re-cut to the track's beat grid"
                if music.retime == "recut"
                else "existing cuts kept"
            )
            if (music.mood_before or "") == music.mood_after:
                lines.append(f'- music: "{music.mood_after}" (same track) — {retime}')
            else:
                before = (
                    "off (no bed)"
                    if music.mood_before == FILM_MUSIC_OFF
                    else (f'"{music.mood_before}"' if music.mood_before else "none")
                )
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
    - the grounding universe follows the version's pinned SOURCE (素材源
      分派): a text film (params pin ``text``) validates against its own
      copy — an explicit copy edit re-declares the corpus
      (``_sync_text_source``, inside the apply) so new words never meet
      the replaced original's validation; a web film validates against the
      project's captured pages — gone, the edit cannot stand
      (``pages_missing``);
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
    # 素材源分派 (ADR-138 §7.6): the version's pinned corpus decides the
    # grounding universe. A TEXT film (params pin ``text``) grounds on its
    # own copy — no captured pages exist or are needed; a WEB film grounds
    # on the project's captured pages, and their absence rejects honestly.
    text_film = bool(params.get("text"))
    if text_film:
        pages: list = []
    else:
        pages = await load_storyboard_pages(db, project)
        if not pages:
            raise FilmEditError(
                "pages_missing",
                "the project's captured pages are gone — the edit's grounding "
                "universe is missing; re-capture the site, then re-issue the edit",
            )

    # ADR-140 media universe: loaded from the BASE board (update_element
    # never changes asset identity, so base and patched boards cite the
    # same ids). This is a WRITE seat — unknown video durations probe the
    # bytes now and the truth is checked (never guessed), and the probed
    # seconds write back to the row.
    media = await load_storyboard_media(db, project, board, probe_duration=True)

    def _validate(b: FilmStoryboard, p: dict) -> list:
        canonical = canonical_film_params(p)
        if p.get("text"):
            # The text leg: the (possibly copy-synced) pinned corpus is the
            # grounding universe; page-coupled scene types are illegal; every
            # words plane must fit its reading pace.
            return validate_storyboard(
                b,
                [],
                narration_required=canonical["voiceover"],
                text_lines=build_text_manifest(str(p["text"])),
                media=media,
            )
        return validate_storyboard(
            b, pages, narration_required=canonical["voiceover"], media=media
        )

    result = apply_film_edits(
        board,
        params,
        ops,
        expected_base_digest=base_ref,
        base_version=getattr(base, "film_storyboard_version", None),
        base_cut=film_base_cut(base),
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
    if result.change_set.music is not None and mood and mood != FILM_MUSIC_OFF:
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
    elif mood == FILM_MUSIC_OFF:
        # 明确关闭 (音频三态): a real terminal state — NO track to resolve
        # (the strict gate never fires on it, the fallback chain never
        # re-opens it); the version's snapshot carries no bed and the run
        # short-circuits the same way.
        track = None
    else:
        track = await film_snapshot_track(db, project, result.params)

    execution = build_film_execution_snapshot(
        pages=pages, track=track, media=media
    )
    if canonical.get("music_mood") == FILM_MUSIC_OFF:
        music_label = "off (no bed)"
    elif track is not None:
        music_label = f"{track.mood} — {track.title}"
        bpm = _track_bpm(track)
        if bpm is not None:
            music_label += f" · {bpm:g} BPM"
    else:
        music_label = None
    subtitle_frames = kept_frames or execution_frames(result.board, _track_beats(track))
    for scene, n in zip(result.board.scenes, subtitle_frames, strict=True):
        if scene.subtitle_track and scene.subtitle_track.cues[-1].end > n / FILM_FPS:
            raise FilmEditError(
                "subtitle_window", "subtitle cues exceed the actual scene duration; "
                "read its timeline and adjust cue times", scene_id=scene.scene_id,
            )
    presentation = storyboard_presentation(
        result.board,
        pages,
        aspect=canonical.get("aspect") or "16:9",
        music=music_label,
        beats=_track_beats(track),
        bpm=_track_bpm(track),
        voiceover=canonical["voiceover"],
        source_note=_text_source_note(film_text_source_from_params(result.params)),
        media=media,
        frame_override=kept_frames,
    )
    return FilmPatchPrepared(
        film=DockStoryboard(
            presentation=presentation,
            storyboard=result.board.model_dump(mode="json"),
            fingerprint=storyboard_fingerprint(
                [{"tool": "launch_film", "params": result.params}], instruction
            ),
            reused=False,
            execution=execution,
        ),
        change_presentation=change_set_presentation(
            result.change_set, result.board, base_board=ensure_scene_ids(board)
        ),
        params=result.params,
        change_set=result.change_set,
        result=result,
        next_base_ref=film_version_identity_digest(
            result.board,
            result.params,
            version=(getattr(base, "film_storyboard_version", None) or 0) + 1,
            # The next version's own timeline state (冻结时间轴 = 版本状态):
            # a cut kept by this batch freezes onto the new version (its
            # read-back surface derives the same "kept" triple from the
            # envelope); every other birth is a draft — no frozen cut.
            cut=(
                ("kept", kept_frames, kept_reveal_onsets)
                if kept_frames is not None
                else None
            ),
        ),
        kept_frames=kept_frames,
        kept_reveal_onsets=kept_reveal_onsets,
    )
