"""Beat-map resolution — the code half of 理解层 v2 (期 1).

The LLM (understand) writes only verbatim text anchors — opening
``marker`` words, full quotable ``text``, emphasized ``word`` — plus an
optional coarse ``approx_start`` copied from the cue-line prefixes. This
module snaps those anchors onto the ASR word axis and stamps the resolved
``start`` / ``end`` / ``asset_id`` — word-level timestamps are the
deterministic foundation and are never LLM output (简报铁律; the
``locate_span`` doctrine: LLM proposes coarse marks, code snaps to word
boundaries). It also sets the quotable lines' ``self_contained`` flag
(code-checked, never the LLM's).

Pure functions over schema objects — no DB, no providers.
"""

from __future__ import annotations

import re
import string
from typing import Any

import structlog

from app.models.schemas import AssetType, MaterialUnderstanding

logger = structlog.get_logger()

# An approx_start hint narrows the anchor search to ±this many seconds
# before falling back to a global scan.
_APPROX_WINDOW_S = 45.0
# Minimum positional match ratio for a fuzzy (non-exact) anchor match.
_FUZZY_MIN_RATIO = 0.8

_PUNCT_TABLE = str.maketrans("", "", string.punctuation + "，。！？；：、（）【】《》“”‘’—…·")

# Self-containment heuristics: a quotable line opening with a dangling
# pronoun / connective (or trailing off on one) does not stand alone on a
# quote card / caption pull.
_DANGLING_OPENERS_EN = {
    "it", "its", "this", "that", "these", "those", "they", "them", "their",
    "he", "she", "his", "her", "him", "such", "there", "here",
    "but", "and", "so", "or", "yet", "nor", "for", "because", "also", "too",
    "however", "therefore", "then", "thus", "hence", "still", "though",
    "although", "while", "if", "when", "after", "before", "until", "unless",
    "since", "as", "moreover", "furthermore", "nevertheless", "nonetheless",
    "besides", "instead", "otherwise", "meanwhile", "finally", "secondly",
    "thirdly", "additionally", "consequently", "well", "now", "yes", "no",
}
_DANGLING_OPENERS_ZH = {
    "这", "那", "它", "他", "她", "他们", "她们", "它们", "这些", "那些",
    "但", "但是", "而且", "并且", "所以", "因此", "然后", "于是", "不过",
    "然而", "因为", "如果", "当", "虽然", "尽管", "另外", "此外", "同时",
    "接着", "最后", "首先", "其次", "或者", "还是", "也", "又", "再",
}


def _norm(text: str) -> str:
    """Lowercase, strip punctuation and whitespace — the anchor match space."""
    return text.lower().translate(_PUNCT_TABLE).replace(" ", "").replace("\n", "")


def self_contained(text: str) -> bool:
    """Code-side self-containment check for a quotable line."""
    stripped = text.strip()
    if not stripped:
        return False
    first = stripped.split(None, 1)[0].lower().strip(string.punctuation)
    if first in _DANGLING_OPENERS_EN:
        return False
    for opener in _DANGLING_OPENERS_ZH:
        if stripped.startswith(opener):
            return False
    # Trailing off: ends on a comma / connective rather than a full stop.
    if stripped[-1] in ",;:" or stripped[-1] in "，；：、—":
        return False
    return True


