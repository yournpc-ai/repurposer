"""Structural checks for the HTTP suite and the developer command reference."""
import ast
from pathlib import Path
import re
import shlex

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[4]
CHAT = ROOT / "apps/api/test/chat_origin"
BYPASSES = {"run_plan_turn", "PlanTurn", "stream_plan_turn", "execute_editor_tool"}
HELPERS = {f"test.support.chat_http.{name}" for name in ("post_chat", "scripted_chat", "tool_result")}


def qualified(node, imports):
    if isinstance(node, ast.Name):
        return imports.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{qualified(node.value, imports)}.{node.attr}"
    return ""


def violations(source, *, test_module=True):
    tree = ast.parse(source)
    imports = {}
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if isinstance(node, ast.ImportFrom):
                    path = f"{node.module}.{alias.name}"
                    imports[alias.asname or alias.name] = path
                else:
                    path = alias.name
                    imports[alias.asname or path.split('.')[0]] = path if alias.asname else path.split('.')[0]
                if path.split(".")[-1] in BYPASSES:
                    errors.append(f"line {node.lineno}: forbidden import {path}")
    http = False
    marked = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = qualified(node.func, imports)
            if target.split(".")[-1] in BYPASSES:
                errors.append(f"line {node.lineno}: forbidden call {target}")
            url = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "url"), None)
            http |= target in HELPERS or (target.endswith(".post") and isinstance(url, ast.Constant)
                                          and url.value == "/api/v1/chat")
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark"
                                                    for t in statement.targets):
            marked |= any(qualified(n, imports) == "pytest.mark.chat_origin" for n in ast.walk(statement.value))
    if test_module and not http:
        errors.append("missing POST /api/v1/chat or shared HTTP helper call")
    if test_module and not marked:
        errors.append("missing module-level pytest.mark.chat_origin")
    return errors


def test_chat_origin_modules_use_http():
    files = sorted(CHAT.rglob("*.py"))
    assert any(path.match("test_*.py") for path in files)
    errors = [
        f"{path.relative_to(CHAT)}: {error}"
        for path in files
        for error in violations(path.read_text(), test_module=path.match("test_*.py"))
    ]
    assert not errors, "\n".join(errors)


GOOD = 'import pytest\npytestmark = pytest.mark.chat_origin\nclient.post("/api/v1/chat")'


@pytest.mark.parametrize("source,error", [
    (GOOD.replace("post(", "get("), "missing POST"),
    (GOOD.replace('client.post("/api/v1/chat")', 'path = "/api/v1/chat"'), "missing POST"),
    (GOOD.replace("pytestmark =", "unused ="), "missing module-level"),
    (GOOD + "\nfrom app.chat.plan_turn import run_plan_turn as turn", "forbidden import"),
    (GOOD + "\nimport app.chat.plan_turn as turn\nturn.PlanTurn()", "forbidden call"),
    (GOOD + "\nstream_plan_turn()", "forbidden call"),
    (GOOD + "\neditor.execute_editor_tool()", "forbidden call"),
    (GOOD.replace('client.post("/api/v1/chat")', 'from test.support.chat_http import post_chat'), "missing POST"),
])
def test_gate_rejects_counterexamples(source, error):
    assert any(error in message for message in violations(source))


def test_gate_scans_support_modules_for_internal_bypasses():
    assert not violations("def helper(): pass", test_module=False)
    assert violations("from app.chat.plan_turn import PlanTurn as turn", test_module=False)


def test_gate_accepts_imported_http_helper_alias():
    assert not violations(GOOD.replace('client.post("/api/v1/chat")',
        "from test.support.chat_http import post_chat as send\nsend(client, pid, message)"))


def documented_targets(markdown):
    fence = None
    for line in markdown.replace("\\\n", " ").splitlines():
        delimiter = re.match(r"^\s*(`{3,}|~{3,})", line)
        if delimiter:
            if fence is None:
                fence = delimiter[1]
            elif delimiter[1].startswith(fence):
                fence = None
        elif fence:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|")
            lexer.whitespace_split = True
            in_make = False
            for word in lexer:
                if word == "make":
                    in_make = True
                elif word in {"&&", ";", "|", "||", "&"}:
                    in_make = False
                elif in_make and not word.startswith("-") and "=" not in word:
                    yield word


def test_testing_guide_make_targets_exist():
    documented = set(documented_targets((ROOT / "docs/TESTING.md").read_text()))
    defined = {name for line in (ROOT / "Makefile").read_text().splitlines()
               if (match := re.match(r"^([\w.-]+(?: +[\w.-]+)*)\s*:(?!=)", line))
               for name in match[1].split()}
    assert documented
    assert not documented - defined, sorted(documented - defined)


def test_documented_targets_include_chained_and_multiple_goals():
    assert list(documented_targets("outside make ignored\n~~~sh\nmake a b FLAG=x && make missing # make no\n~~~")) == [
        "a", "b", "missing",
    ]
