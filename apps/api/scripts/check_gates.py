"""Architecture gates (ADR-039). Run from apps/api/:

    uv run python scripts/check_gates.py

Gate 0 (boot smoke): ``import app.main`` must succeed in a clean subprocess.
A boot-level break (e.g. a module-scope forward reference) otherwise kills
the pytest suite at COLLECTION — every test red with zero signal, and the
registry-reading gates below crash mid-check with a stack, not a verdict.

Gate 1 (N-29 iron rule, naming batch v2 ④/⑥ seat): ``app/providers/``
never imports the decision layer (``app.agents``; the retired ``app.clients``
stays banned as a reintroduction guard), and the deterministic tool packages
additionally never touch the LLM seam (``app.providers.llm``) — deterministic
means no LLM at all. The deterministic package set is registry-derived
(TOOL_REGISTRY behavior), never a hand-maintained list; a MIXED-behavior
package narrows the scan to the deterministic tool's own module (N-56 —
the law binds the tool, not its neighbor).

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
/ ``dispatchable_skills``; the retired node KIND ``checkpoint`` as a
kind-string; imports of ``app.clients`` or ``app.agents.roster``) must
never reappear under ``app/``, and ``agents/roster.py`` must never come
back as a file. The WORD ``checkpoint`` is no longer banned bare: ADR-085
re-claimed it for the Assistant Conversation channel. ``app.skills`` is NOT
banned — it is the instruction-pack home (N-42 指令包, industry meaning);
``roster`` as plain prose (the AGENTS roster) stays legitimate.

Gate 5 (ADR-087 dependency direction, Phase 2.5 — the three-way split made
grep-provable):
  5a 内核边界（U1 frozen）: ``app/agents/tool_loop.py`` says WHAT HAPPENED
      only — typed LoopEvents out, never Activity construction vocabulary
      (projector/frame types, the SSE event name, the i18n key family),
      never Presentation/Domain imports (``app.chat`` / ``app.pipeline`` /
      ``app.models``). Docstring prose naming the boundary stays legal.
  5b Lifecycle Projection → Presentation: ``app/pipeline/lifecycle.py``
      never imports ``app.chat`` — Presentation consumes the projection,
      never the reverse.
  5c Client never INFERS lifecycle: in ``apps/web/src`` the server-named
      stamp (results/graph ``lifecycle.*``) is the only lifecycle read —
      ``hasDraftGraph``-style artifact-existence derivations (retired with
      Phase 1) and local planReady/confirmationReady/materialReady
      derivations that don't read the stamp must never reappear.
"""

import re
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_ROOT))  # the purity gate reads the registries
APP_DIR = API_ROOT / "app"
PROVIDERS_DIR = APP_DIR / "providers"

# ADR-087 dependency direction (gate 5).
KERNEL_FILE = APP_DIR / "agents" / "tool_loop.py"
LIFECYCLE_FILE = APP_DIR / "pipeline" / "lifecycle.py"
WEB_SRC = API_ROOT.parent / "web" / "src"

# Module-level or deferred — an import is an import wherever it sits.
BANNED_DECISION_IMPORT = re.compile(r"^\s*(from|import)\s+app\.(agents|clients)\b")

