"""Composition-root seam wiring (ADR-087 §6, Phase 5).

One call wires the Agent Interface into the pipeline's two legal seams:
the whitelist trigger events (``app.pipeline.trigger_events``) and the
conversation command bridge (``app.pipeline.conversation_bridge``). The
composition roots (``app.main`` / ``app.worker``) call this at boot —
never inside ``app.pipeline`` itself.
"""

from app.chat.service import (
    discard_unanswered_plan,
    dock_interrupt_question,
    finalize_bailed_runs,
    record_material_beat,
    seed_project_prompt,
)
from app.chat.trigger_turn import fire_trigger
from app.pipeline.conversation_bridge import (
    ConversationBridge,
    register_conversation_bridge,
)
from app.pipeline.trigger_events import register_trigger_handler


def wire_pipeline_seams() -> None:
    """Subscribe the Agent Interface to the pipeline's two legal seams."""
    register_trigger_handler(fire_trigger)
    register_conversation_bridge(
        ConversationBridge(
            dock_interrupt_question=dock_interrupt_question,
            finalize_bailed_runs=finalize_bailed_runs,
            seed_project_prompt=seed_project_prompt,
            discard_unanswered_plan=discard_unanswered_plan,
            record_material_beat=record_material_beat,
        )
    )
