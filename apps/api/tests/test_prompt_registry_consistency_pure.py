"""Registry ↔ prompt enumeration consistency (ADR-071 挂账 alarm).

Pure-function coverage only (suite discipline: no DB, no LLM, no HTTP).
The no-material block's hardcoded tool enumerations are prompt prose the
registry cannot project (the block's structure is probe-proven load-bearing
— ADR-071 判词③/⑥, never diet it). Instead of deriving the prose FROM the
registry, this suite is the drift alarm: the day a tool's ``requires``
changes or a new tool lands without the prose following, it goes red here.

- media-needing set (MEDIA ∪ TRANSCRIPT requirements) == the block's
  "Media-needing tasks" enumeration;
- every remaining non-seat generation tool with empty requires == the
  "Copy-writer tasks" enumeration;
- every tool name enumerated anywhere in the two chat system templates is
  a registered (non-seat) tool — typos and stale names surface here.
"""

import re
from pathlib import Path

from app.pipeline.graph import NODE_KINDS
from app.tools import TOOL_REGISTRY

_PROMPTS = Path(__file__).resolve().parents[1] / "app" / "prompts" / "chat"


def _enumerated(template: str, label: str) -> set[str]:
    match = re.search(rf"{re.escape(label)} \(([^)]*)\)", template)
    assert match, f"'{label} (...)' enumeration not found in the template"
    return {name.strip() for name in match.group(1).split("/")}


def _expected_media_needing() -> set[str]:
    """Tools that need an uploaded media FILE — the registry's own flag
    (``ToolEntry.needs_media_file``), never derived from node ``requires``:
    align_stills requires a TRANSCRIPT yet serves the NO-recording case, so
    requirement membership is not this axis."""
    return {
        name
        for name, entry in TOOL_REGISTRY.items()
        if not entry.seat and entry.needs_media_file
    }


def _expected_writers() -> set[str]:
    """Fresh-chain copy writers: produce outputs, need nothing, no media
    file. revise_script is excluded by design — it targets an EXISTING
    output and never rides a fresh chain (the book path's catalog excludes
    it, prompts.py), so the no-material block never enumerates it."""
    return {
        name
        for name, entry in TOOL_REGISTRY.items()
        if not entry.seat
        and not entry.needs_media_file
        and name != "revise_script"
        and (node := NODE_KINDS.get(name)) is not None
        and not node.requires
        and node.produces_outputs
    }


class TestNoMaterialBlockMatchesRegistry:
    def test_media_needing_enumeration(self):
        block = (_PROMPTS / "_writers_no_material.j2").read_text()
        assert _enumerated(block, "Media-needing tasks") == _expected_media_needing()

    def test_copy_writer_enumeration(self):
        block = (_PROMPTS / "_writers_no_material.j2").read_text()
        assert _enumerated(block, "Copy-writer tasks") == _expected_writers()


class TestEnumeratedNamesAreRegistered:
    def test_all_enumerated_tools_exist(self):
        registered = {name for name, entry in TOOL_REGISTRY.items() if not entry.seat}
        for template_path in sorted(_PROMPTS.glob("*_system.j2")):
            text = template_path.read_text()
            enumerated = set()
            for match in re.finditer(r"\b((?:select_clips|translate_clip|dub_clip"
                                     r"|remove_filler|add_music|reframe_clip"
                                     r"|write_post|write_quotes|write_carousel"
                                     r"|write_article|revise_script|research_topic"
                                     r"|synthesize_talk_video)(?:\s*/\s*[a-z_]+)*)\b",
                                     text):
                enumerated.update(
                    name.strip() for name in match.group(1).split("/")
                )
            unknown = enumerated - registered
            assert not unknown, f"{template_path.name} enumerates unregistered: {unknown}"