class _Axis:
    """One asset's word axis preprocessed for anchor search."""

    def __init__(self, asset_id: str, words: list[dict[str, Any]]):
        self.asset_id = asset_id
        self.words = words
        # Char stream of normalized word tokens + each word's char offset.
        self.stream = ""
        self.offsets: list[int] = []
        for w in words:
            self.offsets.append(len(self.stream))
            self.stream += _norm(str(w.get("word") or ""))

    def word_index_at(self, char_pos: int) -> int | None:
        """The word whose token covers the stream position (or None)."""
        lo, hi = 0, len(self.offsets) - 1
        if hi < 0:
            return None
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.offsets[mid] <= char_pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def word_start_s(self, index: int) -> float:
        return float(self.words[index].get("start") or 0)

    def time_window(self, approx: float | None) -> tuple[int, int] | None:
        """Char-range of the ±_APPROX_WINDOW_S time window around approx."""
        if approx is None or not self.words:
            return None
        lo_t, hi_t = approx - _APPROX_WINDOW_S, approx + _APPROX_WINDOW_S
        idx = [
            i
            for i, w in enumerate(self.words)
            if lo_t <= float(w.get("start") or 0) <= hi_t
        ]
        if not idx:
            return None
        start_char = self.offsets[idx[0]]
        last = idx[-1]
        # End = start of the word AFTER the last in-window word (or stream end).
        end_char = self.offsets[last + 1] if last + 1 < len(self.offsets) else len(self.stream)
        return (start_char, end_char)


def _locate_char_span(
    axis: _Axis, quote: str, approx: float | None
) -> tuple[int, int] | None:
    """Find the quote's char span in the axis stream (exact, then fuzzy)."""
    q = _norm(quote)
    if not q or not axis.stream:
        return None

    def search(lo: int, hi: int) -> tuple[int, int] | None:
        hay = axis.stream[lo:hi]
        pos = hay.find(q)
        if pos >= 0:
            return (lo + pos, lo + pos + len(q))
        # Fuzzy: best fixed-length window by positional match ratio.
        if len(q) > len(hay):
            return None
        best_pos, best_hits = -1, int(len(q) * _FUZZY_MIN_RATIO)
        for i in range(0, len(hay) - len(q) + 1):
            hits = sum(1 for a, b in zip(hay[i : i + len(q)], q) if a == b)
            if hits > best_hits:
                best_pos, best_hits = i, hits
        return (lo + best_pos, lo + best_pos + len(q)) if best_pos >= 0 else None

    window = axis.time_window(approx)
    if window is not None:
        found = search(*window)
        if found is not None:
            return found
    return search(0, len(axis.stream))


def _locate(
    axes: list[_Axis], quote: str, approx: float | None
) -> tuple[_Axis, int, int] | None:
    """Locate a verbatim quote across axes → (axis, first_word, last_word)."""
    for axis in axes:
        span = _locate_char_span(axis, quote, approx)
        if span is None:
            continue
        w0 = axis.word_index_at(span[0])
        w1 = axis.word_index_at(max(span[0], span[1] - 1))
        if w0 is not None and w1 is not None:
            return (axis, w0, w1)
    logger.warning("beat_map_anchor_unresolved", quote=quote[:60])
    return None


def _chain_ends(resolved: list[tuple[Any, "_Axis", int]]) -> None:
    """Chain segment ends within each asset: a segment's end = the word-END
    of the last word before the next segment's first word (spans cover whole
    words; the cut lands in the pause). The last segment ends at the axis's
    final word end. ``resolved`` = (item, axis, first_word_index) triples."""
    by_asset: dict[str, list[tuple[Any, _Axis, int]]] = {}
    for item, axis, w0 in resolved:
        by_asset.setdefault(axis.asset_id, []).append((item, axis, w0))
    for group in by_asset.values():
        group.sort(key=lambda t: t[0].start)  # start is monotonic in w0
        for i, (item, axis, w0) in enumerate(group):
            if i + 1 < len(group):
                _, next_axis, next_w0 = group[i + 1]
                if next_w0 > w0:
                    item.end = float(next_axis.words[next_w0 - 1].get("end") or 0)
                else:  # degenerate: same anchor word — zero-length span
                    item.end = group[i + 1][0].start
            else:
                item.end = float(axis.words[-1].get("end") or 0)


