"""Import direction gate (ADR-087 §6, Phase 5 — acceptance main evidence).

Zero DB, zero LLM. Four teeth:

1. **AST gate — pipeline ↛ chat**: no ``app.chat`` import anywhere under
   ``app/pipeline/`` (top-level or deferred, AST walks the whole tree).
2. **AST gate — no cross-module private import**: no ``from app.X… import
   _private`` crossing top-level packages under ``app/`` (intra-package
   private imports are exempt — a module's own privates are its business).
3. **Cold-import probe**: importing every ``app.pipeline.*`` module in a
   fresh interpreter never lands ``app.chat`` in ``sys.modules``; the reverse
   (``app.chat.service`` cold import) legitimately lands ``app.pipeline`` —
   the import graph runs one way.
4. **Wiring belt**: both composition roots (``app.main`` / ``app.worker``)
   call ``app.chat.seams.wire_pipeline_seams`` — the only legal pipeline →
   chat edges (trigger events / conversation bridge) live nowhere else.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = API_ROOT / "app"


def _iter_app_files():
    for path in sorted(APP_ROOT.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def _top_pkg(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else ""


def _is_chat_module(module: str) -> bool:
    return module == "app.chat" or module.startswith("app.chat.")


def test_no_pipeline_to_chat_import() -> None:
    """Gate 1: the frozen prohibition (ADR-087 §6) — pipeline never imports
    chat, at ANY nesting depth (deferred workarounds included)."""
    offenders: list[str] = []
    for path in _iter_app_files():
        rel = path.relative_to(APP_ROOT)
        if rel.parts[0] != "pipeline":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if _top_pkg(node.module) == "chat":
                    offenders.append(f"{rel}:{node.lineno} from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _top_pkg(alias.name) == "chat":
                        offenders.append(f"{rel}:{node.lineno} import {alias.name}")
    assert not offenders, "pipeline → chat imports: " + ", ".join(offenders)


def test_no_cross_module_private_import() -> None:
    """Gate 2: private names never cross a top-level package boundary."""
    offenders: list[str] = []
    for path in _iter_app_files():
        rel = path.relative_to(APP_ROOT)
        src_pkg = rel.parts[0] if len(rel.parts) > 1 else ""
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ImportFrom) and node.module):
                continue
            if not node.module.startswith("app."):
                continue
            dst_pkg = _top_pkg(node.module)
            if not src_pkg or not dst_pkg or src_pkg == dst_pkg:
                continue
            for alias in node.names:
                if alias.name.startswith("_"):
                    offenders.append(
                        f"{rel}:{node.lineno} from {node.module} import {alias.name}"
                    )
    assert not offenders, "cross-module private imports: " + ", ".join(offenders)


def _cold_import(modules: list[str]) -> set[str]:
    """Import the modules in a FRESH interpreter; return the app.* modules
    that landed in sys.modules."""
    code = (
        "import sys, importlib, json\n"
        f"for m in {modules!r}:\n"
        "    importlib.import_module(m)\n"
        "print(json.dumps(sorted("
        "m for m in sys.modules if m == 'app' or m.startswith('app.'))))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, f"cold-import child failed:\n{out.stderr[-3000:]}"
    return set(json.loads(out.stdout))


def _pipeline_modules() -> list[str]:
    mods: set[str] = set()
    for path in _iter_app_files():
        rel = path.relative_to(APP_ROOT)
        if rel.parts[0] != "pipeline":
            continue
        dotted = "app." + ".".join(rel.with_suffix("").parts)
        if dotted.endswith(".__init__"):
            dotted = dotted[: -len(".__init__")]
        mods.add(dotted)
    return sorted(mods)


def test_pipeline_cold_import_never_lands_chat() -> None:
    """Probe 3a (the unidirection proof): every pipeline module, one fresh
    interpreter — app.chat must never arrive."""
    loaded = _cold_import(_pipeline_modules())
    landed = {m for m in loaded if _is_chat_module(m)}
    assert not landed, f"pipeline cold import landed chat: {sorted(landed)}"


def test_chat_cold_import_lands_pipeline_one_way() -> None:
    """Probe 3b (the reverse is the LEGAL direction): chat cold-importing
    its pipeline dependencies succeeds and lands pipeline modules — the
    graph's one-way street."""
    loaded = _cold_import(["app.chat.service"])
    assert "app.pipeline.derivative_dispatch" in loaded
    assert "app.pipeline.asset_processing" in loaded


def test_composition_roots_wire_the_seams() -> None:
    """Belt 4: the two legal seams (trigger events / conversation bridge)
    are wired by the composition roots and nowhere else."""
    for root_name in ("main.py", "worker.py"):
        src = (APP_ROOT / root_name).read_text()
        assert "wire_pipeline_seams()" in src, (
            f"app.{root_name.removesuffix('.py')} never wires the seams"
        )
