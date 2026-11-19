"""Ground DOI text authored for website illustrations in the frozen source or user copy."""

from __future__ import annotations

import re
from collections.abc import Iterable
from uuid import UUID
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import BriefSlotSource, CreativeState
from app.models.tables import SourceSnapshot
from app.tools.video.preparation import frozen_source_lines
from app.tools.video.visual_assets import (
    ControlledSVGSource,
    SceneAssetSpec,
    VisualAssetError,
    sanitize_svg_program,
)

_DOI = re.compile(r"(?<![a-zA-Z0-9])10\.\d{4,9}/[^\s\"“”，。；、…]*")


def _token(text: str) -> str:
    token = text.casefold().rstrip(".,;:!?")
    for left, right in (("(", ")"), ("[", "]")):
        excess = min(token.count(right) - token.count(left), len(token) - len(token.rstrip(right)))
        if excess > 0:
            token = token[:-excess]
    return token


def _svg_copy(spec: SceneAssetSpec) -> str:
    if not isinstance(spec.source, ControlledSVGSource):
        return ""
    # Avoid parsing unrelated illustrations. Entity references and tspans can
    # spell a visible identifier across multiple XML nodes.
    if not any(part in spec.source.program for part in ("10.", "&#", "tspan")):
        return ""
    svg, _, _ = sanitize_svg_program(spec.source.program, spec.output)
    copy: list[str] = []

    def visit(node: ET.Element, in_text: bool = False, visible: bool = True) -> None:
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "defs" or node.get("display") == "none" or re.fullmatch(
            r"0+(?:\.0+)?%?", node.get("opacity", "")
        ):
            return
        visibility = node.get("visibility")
        if visibility in {"hidden", "collapse", "visible"}:
            visible = visibility == "visible"
        if tag == "text":
            in_text = True
            copy.append("\n")
        if in_text and visible:
            copy.append(node.text or "")
        for child in node:
            visit(child, in_text, visible)
            if in_text and visible:
                copy.append(child.tail or "")

    visit(ET.fromstring(svg))
    return "".join(copy)


def _unverified_doi(copy: str, trusted: set[str]) -> str | None:
    for match in _DOI.finditer(copy):
        displayed = match[0].casefold()
        # Wrapped identifiers may occupy several SVG text rows. Accept the
        # reconstruction only if it reaches the end of an entire source DOI.
        remaining = copy[match.end():]
        while _token(displayed) not in trusted:
            if not any(doi.startswith(displayed) for doi in trusted):
                return match[0]
            continuation = re.match(r"[ \t]*\n\s*(\S+)", remaining)
            if continuation is None:
                return match[0]
            displayed += continuation[1].casefold()
            remaining = remaining[continuation.end():]
    return None


async def validate_website_scene_citations(
    db: AsyncSession, *, owner_id: UUID, state: CreativeState, specs: list[SceneAssetSpec],
    user_text: str, source_ids: Iterable[UUID],
) -> None:
    if state.brand_profile is None:
        return
    claims = [(spec.scene_id, _svg_copy(spec)) for spec in specs]
    if not any(_DOI.search(copy) for _, copy in claims):
        return
    evidence = [user_text]
    if state.brief.must_include.source == BriefSlotSource.USER_STATED:
        evidence.extend(state.brief.must_include.value or [])
    evidence.extend(
        item.value for item in state.brief.constraints
        if item.source == BriefSlotSource.USER_STATED and item.value
    )
    pinned = {UUID(ref.snapshot_id): ref.digest for ref in state.brand_profile.source_refs}
    snapshots = await db.scalars(select(SourceSnapshot).where(
        SourceSnapshot.id.in_(set(source_ids) | pinned.keys()), SourceSnapshot.owner_id == owner_id,
        SourceSnapshot.kind == "web",
    ))
    for snapshot in snapshots:
        if snapshot.id in pinned and snapshot.digest != pinned[snapshot.id]:
            continue
        meta = snapshot.meta or {}
        evidence.append(meta.get("canonical_url") or "")
        entries = frozen_source_lines(snapshot)
        for view in meta.get("views") or []:
            entries.extend(view.get("elements") or [])
        for entry in entries:
            evidence.extend(entry[key] for key in ("text", "href") if isinstance(entry.get(key), str))
    trusted = {
        _token(match[0]) for source in evidence for match in _DOI.finditer(source)
        if not match[0].endswith("/")
    }
    issues = []
    for scene_id, copy in claims:
        if missing := _unverified_doi(copy, trusted):
            issues.append(f"{scene_id} ({missing[:120]})")
    if issues:
        raise VisualAssetError(
            "Displayed DOI has no full match in the supplied sources: " + ", ".join(issues)
            + ". For all citations in those scenes, reflow exact sourced identifiers or "
            "illustrate the reference with a plain label such as ‘Source paper’."
        )