# 5a: the kernel never imports Presentation/Domain…
BANNED_KERNEL_IMPORT = re.compile(r"^\s*(from|import)\s+app\.(chat|pipeline|models)\b")
# …and never speaks the Activity channel's CONSTRUCTION vocabulary (the
# docstring's prose naming the boundary — "the Activity Projection's job" —
# is legal; these tokens are the projection's types / wire event / i18n
# family / kind·status constants, none of which may appear in the kernel).
BANNED_KERNEL_ACTIVITY_VOCAB = re.compile(
    r"\bActivityProjector\b"
    r"|\bActivityFrame\b"
    r"|assistant\.activity"
    r"|chat\.activity\."
    r"|\bKIND_(READ|DRAFT|RUN|REPAIR)\b"
    r"|\bSTATUS_(ACTIVE|COMPLETED|FAILED|CANCELLED)\b"
)
# 5b: the Lifecycle Projection never imports the Presentation layer.
BANNED_PRESENTATION_IMPORT = re.compile(r"^\s*(from|import)\s+app\.chat\b")
# 5c: the client never infers lifecycle — the retired derivation identifier
# (Phase 1 removed it; a hit is always a reintroduction, prose included —
# the same strictness gate 4 applies to retired identifiers)…
BANNED_CLIENT_LIFECYCLE_DERIVATION = re.compile(r"\bhasDraftGraph\b")
# …and local readiness locals whose RHS never touches the stamp (a legal
# alias like ``const planReady = lifecycle?.plan_ready ?? false`` reads the
# stamp and passes; deriving readiness from nodes/runs/outputs does not).
# ``confirmActive`` joined the name set with Phase 3 Batch B (裁定 1): the
# confirm beat's derived predicate is ``intentReady && isPlanReady(lifecycle)
# && !runAttached`` — a direct stamp read; any artifact/existence-derived
# reimplementation of the confirm beat must bite here.
BANNED_CLIENT_LIFECYCLE_LOCAL = re.compile(
    r"^\s*const\s+(planReady|confirmationReady|materialReady|confirmActive)\s*=\s*(?!.*\blifecycle\b)"
)

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
# shim, so a hit is always a reintroduction. The N-40 half is scoped to the
# retired NODE KIND (``kind="checkpoint"``): ADR-085 (2026-09-17) re-claimed
# the WORD ``checkpoint`` for the Assistant Conversation channel
# (``on_checkpoint`` hook / ``assistant.checkpoint`` SSE event /
# ``intent.type=checkpoint`` row) — that vocabulary is current and legal;
# what must never come back is the flow-control node kind. Bare-word
# matching was retired when the word gained a lawful sense (Phase 2.5
# adjudication: the ban outlived its contract).
BANNED_RETIRED_IDENTIFIERS = re.compile(
    r"\bSkillEntry\b"
    r"|\bSkillRejected\b"
    r"|\bdispatchable_skills\b"
    r"|kind\s*(?:=|==)\s*[\"']checkpoint[\"']"
    r"|^\s*(from|import)\s+app\.clients\b"
    r"|^\s*(from|import)\s+app\.agents\.roster\b",
    re.IGNORECASE,
)


def _deterministic_scan_targets() -> list[Path]:
    """The deterministic tools' scan set, registry-derived (N-29 ④):
    TOOL_REGISTRY entries whose behavior is deterministic → their node
    class's package. Whole-package scan when the package houses ONLY
    deterministic citizens; narrows to the tool's own module file in a
    MIXED-behavior package (N-56: cut_segments shares ``tools/clips`` with
    the probabilistic select_clips — the law binds the deterministic tool's
    code, not its neighbor's LLM seam). Importing the door is safe here
    (this script runs interpreter-side, never inside the app import
    graph)."""
    from app.pipeline.graph import NODE_KINDS
    from app.tools import TOOL_REGISTRY

    det_files: list[Path] = []
    dir_behaviors: dict[Path, set[str]] = {}
    for entry in TOOL_REGISTRY.values():
        node = NODE_KINDS.get(entry.name)
        if node is None:
            continue
        mod = sys.modules.get(node.__module__)
        if mod is None or not mod.__file__:
            continue
        file = Path(mod.__file__)
        dir_behaviors.setdefault(file.parent, set()).add(entry.behavior)
        if entry.behavior == "deterministic":
            det_files.append(file)
    targets: list[Path] = []
    whole_dirs: set[Path] = set()
    for file in det_files:
        pkg = file.parent
        if dir_behaviors.get(pkg) == {"deterministic"}:
            if pkg not in whole_dirs:
                whole_dirs.add(pkg)
                targets.extend(sorted(pkg.rglob("*.py")))
        else:
            targets.append(file)
    return targets


def check_purity() -> list[str]:
    # (path, banned-pattern): providers/ never imports the decision layer;
    # deterministic packages never import the decision layer NOR the LLM seam.
    targets: list[tuple[Path, re.Pattern]] = [
        (path, BANNED_DECISION_IMPORT) for path in sorted(PROVIDERS_DIR.rglob("*.py"))
    ]
    for path in _deterministic_scan_targets():
        targets.append((path, BANNED_LLM_IMPORT))
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


