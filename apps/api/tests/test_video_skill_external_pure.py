"""External Skill import: untrusted bytes → reviewable draft, never execution."""
from __future__ import annotations

import pytest

from app.skills.external import ExternalSkillError, build_skill_draft

_ROOT = b"""---
name: video-shotcraft
description: Shot-card methods and implementation references.
allowed-tools: [Read, Bash]
---
Read the selected shot card and its exact implementation. Use page captures,
word-by-word timing and beat sync where the current capability allows it.
"""

_SHOT = b"""---
name: blur-slide
---
The title uses opacity, translateY(64px), blur(18px) and letterSpacing.
The reference implementation is demos/typography/blur-slide/BlurSlide.tsx.
"""

_IMPLEMENTATION = b"""import { useCurrentFrame } from 'remotion';
const words = 'Exact user copy'.split(' ');
const progress = frame / 22;
const style = { opacity: progress, transform: `translateY(${64 - progress}px)` };
"""

_CURRENT = {
    "animation:opacity",
    "animation:transform.position",
    "text:word-parts",
    "capture:web",
}


def _files() -> dict[str, bytes]:
    return {
        "SKILL.md": _ROOT,
        "references/shots/typography/blur-slide.md": _SHOT,
        "demos/typography/blur-slide/BlurSlide.tsx": _IMPLEMENTATION,
        "assets/scripts/sfx-source.py": b"raise RuntimeError('must never execute')\n",
        "gallery/media/poster/blur-slide.png": b"not-a-decoded-image",
    }


def test_shotcraft_sources_become_reviewable_draft_with_evidence_gaps():
    draft = build_skill_draft(_files(), declared_capabilities=_CURRENT)

    assert draft.name == "video-shotcraft"
    assert "Read the selected shot card" in draft.instructions
    by_path = {source.path: source for source in draft.references}
    assert by_path["assets/scripts/sfx-source.py"].role == "script"
    assert by_path["demos/typography/blur-slide/BlurSlide.tsx"].role == "implementation"
    assert by_path["references/shots/typography/blur-slide.md"].role == "reference"
    assert by_path["assets/scripts/sfx-source.py"].text.startswith("raise RuntimeError")

    report = draft.capability_report
    assert report.supported == [
        "animation:opacity",
        "animation:transform.position",
        "capture:web",
        "text:word-parts",
    ]
    gaps = {gap.capability: gap.source_paths for gap in report.gaps}
    assert "runtime:remotion-source" in gaps
    assert "animation:blur" in gaps
    assert "animation:letter-spacing" in gaps
    assert gaps["animation:blur"] == ["references/shots/typography/blur-slide.md"]
    assert report.rejected_files == {
        "gallery/media/poster/blur-slide.png": "unsupported_source_type"
    }


def test_scripts_and_allowed_tools_are_dependencies_not_permissions():
    draft = build_skill_draft(_files(), declared_capabilities=_CURRENT)

    dependencies = {
        (item.kind, item.name): item.source_paths
        for item in draft.capability_report.unauthorized_dependencies
    }
    assert dependencies == {
        ("allowed_tool", "Read"): ["SKILL.md"],
        ("allowed_tool", "Bash"): ["SKILL.md"],
        ("script", "assets/scripts/sfx-source.py"): ["assets/scripts/sfx-source.py"],
    }
    assert "script:external" not in {gap.capability for gap in draft.capability_report.gaps}


def test_source_hash_is_order_independent_and_exact_source_sensitive():
    files = _files()
    first = build_skill_draft(files, declared_capabilities=_CURRENT)
    second = build_skill_draft(dict(reversed(list(files.items()))), declared_capabilities=_CURRENT)
    assert first.source_hash == second.source_hash

    changed = {**files, "references/shots/typography/blur-slide.md": _SHOT + b"hold\n"}
    changed_draft = build_skill_draft(changed, declared_capabilities=_CURRENT)
    assert changed_draft.source_hash != first.source_hash

    pinned = build_skill_draft(
        files,
        declared_capabilities=_CURRENT,
        source_uri="https://github.com/Vincentwei1021/video-shotcraft",
        source_revision="1266a3ec4831289c4d893d42dd5102723658039a",
    )
    assert pinned.source_revision == "1266a3ec4831289c4d893d42dd5102723658039a"
    assert pinned.source_hash == first.source_hash


@pytest.mark.parametrize(
    "path",
    ["../SKILL.md", "/SKILL.md", ".git/SKILL.md", "a/./b.md", "a//b.md", "a\\b.md"],
)
def test_unsafe_paths_fail_closed(path: str):
    with pytest.raises(ExternalSkillError, match="path"):
        build_skill_draft({path: _ROOT}, declared_capabilities=_CURRENT)


def test_invalid_text_and_missing_root_fail_closed():
    with pytest.raises(ExternalSkillError, match="UTF-8"):
        build_skill_draft(
            {"SKILL.md": _ROOT, "references/bad.md": b"\xff"},
            declared_capabilities=_CURRENT,
        )
    with pytest.raises(ExternalSkillError, match="root SKILL.md"):
        build_skill_draft(
            {"references/only.md": b"instructions"},
            declared_capabilities=_CURRENT,
        )


def test_frontmatter_cannot_silently_add_unknown_contract_fields():
    root = _ROOT.replace(b"allowed-tools: [Read, Bash]", b"permissions: [admin]")
    with pytest.raises(ExternalSkillError, match="frontmatter keys"):
        build_skill_draft({"SKILL.md": root}, declared_capabilities=_CURRENT)
