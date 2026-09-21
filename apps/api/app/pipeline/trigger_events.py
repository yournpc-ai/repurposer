"""Trigger event seam (ADR-087 §6 dependency direction; CHAT_ARCH §8.8 whitelist).

The pipeline PUBLISHES the whitelisted world events; the Agent Interface
subscribes its trigger turn from the composition root (``app.main`` /
``app.worker``). This module is the ONLY legal pipeline → chat edge for the
trigger seats — Runtime → Events, never an import of ``app.chat``. The
pipeline's fire points (understanding warm / run terminal / craft decompile)
call :func:`fire_trigger`; ``chat/trigger_turn.py`` registers its own
``fire_trigger`` (schedule the turn, track the task) as the handler at
process boot.

Whitelist discipline (freeze): the three trigger kinds below are the whole
proactivity boundary — this is a seam, not an event bus. Adding a kind is an
ADR-level review (CHAT_ARCH §8.8), never a drive-by.
"""

from collections.abc import Callable
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

# The proactivity boundary (白名单): a turn fires ONLY on these world events.
TRIGGER_UNDERSTANDING = "understanding_warmed"
TRIGGER_RUN_COMPLETED = "run_completed"
TRIGGER_CRAFT_DECOMPILED = "craft_decompiled"  # 案例拆解完成 (ADR-078, 旅程二④)
TRIGGER_WHITELIST = frozenset(
    {TRIGGER_UNDERSTANDING, TRIGGER_RUN_COMPLETED, TRIGGER_CRAFT_DECOMPILED}
)

# The subscriber's fire seat: (project_id, trigger, ref) -> schedule the turn
# and return (fire-and-forget — the world event already landed truthfully;
# the speech layer degrades to silence, never to a pipeline failure).
TriggerHandler = Callable[[UUID, str, str], None]

_handler: TriggerHandler | None = None


def register_trigger_handler(handler: TriggerHandler) -> None:
    """Subscribe the Agent Interface's trigger turn. Wired once per process
    by the composition root (``app.main`` / ``app.worker``); a later call
    replaces (probe/test seams)."""
    global _handler
    _handler = handler


def fire_trigger(project_id: UUID, trigger: str, ref: str) -> None:
    """Publish a whitelisted world event. No subscriber = the speech layer is
    absent in this process (ad-hoc in-process scripts): log and move on —
    the event itself (the understanding row, the run verdict) already
    landed. An unknown trigger fails loudly at the fire site."""
    if trigger not in TRIGGER_WHITELIST:
        raise ValueError(f"trigger {trigger!r} is outside the whitelist")
    if _handler is None:
        logger.warning("trigger_no_subscriber", trigger=trigger, ref=ref)
        return
    _handler(project_id, trigger, ref)
