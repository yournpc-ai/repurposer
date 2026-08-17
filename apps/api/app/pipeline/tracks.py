"""Python mirror of the TRACK_REGISTRY catalog (packages/clip/src/tracks.ts) — ADR-044.

Double-end discipline (CAPTION_PRESETS 同款): the TS catalog is the source of
truth; this mirror validates membership and consumes declarations only. Drift
guard: ``scripts/check_track_registry.py`` diffs the two ends.

Consumers fold through the helpers below — never special-case a spec field:

- :func:`resolve_spec_urls` — the bake seam (``rendering._absolutize``) walks
  declared ``url_fields``.
- :func:`spec_provenance` — ADR-026 classification reads track provenance.
- :func:`total_output_seconds` — pricing's duration mirror (estimate fold).
- :func:`track_of_field` — ops addressing reconciliation.

The two boot-time self-checks (:func:`assert_track_registry`,
:func:`assert_phantom_track`) are mounted in
``orchestrator.assert_runners_registered`` (API lifespan + worker startup).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class TrackDef:
    family: str  # sequence | data | layer | block
    timeline: str  # source | output | derived — declared, never implemented per-track
    owner: tuple[str, ...]  # writer skill(s) post-birth (birth producers write any track)
    mutex: tuple[str, ...]  # mutually-exclusive slot labels
    pairs: tuple[str, ...]  # declared pairings (translation ⇄ caption)
    provenance: str  # real | generated (ADR-026)
    url_fields: tuple[str, ...]  # dotted paths; "[*]" expands a list at that part
    checks: tuple[str, ...]  # deterministic craft checks (residents with skill packages)
    fields: tuple[str, ...]  # ClipSpec top-level keys this track owns (the partition)
    # Tracks this one DERIVES from (ADR-044 派生轨失效声明): an op writing a
    # dependency's fields makes this track stale (dub ⟵ main timeline).
    depends: tuple[str, ...] = ()


TRACKS: dict[str, TrackDef] = {
    "main": TrackDef(
        family="sequence", timeline="source",
        # births write it; remove_filler is the timeline's morph writer
        owner=("select_clips", "materialize_source", "remove_filler"),
        mutex=(), pairs=(), provenance="real",
        # segments[*].url: hetero splice donor URLs (切 op) ride the same seam
        url_fields=("source.url", "source.image_urls[*]", "segments[*].url"),
        checks=(),
        fields=("source", "segments", "aspect", "target_language"),
    ),
    "caption": TrackDef(
        family="data", timeline="source",
        # preprocess writes the ASSET's words (birth input), never the spec
        # post-birth — the spec track's sole morph writer is remove_filler
        owner=("remove_filler",),
        mutex=(), pairs=(), provenance="real",
        url_fields=(), checks=(),
        fields=("caption_track", "caption_style_preset", "caption_position", "caption_enabled"),
    ),
    "translation": TrackDef(
        family="data", timeline="source",
        owner=("translate_clip",),
        mutex=(), pairs=("caption",), provenance="real",
        url_fields=(), checks=(),
        fields=("translation_track",),
    ),
    "crop": TrackDef(
        family="data", timeline="source",
        # birth default today; reframe_clip becomes the writer on the 08-19 line
        owner=("select_clips", "materialize_source"),
        mutex=(), pairs=(), provenance="real",
        url_fields=(),
        # 08-19 residents: crop-stays-on-face / min-dwell / anti-jump-cut easing
        checks=(),
        # + "crop_track" on the 08-19 line — the boot partition check forces it
        fields=("crop",),
    ),
    "layers": TrackDef(
        family="layer", timeline="derived",  # anchor → output position, projected at the bake seam
        owner=(),  # insert_broll lands on the 08-19+ line; nothing writes yet
        mutex=(), pairs=(),
        provenance="real",  # item-level: every layer declares its own (必填)
        url_fields=("layers[*].media.url",),
        checks=(),  # 08-19+ residents: broll min-dwell / callout contrast …
        fields=("layers",),
    ),
    "title": TrackDef(
        family="block", timeline="output",
        owner=("select_clips", "materialize_source"),
        mutex=(), pairs=(), provenance="real",
        url_fields=(), checks=(),
        fields=("title",),
    ),
    "music": TrackDef(
        family="block", timeline="output",
        owner=("add_music",),
        mutex=(), pairs=(), provenance="real",
        url_fields=("music.url",),
        checks=(),
        fields=("music",),
    ),
    "dub": TrackDef(
        family="block", timeline="output",
        owner=("dub_clip",),
        mutex=("original_audio",),  # dub.enabled ⇒ the main track's original audio mutes
        pairs=(), provenance="generated",  # voice clone = synthetic track (ADR-026)
        url_fields=("dub.url",),
        checks=(),
        fields=("dub",),
        # The dub audio is one continuous file locked to the OUTPUT timeline —
        # a main-timeline op (trim/cut/reorder/insert) desyncs it (ADR-044).
        depends=("main",),
    ),
    "intro_outro": TrackDef(
        family="block", timeline="output",
        owner=(),  # persona-skin bake at generation; no skill writes post-birth
        mutex=(), pairs=(), provenance="real",
        url_fields=("brand.intro.media_url", "brand.outro.media_url"),
        checks=(),
        fields=("brand", "brand_ref"),
    ),
}


# ---- fold helpers ---------------------------------------------------------


def _iter_url_slots(spec: Any, path: str) -> Iterable[tuple[dict, str, bool]]:
    """Yield ``(dict_node, key, is_list)`` slots a dotted url path resolves to.

    ``[*]`` expands a list at that path part (e.g. ``segments[*].url`` walks
    every segment); on the LEAF (e.g. ``source.image_urls[*]``) the yielded
    slot is the list itself. Missing/None intermediates yield nothing — an
    absent track has nothing to resolve.
    """
    parts = path.split(".")
    frontier: list[Any] = [spec]
    for part in parts[:-1]:
        is_list = part.endswith("[*]")
        key = part[:-3] if is_list else part
        nxt: list[Any] = []
        for node in frontier:
            if not isinstance(node, dict):
                continue
            value = node.get(key)
            if value is None:
                continue
            if is_list:
                if isinstance(value, list):
                    nxt.extend(v for v in value if isinstance(v, dict))
            else:
                nxt.append(value)
        frontier = nxt
    leaf = parts[-1]
    if leaf.endswith("[*]"):
        key = leaf[:-3]
        for node in frontier:
            if isinstance(node, dict) and isinstance(node.get(key), list):
                yield node, key, True
    else:
        for node in frontier:
            if isinstance(node, dict):
                yield node, leaf, False


def resolve_spec_urls(
    spec: dict[str, Any],
    resolve: Callable[[str], str],
    *,
    tracks: dict[str, TrackDef] | None = None,
) -> dict[str, Any]:
    """Bake-seam fold: run ``resolve`` over every declared ``url_fields`` slot.

    Registry-driven — a newly registered track's URLs are absolutized with
    zero changes here. Mutates and returns ``spec``.
    """
    for track in (TRACKS if tracks is None else tracks).values():
        for path in track.url_fields:
            for node, key, is_list in _iter_url_slots(spec, path):
                if is_list:
                    node[key] = [
                        resolve(v) if isinstance(v, str) and v else v for v in node[key]
                    ]
                else:
                    value = node.get(key)
                    if isinstance(value, str) and value:
                        node[key] = resolve(value)
    return spec


def spec_provenance(
    spec: dict[str, Any], *, tracks: dict[str, TrackDef] | None = None
) -> str:
    """ADR-026 classification fold: ``"generated"`` iff a track DECLARED
    generated is present-and-enabled in this spec (presence = a truthy field
    value; a block carrying ``enabled: false`` is off and doesn't count) — or
    any main-track segment is marked generated (a synthetic splice makes the
    product synthetic media even though the main track's default is "real").
    """
    for segment in spec.get("segments") or []:
        if isinstance(segment, dict) and segment.get("provenance") == "generated":
            return "generated"
    for layer in spec.get("layers") or []:
        if isinstance(layer, dict) and layer.get("provenance") == "generated":
            return "generated"
    for track in (TRACKS if tracks is None else tracks).values():
        if track.provenance != "generated":
            continue
        for field in track.fields:
            value = spec.get(field)
            if not value:
                continue
            if isinstance(value, dict) and value.get("enabled") is False:
                continue
            return "generated"
    return "real"


def total_output_seconds(
    spec: dict[str, Any], *, tracks: dict[str, TrackDef] | None = None
) -> float:
    """Python mirror of ``totalDurationSeconds`` (packages/clip/src/types.ts).

    Per-family contribution logic lives here once; the registry declares the
    field homes: the sequence family's kept segments + the intro_outro
    block's card seconds (arithmetic shared with the lane-projection mirrors
    in app/pipeline/clip_spec.py). Unknown tracks contribute nothing (and
    never crash the fold).
    """
    from app.pipeline.clip_spec import intro_seconds, outro_seconds, video_duration_seconds

    reg = TRACKS if tracks is None else tracks
    total = 0.0
    if "segments" in reg["main"].fields:
        total += video_duration_seconds(spec)
    if "brand" in reg["intro_outro"].fields:
        total += intro_seconds(spec) + outro_seconds(spec)
    return total if total > 0 else 1 / 30.0  # >= a frame (COMPOSITION_FPS=30)


def track_of_field(field: str, *, tracks: dict[str, TrackDef] | None = None) -> str | None:
    """Which track owns this spec top-level field (None = unregistered)."""
    for name, track in (TRACKS if tracks is None else tracks).items():
        if field in track.fields:
            return name
    return None


# ---- ops-closure helpers (ADR-044 D7) --------------------------------------


def skill_written_tracks(kind: str, *, tracks: dict[str, TrackDef] | None = None) -> set[str]:
    """The clip-spec tracks a skill writes post-birth: its owned tracks plus
    their declared pairs (translate_clip → translation + caption)."""
    written: set[str] = set()
    for name, track in (TRACKS if tracks is None else tracks).items():
        if kind in track.owner:
            written.add(name)
            written.update(track.pairs)
    return written


def track_present(spec: dict[str, Any], track: TrackDef) -> bool:
    """The track has live content in this spec (a truthy field value; a block
    carrying ``enabled: false`` is off and doesn't count)."""
    for field in track.fields:
        value = spec.get(field)
        if not value:
            continue
        if isinstance(value, dict) and value.get("enabled") is False:
            continue
        return True
    return False


def stale_tracks(
    spec: dict[str, Any],
    written_fields: Iterable[str],
    *,
    tracks: dict[str, TrackDef] | None = None,
) -> list[str]:
    """派生轨失效声明 (ADR-044): given the spec fields an op batch just wrote,
    the present-and-enabled tracks whose declared dependencies were touched —
    e.g. a main-timeline op on a dubbed spec stales the dub. The caller
    surfaces the list (重配一句话); the spec is never silently "legal".
    """
    written = {
        track
        for field in written_fields
        if field != "*" and (track := track_of_field(field, tracks=tracks)) is not None
    }
    if not written:
        return []
    return [
        name
        for name, track in (TRACKS if tracks is None else tracks).items()
        if track.depends and set(track.depends) & written and track_present(spec, track)
    ]


def assert_single_writer_per_track(
    steps: Iterable[tuple[str, dict | None]],
    is_producer: Callable[[str], bool],
) -> None:
    """一轨一写者 (ADR-044): within one run, a clip-spec track takes at most
    ONE non-fork morph writer. Birth producers create the row (they write
    every track by construction) and fork steps derive their own rows — both
    exempt. A collision is a compile-time error (422 at create_run), never a
    runtime merge.

    ``steps`` are (kind, spec) pairs of the compiled run; ``is_producer``
    marks row-creating kinds (NODE_KINDS[…].produces_outputs).
    """
    claims: dict[str, str] = {}
    for kind, spec in steps:
        if is_producer(kind):
            continue
        if (spec or {}).get("fork"):
            continue
        for track in sorted(skill_written_tracks(kind)):
            prior = claims.get(track)
            if prior is not None:
                raise ValueError(
                    f"track collision: '{prior}' and '{kind}' both write track "
                    f"'{track}' in one run — fork one of them or split the runs"
                )
            claims[track] = kind


# ---- boot-time self-checks (mounted in orchestrator.assert_runners_registered)


def assert_track_registry() -> None:
    """Check ① (对账 = ⊆): every ClipSpec top-level field is owned by EXACTLY
    one track — the partition must be complete and disjoint — and every op's
    declared ``writes`` stay inside the partition (ops addressing fold).
    """
    from app.models.schemas import ClipSpec  # deferred: schemas import graph

    declared: dict[str, str] = {}
    for name, track in TRACKS.items():
        for field in track.fields:
            prior = declared.get(field)
            if prior is not None:
                raise RuntimeError(
                    f"Track field '{field}' claimed by both '{prior}' and '{name}'"
                )
            declared[field] = name
    model_fields = set(ClipSpec.model_fields)
    missing = model_fields - set(declared)
    unknown = set(declared) - model_fields
    if missing:
        raise RuntimeError(
            f"ClipSpec fields not registered to any track: {sorted(missing)}"
        )
    if unknown:
        raise RuntimeError(
            f"TRACK_REGISTRY declares fields not on ClipSpec: {sorted(unknown)}"
        )

    from app.operations.registry import OP_REGISTRY  # deferred: ops import graph

    for op_name, opdef in OP_REGISTRY.items():
        for field in opdef.writes:
            if field == "*":  # whole-spec system/snapshot ops
                continue
            if field not in declared:
                raise RuntimeError(
                    f"op '{op_name}' writes unregistered spec field '{field}'"
                )


def assert_phantom_track() -> None:
    """Check ② (elasticity fixture, ADR-044): register a PHANTOM track and
    prove the consumers — bake seam / addressing / compliance / pricing —
    take it over with zero consumer-side changes. The real registry never
    sees it.
    """
    phantom = TrackDef(
        family="block", timeline="output",
        owner=("phantom_skill",), mutex=(), pairs=(),
        provenance="generated",
        url_fields=("phantom_badge.url",),
        checks=(), fields=("phantom_badge",),
    )
    reg = {**TRACKS, "phantom": phantom}
    spec: dict[str, Any] = {
        "phantom_badge": {"url": "user/uploads/badge.png", "enabled": True}
    }

    # bake seam: the phantom's URL is absolutized by the fold, no branch added
    out = resolve_spec_urls(spec, lambda v: f"https://cdn.test/{v}", tracks=reg)
    assert out["phantom_badge"]["url"] == "https://cdn.test/user/uploads/badge.png"
    # compliance: declared generated provenance classifies the spec
    assert spec_provenance(spec, tracks=reg) == "generated"
    off = {"phantom_badge": {"url": "user/uploads/badge.png", "enabled": False}}
    assert spec_provenance(off, tracks=reg) == "real"
    # addressing: the field resolves to its track
    assert track_of_field("phantom_badge", tracks=reg) == "phantom"
    # pricing: the duration fold tolerates the unknown track untouched
    assert total_output_seconds({"segments": [], "phantom_badge": {}}, tracks=reg) > 0
    # the real registry stays ignorant — the phantom never leaks in
    assert track_of_field("phantom_badge") is None
