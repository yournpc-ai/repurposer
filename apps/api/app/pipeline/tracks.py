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
    owner: tuple[str, ...]  # sole writer skill(s) post-birth
    mutex: tuple[str, ...]  # mutually-exclusive slot labels
    pairs: tuple[str, ...]  # declared pairings (translation ⇄ caption)
    provenance: str  # real | generated (ADR-026)
    url_fields: tuple[str, ...]  # dotted paths; "[*]" expands a list at that part
    checks: tuple[str, ...]  # deterministic craft checks (residents with skill packages)
    fields: tuple[str, ...]  # ClipSpec top-level keys this track owns (the partition)


TRACKS: dict[str, TrackDef] = {
    "main": TrackDef(
        family="sequence", timeline="source",
        owner=("select_clips", "materialize_source"),
        mutex=(), pairs=(), provenance="real",
        # segments[*].url: hetero splice donor URLs (切 op) ride the same seam
        url_fields=("source.url", "source.image_urls[*]", "segments[*].url"),
        checks=(),
        fields=("source", "segments", "aspect", "target_language"),
    ),
    "caption": TrackDef(
        family="data", timeline="source",
        owner=("preprocess", "remove_filler"),
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
    block's card seconds. Unknown tracks contribute nothing (and never crash
    the fold).
    """
    reg = TRACKS if tracks is None else tracks
    total = 0.0
    segments = spec.get("segments", []) if "segments" in reg["main"].fields else []
    total += sum(
        max(0.0, float(s.get("end", 0)) - float(s.get("start", 0)))
        for s in segments
        if not s.get("hidden")
    )
    brand = spec.get("brand") if "brand" in reg["intro_outro"].fields else None
    if isinstance(brand, dict):
        for card_key, default in (("intro", 2.0), ("outro", 2.0)):
            card = brand.get(card_key)
            if isinstance(card, dict):
                total += float(card.get("duration_seconds") or default)
    return total if total > 0 else 1 / 30.0


def track_of_field(field: str, *, tracks: dict[str, TrackDef] | None = None) -> str | None:
    """Which track owns this spec top-level field (None = unregistered)."""
    for name, track in (TRACKS if tracks is None else tracks).items():
        if field in track.fields:
            return name
    return None


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
