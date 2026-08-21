"""Architecture gates (ADR-039). Run from apps/api/:

    uv run python scripts/check_gates.py

Gate 1 (N-29 iron rule, naming batch v2 ④/⑥ seat): ``app/providers/``
never imports the decision layer (``app.agents``; the retired ``app.clients``
stays banned as a reintroduction guard), and the deterministic tool packages
additionally never touch the LLM seam (``app.providers.llm``) — deterministic
means no LLM at all. The deterministic package set is registry-derived
(TOOL_REGISTRY behavior), never a hand-maintained list.

Gate 2 (P2 no-parallel-maps rule): every "type → X" fact derives from the
node classes / the tool registry. The retired parallel-map identifiers
(``_OUTPUT_TO_NODE_KIND`` and friends) and the retired ``pipeline/registry``
module must never reappear under ``app/``.

Gate 3 (P3 no-blind-retries rule): every retry carries structured feedback
and runs exactly one round (the Agent funnel's repair); the retired
blind-retry identifiers (``auto_retry`` / ``_with_retry``) must never
reappear under ``app/``. The client layer's tenacity (transport) and the
graph's step retry budget (``NodeBase.retries``) are not retries in this
sense.

Gate 4 (naming batch v2 retired identifiers): the renames of N-40/N-41/N-42
leave no shim — the retired identifiers (``SkillEntry`` / ``SkillRejected``
/ ``dispatchable_skills`` / ``checkpoint``; imports of ``app.clients`` or
``app.agents.roster``) must never reappear under ``app/``, and
``agents/roster.py`` must never come back as a file. ``app.skills`` is NOT
banned — it is the instruction-pack home (N-42 指令包, industry meaning);
``roster`` as plain prose (the AGENTS roster) stays legitimate.
"""

import re
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))  # the purity gate reads the registries
APP_DIR = API_ROOT / "app"
PROVIDERS_DIR = APP_DIR / "providers"

# Module-level or deferred — an import is an import wherever it sits.
BANNED_DECISION_IMPORT = re.compile(r"^\s*(from|import)\s+app\.(agents|clients)\b")
BANNED_LLM_IMPORT = re.compile(r"^\s*(from|import)\s+app\.(agents|clients|providers\.llm)\b")

# P2 retired identifiers: the parallel maps these named now derive from
# ``pipeline/graph.py`` (NODE_KINDS) or ``app/tools/__init__.py``
# (TOOL_REGISTRY). A hit means someone reintroduced a second source.
BANNED_PARALLEL_MAPS = re.compile(
    r"_OUTPUT_TO_NODE_KIND"
    r"|_SKILL_TO_OUTPUT"
    r"|_TOOL_TO_OUTPUT"  # the new-vocabulary twin — same reintroduction
    r"|_SLOT_ORDER"
    r"|_SLOT_TYPE_LABEL"
    r"|\bKNOWN_OUTPUTS\b"
    r"|\bSLOT_COUNT_LIMITS\b"
    r"|\bSLOT_DEFAULT_COUNT\b"
    r"|\bSTEP_RUNNERS\b"
    r"|\bretries_for_node_kind\b"
    r"|app\.pipeline\.registry"
)

# P3 retired identifiers: the blind retries these named were replaced by the
# Agent funnel's one bounded repair round (structured echo). A hit means
# someone reintroduced a retry without feedback.
BANNED_BLIND_RETRY = re.compile(r"auto_retry|_with_retry")

# Naming batch v2 retired identifiers (N-40/N-41/N-42): the renames left no
# shim, so a hit is always a reintroduction. ``checkpoint`` is matched
# case-insensitively (kind string AND prose); ``app.skills`` is deliberately
# absent — it is the live instruction-pack home.
BANNED_RETIRED_IDENTIFIERS = re.compile(
    r"\bSkillEntry\b"
    r"|\bSkillRejected\b"
    r"|\bdispatchable_skills\b"
    r"|\bcheckpoint\b"
    r"|^\s*(from|import)\s+app\.clients\b"
    r"|^\s*(from|import)\s+app\.agents\.roster\b",
    re.IGNORECASE,
)


def _deterministic_package_dirs() -> list[Path]:
    """The deterministic tool packages' directories, registry-derived (N-29 ④):
    TOOL_REGISTRY entries whose behavior is deterministic → their node class's
    package. Importing the door is safe here (this script runs interpreter-side,
    never inside the app import graph)."""
    from app.pipeline.graph import NODE_KINDS
    from app.tools import TOOL_REGISTRY

    dirs = set()
    for entry in TOOL_REGISTRY.values():
        if entry.behavior != "deterministic":
            continue
        node = NODE_KINDS.get(entry.name)
        if node is None:
            continue
        mod = sys.modules.get(node.__module__)
        if mod is not None and mod.__file__:
            dirs.add(Path(mod.__file__).parent)
    return sorted(dirs)


def check_purity() -> list[str]:
    # (path, banned-pattern): providers/ never imports the decision layer;
    # deterministic packages never import the decision layer NOR the LLM seam.
    targets: list[tuple[Path, re.Pattern]] = [
        (path, BANNED_DECISION_IMPORT) for path in sorted(PROVIDERS_DIR.rglob("*.py"))
    ]
    for pkg in _deterministic_package_dirs():
        targets.extend((path, BANNED_LLM_IMPORT) for path in sorted(pkg.rglob("*.py")))
    violations: list[str] = []
    for path, pattern in targets:
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.match(line):
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


def check_blind_retries() -> list[str]:
    violations: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if BANNED_BLIND_RETRY.search(line):
                rel = path.relative_to(API_ROOT)
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    return violations


def check_retired_identifiers() -> list[str]:
    violations: list[str] = []
    roster_py = APP_DIR / "agents" / "roster.py"
    if roster_py.exists():
        violations.append("app/agents/roster.py: file resurrected (N-41: it is registry.py)")
    for path in sorted(APP_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if BANNED_RETIRED_IDENTIFIERS.search(line):
                rel = path.relative_to(API_ROOT)
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    return violations


def main() -> int:
    failures = check_purity()
    if failures:
        print("purity gate FAILED (N-29: providers/ never imports the decision layer; deterministic packages never touch the LLM seam):")
        for failure in failures:
            print(f"  {failure}")
    parallel = check_parallel_maps()
    if parallel:
        print("parallel-map gate FAILED (P2: derive from NODE_KINDS / TOOL_REGISTRY):")
        for failure in parallel:
            print(f"  {failure}")
    blind = check_blind_retries()
    if blind:
        print("blind-retry gate FAILED (P3: one bounded repair round, with feedback):")
        for failure in blind:
            print(f"  {failure}")
    retired = check_retired_identifiers()
    if retired:
        print("retired-identifier gate FAILED (naming batch v2: no shim, no reintroduction):")
        for failure in retired:
            print(f"  {failure}")
    if failures or parallel or blind or retired:
        return 1
    print("check_gates: OK (providers/+deterministic purity, no parallel maps, no blind retries, no retired identifiers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
