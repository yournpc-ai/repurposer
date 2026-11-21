"""Format skill instructions and compact Output labels."""

from typing import Any

from app.skills import SKILL_REGISTRY


def pack_instructions(packs: list[str]) -> str:
    """Weave an agent declaration's skill packs into one instructions block
    (N-42 指令包: assembly-time injection — the model never decides when a
    pack loads). Unknown names raise KeyError at weave time; the startup
    self-check resolves every declared pack first, so this never fires
    mid-run. Bodies join on a blank line so stacked packs (persona-level
    loaders, later batch) keep their markdown sections separated; a single
    pack renders byte-identical to its bare body."""
    return "\n".join(SKILL_REGISTRY[name].body for name in packs)


def output_one_liner(output: Any) -> str:
    """A one-line label for a visible output (type + first creative line)."""
    payload = output.payload or {}
    for key in ("hook", "title", "body"):
        text = payload.get(key)
        if text:
            return str(text).split("\n", 1)[0][:80]
    return ""
