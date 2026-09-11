"""Model-facing prose for the two chat intent agents (N-42 批③).

2026-09-11 ADR-071 结构拆分 + 规则减负: the prose itself lives in
``app/prompts/chat/*.j2`` — one template per agent, shared blocks as
``_*.j2`` partials (``{% include %}``, one definition two consumers) —
rendered through the shared ``agents/base.py`` jinja env. 考古不出 token
律: dates / ADR numbers / reversal history live in the templates' ``{# #}``
head comments, never in model-facing text. This module is the thin
assembly wrapper: same function signatures, same call sites
(``chat/intent.py`` keeps the declarations data-only). The tool catalog
lines are the registry's self-projection (``app/tools/__init__.py`` —
``tool_catalog_lines``): chat consumes, never re-projects (裂脑修复);
they ride into the templates as render variables (``tool_lines`` /
``op_lines`` / ``wiring_lines``).
"""

from app.agents.base import jinja_env
from app.operations.registry import OP_REGISTRY
from app.tools import tool_catalog_lines


def intent_router_system() -> str:
    """The task-book builder's system prompt (book path).

    revise_script is excluded from the catalog — it targets an EXISTING
    output and the book path runs before the project's first run, when none
    exist."""
    return jinja_env.get_template("chat/intent_router.j2").render(
        tool_lines=tool_catalog_lines(exclude={"revise_script"}),
    )


def chat_intent_system() -> str:
    """The chat loop intent proposer's system prompt (four-state proposal).

    Params are injected as "name: description" (agent-loop-upgrade W2) —
    the Field descriptions in the registry's params models ARE the LLM's
    parameter documentation."""
    # The edit-ops vocabulary comes from the operations registry (ADR-032)
    # — same pattern as the tool list; precomputed ops (translate/dub)
    # are deliberately proposed as task_list tools instead.
    op_lines = "\n".join(
        f"- {name}: {opdef.description} (params: {list(opdef.params_model.model_fields)})"
        for name, opdef in OP_REGISTRY.items()
        if opdef.client_allowed and not opdef.precomputed and opdef.llm_visible
    )
    # The wiring vocabulary (ADR-057 K4) comes from the graph registry —
    # same injection discipline as the tool/op catalogs (注册表条目扰动 =
    # prompt 扰动: entries stay terse, the gate enumerations ride along).
    # Kept as a function-level import (cycle insurance, pre-split form).
    from app.pipeline.graph_store import wiring_catalog_lines

    return jinja_env.get_template("chat/chat_intent.j2").render(
        tool_lines=tool_catalog_lines(),
        op_lines=op_lines,
        wiring_lines=wiring_catalog_lines(),
    )