def resolve_beat_map(
    understanding: MaterialUnderstanding,
    word_axis: list[dict[str, Any]],
    image_refs: list[dict[str, str]],
) -> MaterialUnderstanding:
    """Snap every beat-map anchor onto the word axis; flag quotable lines.

    ``word_axis`` = [{"asset_id", "words"}] per word-bearing asset;
    ``image_refs`` = [{"ref": "image 1", "asset_id"}] in media order.
    Unresolved anchors keep start/end=None — the fields stay honest (a miss
    is data, never a fabricated time).
    """
    axes = [
        _Axis(str(a["asset_id"]), [w for w in a["words"] if str(w.get("word") or "").strip()])
        for a in word_axis
        if a.get("words")
    ]

    resolved_boundaries: list[tuple[Any, _Axis, int]] = []
    for b in understanding.topic_boundaries:
        hit = _locate(axes, b.marker, b.approx_start)
        if hit:
            axis, w0, _ = hit
            b.asset_id, b.start = axis.asset_id, axis.word_start_s(w0)
            resolved_boundaries.append((b, axis, w0))
    _chain_ends(resolved_boundaries)

    for c in understanding.climax_spans:
        hit = _locate(axes, c.text, c.approx_start)
        if hit:
            axis, w0, w1 = hit
            c.asset_id = axis.asset_id
            c.start = axis.word_start_s(w0)
            c.end = float(axis.words[w1].get("end") or 0)

    for e in understanding.emphasis_words:
        hit = _locate(axes, e.word, e.approx_start)
        if hit:
            axis, w0, _ = hit
            e.asset_id, e.start = axis.asset_id, axis.word_start_s(w0)

    for q in understanding.quotable_lines:
        q.self_contained = self_contained(q.text)
        hit = _locate(axes, q.text, q.approx_start)
        if hit:
            axis, w0, w1 = hit
            q.asset_id = axis.asset_id
            q.start = axis.word_start_s(w0)
            q.end = float(axis.words[w1].get("end") or 0)

    resolved_hints: list[tuple[Any, _Axis, int]] = []
    for h in understanding.narrative_role_hints:
        hit = _locate(axes, h.marker, h.approx_start)
        if hit:
            axis, w0, _ = hit
            h.asset_id, h.start = axis.asset_id, axis.word_start_s(w0)
            resolved_hints.append((h, axis, w0))
    _chain_ends(resolved_hints)

    for v in understanding.visual_anchors:
        m = re.fullmatch(r"image\s+(\d+)", v.ref.strip().lower())
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(image_refs):
                v.asset_id = image_refs[idx]["asset_id"]

    return understanding


def _block_label(asset) -> str:
    kind = asset.type.value if isinstance(asset.type, AssetType) else str(asset.type)
    title = (asset.title or "").strip()
    return f"{kind} · {title}" if title else kind


def build_source_blocks(assets: list) -> list[dict[str, Any]]:
    """Per-asset prompt blocks: anchored cue lines when the asset carries an
    ASR word axis (video/audio), the raw text otherwise. Aligned with the
    digest texts (same ``extracted_text or transcript`` selection rule)."""
    # Deferred: the tools door (app.tools.__init__) imports node_runners,
    # which imports this module — a top-level edge would cycle.
    from app.tools.clips.transcript import build_anchored_transcript

    blocks: list[dict[str, Any]] = []
    for asset in assets:
        text = (asset.extracted_text or asset.transcript) or ""
        if not text.strip():
            continue
        words = (asset.meta or {}).get("words") or []
        anchored = build_anchored_transcript(words) if words else ""
        blocks.append(
            {
                "label": _block_label(asset),
                "text": anchored or text,
                "timed": bool(anchored),
            }
        )
    return blocks


def word_axis_from_assets(assets: list) -> list[dict[str, Any]]:
    """The word axes the beat-map resolver snaps onto (per AV asset)."""
    return [
        {"asset_id": str(a.id), "words": (a.meta or {}).get("words") or []}
        for a in assets
        if (a.meta or {}).get("words")
    ]


def image_refs_from_assets(assets: list) -> list[dict[str, str]]:
    """"image N" refs in the order collect_asset_media feeds plain images
    (the visual_anchors' semantic-half join key)."""
    refs: list[dict[str, str]] = []
    for a in assets:
        if a.type == AssetType.IMAGE and a.file_url:
            refs.append({"ref": f"image {len(refs) + 1}", "asset_id": str(a.id)})
    return refs
