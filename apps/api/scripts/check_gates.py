"""Architecture gates (ADR-039). Run from apps/api/:

    uv run python scripts/check_gates.py

Gate 1 (N-29 tools/ iron rule): ``app/tools/`` is the pure-mechanical layer —
no agent declarations, no LLM client. Any ``app.agents`` / ``app.clients``
import under tools/ fails the build.

Gate 2 (P2 no-parallel-maps rule): every "type → X" fact derives from the
node classes / the skill registry. The retired parallel-map identifiers
(``_OUTPUT_TO_NODE_KIND`` and friends) and the retired ``pipeline/registry``
module must never reappear under ``app/``.
"""

import re
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = API_ROOT / "app"
TOOLS_DIR = APP_DIR / "tools"

# Module-level or deferred — an import is an import wherever it sits.
BANNED_TOOLS_IMPORT = re.compile(r"^\s*(from|import)\s+app\.(agents|clients)\b")

# P2 retired identifiers: the parallel maps these named now derive from
# ``pipeline/graph.py`` (NODE_KINDS) or ``app/skills/__init__.py``
# (SKILL_REGISTRY). A hit means someone reintroduced a second source.
BANNED_PARALLEL_MAPS = re.compile(
    r"_OUTPUT_TO_NODE_KIND"
    r"|_SKILL_TO_OUTPUT"
    r"|_SLOT_ORDER"
    r"|_SLOT_TYPE_LABEL"
    r"|\bKNOWN_OUTPUTS\b"
    r"|\bSLOT_COUNT_LIMITS\b"
    r"|\bSLOT_DEFAULT_COUNT\b"
    r"|\bSTEP_RUNNERS\b"
    r"|\bretries_for_node_kind\b"
    r"|app\.pipeline\.registry"
)


def check_tools_purity() -> list[str]:
    violations: list[str] = []
    for path in sorted(TOOLS_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if BANNED_TOOLS_IMPORT.match(line):
                rel = path.relative_to(API_ROOT)
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    return violations


def check_parallel_maps() -> list[str]:
    violations: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if BANNED_PARALLEL_MAPS.search(line):
                rel = path.relative_to(API_ROOT)
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    return violations


def main() -> int:
    failures = check_tools_purity()
    if failures:
        print("tools/ purity gate FAILED (N-29: no app.agents / app.clients imports):")
        for failure in failures:
            print(f"  {failure}")
    parallel = check_parallel_maps()
    if parallel:
        print("parallel-map gate FAILED (P2: derive from NODE_KINDS / SKILL_REGISTRY):")
        for failure in parallel:
            print(f"  {failure}")
    if failures or parallel:
        return 1
    print("check_gates: OK (tools/ purity, no parallel maps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
