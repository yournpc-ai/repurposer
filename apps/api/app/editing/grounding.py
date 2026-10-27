"""Citation / fact grounding and camera focus for the video design chain
(VIDEO_PROJECT §8.3 — the validator seat for creative answers).

The director cites manifest lines by index and names camera targets by
element id; CODE resolves both against the bound snapshot's manifest. A
citation that does not resolve, or a focus id absent from the assigned
view's inventory, is a repairable violation — never a silent substitution.

Pure: snapshot manifests arrive as plain dicts (``kind``/``text`` lines and
per-view element inventories); no DB, no storage IO.
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CiteLine(BaseModel):
    """One factual slot's citation: the manifest line index the text comes
    from. The model's natural spellings (a bare ``3`` / ``"L3"`` /
    ``{"id": "L3"}`` / ``{"text": ..., "citation": "L3"}``) fold into the
    canonical form — genuinely malformed input stays a pydantic rejection.
    A ``text`` echo riding next to the citation is dropped: the manifest
    line is the text's only source of truth, never the model's restatement.
    """

    model_config = ConfigDict(extra="forbid")

    line: int = Field(ge=1, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _fold(cls, data: Any) -> Any:
        if isinstance(data, bool):
            return data
        if isinstance(data, int):
            return {"line": data}
        if isinstance(data, str):
            m = re.fullmatch(r"[Ll]?(\d+)", data.strip())
            return {"line": int(m.group(1))} if m else data
        if isinstance(data, dict) and "line" not in data:
            ref = data.get("id", data.get("citation"))
            if isinstance(ref, int) and not isinstance(ref, bool):
                return {"line": ref}
            if isinstance(ref, str):
                m = re.fullmatch(r"[Ll]?(\d+)", ref.strip())
                if m:
                    return {"line": int(m.group(1))}
        return data

    @classmethod
    def model_validate_natural(cls, data: Any) -> "CiteLine":
        return cls.model_validate(cls._fold(data))


@dataclass(frozen=True)
class ManifestLine:
    """One groundable line of a bound web snapshot (built snapshot-side from
    the capture's research manifest)."""

    index: int  # 1-based, the citation's address
    kind: str  # title / description / h1 / h2 / h3 / button / link / paragraph
    text: str
    page: int  # which bound snapshot (0-based, bind order)


def manifest_lines(sources: list[dict[str, Any]]) -> list[ManifestLine]:
    """Flatten the bound web snapshots' research lines into one numbered
    manifest (bind order = page order). Each web snapshot's meta carries
    ``lines`` (kind/text) frozen at snapshot time."""
    out: list[ManifestLine] = []
    for page, meta in enumerate(sources):
        for line in meta.get("lines") or []:
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            out.append(
                ManifestLine(
                    index=len(out) + 1,
                    kind=str(line.get("kind") or "paragraph"),
                    text=text,
                    page=page,
                )
            )
    return out


def resolve_citation(lines: list[ManifestLine], ref: CiteLine) -> str:
    """Resolve one citation to its exact source text; raise naming the miss."""
    for line in lines:
        if line.index == ref.line:
            return line.text
    raise ValueError(f"line L{ref.line} does not exist in the page manifest")


# Edge characters no on-screen slot may begin or end with (dangling
# connectors a head/tail fit can leave behind). Sentence enders stay;
# interior hyphens are never touched; a LEADING "-" can be a minus sign.
_EDGE_LEAD_CONNECTORS = "—–:;,·•|/"
_EDGE_TRAIL_CONNECTORS = "—–-:;,·•|/"
_SENTENCE_END = re.compile(r"[.!?。！？…]+[\")\]}»」』]*")


def strip_edge_connectors(text: str) -> str:
    t = text.strip().lstrip(_EDGE_LEAD_CONNECTORS).lstrip()
    return t.rstrip(_EDGE_TRAIL_CONNECTORS).rstrip()


def fit_to_cap(text: str, cap: int, fit: str) -> str:
    """Apply a slot's fit to its character cap. ``full`` returns as-is (an
    over-cap line then surfaces as a violation upstream). ``head`` prefers
    the last complete sentence inside the window, then a word boundary;
    ``tail`` trims at a word boundary (CJK and single-word lines hard-cut).
    """
    text = text.strip()
    if len(text) <= cap or fit == "full":
        return text
    if fit == "head":
        cut = text[:cap]
        enders = list(_SENTENCE_END.finditer(cut))
        if enders and enders[-1].end() >= cap * 0.4:
            return cut[: enders[-1].end()].strip()
        sp = cut.rfind(" ")
        return (cut[:sp] if sp > 0 else cut).strip()
    cut = text[-cap:]
    sp = cut.find(" ")
    return (cut[sp + 1 :] if 0 < sp < len(cut) - 1 else cut).strip()


# A plate card carries a number — the line's first token leads with one.
_NUMBERISH = re.compile(r"^\s*\S*\d")


def detect_plate_cards(lines: list[ManifestLine], *, limit: int = 3) -> list[dict[str, Any]]:
    """Code-detected numbers evidence: number-led manifest lines split into
    big/label cards (``40`` / ``apps a month``). Fewer than two clean cards
    is no plate. Cards carry their source page so the plate hangs off the
    chapter that proved the numbers."""
    cards: list[dict[str, str]] = []
    for line in lines:
        text = line.text.strip()
        if not _NUMBERISH.match(text) or len(text) > 40:
            continue
        parts = text.split(None, 1)
        if len(parts) != 2 or not any(ch.isdigit() for ch in parts[0]):
            continue
        big, label = parts[0].strip(), strip_edge_connectors(parts[1].strip(" —-·"))
        if not big or not label:
            continue
        cards.append({"big": big[:12], "label": fit_to_cap(label, 30, "head"), "page": line.page})
        if len(cards) >= limit:
            break
    return cards if len(cards) >= 2 else []


# Camera default preference: the view's DOMINANT CONTENT first — display
# headline, then media, then the largest copy block; controls last.
_FOCUS_KINDS = ("heading", "video", "image", "text", "button")


def pick_focus(elements: list[dict[str, Any]]) -> str | None:
    """One default camera target for a view: the best uncovered element by
    kind preference then area. None = no inventory (the raw center push-in
    is the fallback the camera math owns)."""
    candidates = [e for e in elements if not e.get("covered")]
    for kind in _FOCUS_KINDS:
        pool = [e for e in candidates if e.get("kind") == kind]
        if pool:
            return str(max(pool, key=lambda e: float(e.get("w", 0)) * float(e.get("h", 0)))["id"])
    if candidates:
        return str(max(candidates, key=lambda e: float(e.get("w", 0)) * float(e.get("h", 0)))["id"])
    return None


def _visible_part(element: dict[str, Any]) -> dict[str, float] | None:
    """Intersect an element's normalized rect with the view ([0,1]²).

    Viewport-cropped captures legitimately carry elements that extend past
    the fold (x/w or y/h beyond 1); only the visible part is a lawful camera
    target. None = entirely outside the captured view.
    """
    x0 = max(0.0, float(element["x"]))
    y0 = max(0.0, float(element["y"]))
    x1 = min(1.0, float(element["x"]) + float(element["w"]))
    y1 = min(1.0, float(element["y"]) + float(element["h"]))
    if x1 <= x0 or y1 <= y0:
        return None
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def resolve_focus(
    elements: list[dict[str, Any]], override_id: str | None
) -> dict[str, float] | None:
    """Resolve the director's element-id override (or the default pick) to
    the element's normalized center/extent, measured on its VISIBLE part.
    None = center push-in fallback.
    An override naming an absent, covered, or fully off-view element is a
    violation."""
    if override_id:
        element = next((e for e in elements if str(e.get("id")) == override_id), None)
        if element is None:
            raise ValueError(f"element {override_id!r} is not in this view's inventory")
        if element.get("covered"):
            raise ValueError(f"element {override_id!r} is covered at capture time")
    else:
        picked = pick_focus(elements)
        if picked is None:
            return None
        element = next(e for e in elements if str(e.get("id")) == picked)
    visible = _visible_part(element)
    if visible is None:
        if override_id:
            raise ValueError(f"element {override_id!r} is outside the captured view")
        return None
    return {
        "cx": visible["x"] + visible["w"] / 2,
        "cy": visible["y"] + visible["h"] / 2,
        "w": visible["w"],
        "h": visible["h"],
    }


def camera_keyframes(
    focus: dict[str, float] | None,
    *,
    view_width: int,
    view_height: int,
    canvas_width: int,
    canvas_height: int,
    clip_ticks: int,
    arrival_frac: float,
    start_scale: float = 1.08,
) -> tuple[float, list[tuple[int, tuple[float, float]]]]:
    """One walk's camera: (final zoom, position keyframes in clip-local
    ticks). The arrival pushes to the focus element's center; the approach
    starts from a wide slightly-offset frame. Origin-center transform law:
    translate happens in scaled space (renderer: translate then scale around
    the box center), so the centering offset is −(p − c)·z.

    The view image covers the canvas box (objectFit cover): image pixels map
    to box points through the cover scale, centered.
    """
    fit = max(canvas_width / view_width, canvas_height / view_height)
    if focus is None:
        focus = {"cx": 0.5, "cy": 0.45, "w": 0.6, "h": 0.5}
    zoom = min(max(0.55 / max(focus["w"], focus["h"], 0.05), 1.25), 2.0)
    # Element center in image pixels → box (canvas) pixels.
    px = (focus["cx"] * view_width - view_width / 2) * fit + canvas_width / 2
    py = (focus["cy"] * view_height - view_height / 2) * fit + canvas_height / 2
    tx = -(px - canvas_width / 2) * zoom
    ty = -(py - canvas_height / 2) * zoom
    # Coverage is a hard law, centering is soft: the zoomed image must still
    # cover the canvas, so the translate is fenced to the cover slack on each
    # axis (an edge/near-fold focus would otherwise push the image off-frame
    # and expose black).
    # object-fit crops inside the canvas-sized Img box BEFORE its parent
    # transform. Extra source-image pixels cannot cover a translated box.
    # Round the zoom first, matching the actual emitted scale exactly.
    zoom = round(zoom, 3)

    def covered(x: float, y: float, scale: float) -> tuple[float, float]:
        slack_x = math.floor(max((scale - 1) * canvas_width / 2, 0.0) * 10) / 10
        slack_y = math.floor(max((scale - 1) * canvas_height / 2, 0.0) * 10) / 10
        return (min(max(round(x, 1), -slack_x), slack_x),
                min(max(round(y, 1), -slack_y), slack_y))

    tx, ty = covered(tx, ty, zoom)
    arrival = int(clip_ticks * arrival_frac)
    approach = covered(tx * 0.15 - 24, ty * 0.15 + 12, start_scale)
    keyframes: list[tuple[int, tuple[float, float]]] = [
        (0, approach),
        (arrival, (tx, ty)),
        (clip_ticks, covered(tx * 1.02, ty * 1.02, round(min(zoom * 1.01, 2.05), 3))),
    ]
    return round(zoom, 3), keyframes
