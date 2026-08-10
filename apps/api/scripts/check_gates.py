"""Architecture gates (ADR-039 P1). Run from apps/api/:

    uv run python scripts/check_gates.py

Gate 1 (N-29 tools/ iron rule): ``app/tools/`` is the pure-mechanical layer —
no agent declarations, no LLM client. Any ``app.agents`` / ``app.clients``
import under tools/ fails the build.
"""

import re
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = API_ROOT / "app" / "tools"

# Module-level or deferred — an import is an import wherever it sits.
BANNED = re.compile(r"^\s*(from|import)\s+app\.(agents|clients)\b")


def check_tools_purity() -> list[str]:
    violations: list[str] = []
    for path in sorted(TOOLS_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if BANNED.match(line):
                rel = path.relative_to(API_ROOT)
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    return violations


def main() -> int:
    failures = check_tools_purity()
    if failures:
        print("tools/ purity gate FAILED (N-29: no app.agents / app.clients imports):")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("check_gates: OK (tools/ purity)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
