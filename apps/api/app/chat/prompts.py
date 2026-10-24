"""Model-facing prose for the two chat intent agents.

The prose itself lives in ``app/prompts/chat/*.j2`` — one template per
agent, shared blocks as ``_*.j2`` partials (``{% include %}``, one
definition two consumers) — rendered through the shared
``agents/base.py`` jinja env. Model-facing text carries current-state law
only: dates / ADR numbers / incident narratives never enter it. This
module is the thin assembly wrapper: same function signatures, same call
sites (``chat/intent.py`` keeps the declarations data-only). The tool
catalog lines are the registry's self-projection (``app/tools/__init__.py`` —
``tool_catalog_lines``): chat consumes, never re-projects; they ride into
the templates as render variables (``tool_lines`` / ``wiring_lines``).
"""

from app.agents.base import jinja_env
from app.tools import capability_menu_lines, tool_catalog_lines


def intent_router_system() -> str:
    """The plan builder's system prompt (plan path).

    revise_script is excluded from the catalog — it targets an EXISTING
    output and the plan path runs before the project's first run, when none
    exist."""
    from app.config import settings  # deferred: config leaf

    return jinja_env.get_template("chat/intent_router_system.j2").render(
        tool_lines=tool_catalog_lines(exclude={"revise_script"}),
        menu_lines=capability_menu_lines(),
        # The film edit path's prompt law rides the same deployment gate as
        # the tool wire view — gate off, the model is never told.
        film_edits_enabled=settings.film_edits_enabled,
    )


def chat_intent_system() -> str:
    """The chat loop intent proposer's system prompt (four-state proposal).

    Params are injected as "name: description" — the Field descriptions in
    the registry's params models ARE the LLM's parameter documentation."""
    # The raw edit-ops vocabulary (``op_lines`` from OP_REGISTRY) is NOT
    # injected — the Agent's only edit entry is edit_output's controlled
    # enum (ADR-090); raw op names and their param shapes never enter the
    # LLM vocabulary.
    # The wiring vocabulary (ADR-057 K4) comes from the graph registry —
    # same injection discipline as the tool catalog (registry entries stay
    # terse; the gate enumerations ride along).
    # Kept as a function-level import (cycle insurance, pre-split form).
    from app.config import settings  # deferred: config leaf
    from app.pipeline.graph_store import wiring_catalog_lines

    return jinja_env.get_template("chat/chat_intent_system.j2").render(
        tool_lines=tool_catalog_lines(),
        menu_lines=capability_menu_lines(),
        wiring_lines=wiring_catalog_lines(),
        # chat_loop=True: the shared no-material partial drops the router-only
        # framing (draft header / material_text bullets) and appends
        # the existing-project tail (ADR-071 ④ 单一化).
        chat_loop=True,
        # The film edit path's prompt law rides the same deployment gate as
        # the tool wire view — gate off, the model is never told.
        film_edits_enabled=settings.film_edits_enabled,
    )


def trigger_system() -> str:
    """The read-bearing proactive speaker for run_failed/craft_decompiled.

    run_completed is a separate DELIVERY turn with its own readless prompt;
    the two turn families never share branch law.
    """
    return jinja_env.get_template("chat/trigger_system.j2").render(
        menu_lines=capability_menu_lines(),
    )


def delivery_system() -> str:
    """The delivery turn's compact, outcome-branched system prompt."""
    return jinja_env.get_template("chat/delivery_system.j2").render()
