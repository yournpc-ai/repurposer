"""Rendered-diff proof for the prompts.py → j2 refactor (ADR-071, 2026-09-11).

Compares the pre-refactor module (scratch/prompts_before_split.py, snapshotted
before the rewrite) against the live app.chat.prompts.

- Step 1 (mechanical split): both functions must report BYTE-IDENTICAL.
- Step 2 (rule diet + dedup): the printed unified diff IS the review
  artifact — every hunk must map to the approved diet list.

Run:
    cd apps/api && uv run python ../../scratch/prompt_split_diff.py
"""

import difflib
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

SNAPSHOT = REPO / "scratch" / "prompts_before_split.py"

old = types.ModuleType("prompts_before_split")
old.__dict__["__file__"] = str(SNAPSHOT)
exec(compile(SNAPSHOT.read_text(), str(SNAPSHOT), "exec"), old.__dict__)

from app.chat import prompts as new  # noqa: E402

failed = False
for name in ("intent_router_system", "chat_intent_system"):
    before = getattr(old, name)()
    after = getattr(new, name)()
    if before == after:
        print(f"{name}: BYTE-IDENTICAL ({len(after)} chars)")
        continue
    failed = True
    print(f"{name}: CHANGED (old={len(before)} chars, new={len(after)} chars)")
    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"before/{name}",
        tofile=f"after/{name}",
        lineterm="",
    )
    print("\n".join(diff))
    print()

sys.exit(1 if failed else 0)