def check_import_smoke() -> list[str]:
    """Gate 0: the app must import clean in a fresh interpreter. Subprocess,
    never in-process — this script's own interpreter already carries partial
    imports, and the failure we catch here must read as a boot verdict, not
    a stack in the wrong frame."""
    proc = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode == 0:
        return []
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return ["import app.main raised (boot-level failure):", *tail[-15:]]


def check_kernel_boundary() -> list[str]:
    """Gate 5a (U1 frozen boundary): the ToolLoop kernel emits typed
    LoopEvents saying WHAT HAPPENED — it never imports Presentation/Domain
    and never speaks the Activity channel's construction vocabulary."""
    violations: list[str] = []
    for lineno, line in enumerate(KERNEL_FILE.read_text().splitlines(), start=1):
        if BANNED_KERNEL_IMPORT.match(line) or BANNED_KERNEL_ACTIVITY_VOCAB.search(line):
            violations.append(f"{KERNEL_FILE.relative_to(API_ROOT)}:{lineno}: {line.strip()}")
    return violations


def check_lifecycle_no_presentation() -> list[str]:
    """Gate 5b (ADR-087 dependency direction): the Lifecycle Projection is a
    pure fact layer — Presentation (app.chat) consumes it, never the
    reverse."""
    violations: list[str] = []
    for lineno, line in enumerate(LIFECYCLE_FILE.read_text().splitlines(), start=1):
        if BANNED_PRESENTATION_IMPORT.match(line):
            violations.append(f"{LIFECYCLE_FILE.relative_to(API_ROOT)}:{lineno}: {line.strip()}")
    return violations


def check_client_lifecycle_reads() -> list[str]:
    """Gate 5c (固定不等式的客户端牙): the lifecycle stamp is server-named;
    the client READS ``lifecycle.*`` and never re-derives readiness from
    artifact/run/graph existence."""
    violations: list[str] = []
    if not WEB_SRC.exists():
        return [f"{WEB_SRC}: web source tree not found (gate 5c needs the client)"]
    for path in sorted(WEB_SRC.rglob("*.ts")) + sorted(WEB_SRC.rglob("*.tsx")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if BANNED_CLIENT_LIFECYCLE_DERIVATION.search(
                line
            ) or BANNED_CLIENT_LIFECYCLE_LOCAL.match(line):
                rel = path.relative_to(WEB_SRC.parent.parent)
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    return violations


def main() -> int:
    smoke = check_import_smoke()
    if smoke:
        print("gate 0 FAILED (boot smoke — the app must import before any gate can read its registries):")
        for line in smoke:
            print(f"  {line}")
        return 1
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
    kernel = check_kernel_boundary()
    if kernel:
        print("kernel-boundary gate FAILED (ADR-087 U1: the ToolLoop kernel says WHAT HAPPENED via typed LoopEvents — Activity vocabulary/projection belongs to app/chat/activity.py, Presentation/Domain imports are banned):")
        for failure in kernel:
            print(f"  {failure}")
    lifecycle = check_lifecycle_no_presentation()
    if lifecycle:
        print("lifecycle-purity gate FAILED (ADR-087 dependency direction: the Lifecycle Projection never imports Presentation — app.chat is the consumer, not a dependency):")
        for failure in lifecycle:
            print(f"  {failure}")
    client = check_client_lifecycle_reads()
    if client:
        print("client-lifecycle gate FAILED (固定不等式: lifecycle is server-named — read the results/graph `lifecycle.*` stamp; never infer readiness from artifact/run/graph existence):")
        for failure in client:
            print(f"  {failure}")
    if failures or parallel or blind or retired or kernel or lifecycle or client:
        return 1
    print("check_gates: OK (gate 0 boot smoke, providers/+deterministic purity, no parallel maps, no blind retries, no retired identifiers, ADR-087 kernel/lifecycle/client boundaries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
