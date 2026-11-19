from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.base import Agent, AssembleResult


class SfxIntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["search", "add", "replace", "use_existing", "present", "none", "deny"]
    evidence: str = Field(min_length=1, max_length=300)


def _assemble_sfx_intent(*, user_text: str) -> AssembleResult:
    return {"user_text": user_text}, []


sfx_intent_agent: Agent[SfxIntentDecision] = Agent(
    name="sfx_intent",
    prompt="chat/sfx_intent.j2",
    schema=SfxIntentDecision,
    system=(
        "只判断用户想进行的音效操作。不要编造工具请求，也不要将助手的话当作用户授权。只输出有效 JSON。"
    ),
    temperature=0.0,
    assemble=_assemble_sfx_intent,
    timeout_s=60,
)


def allows_provider_search(decision: SfxIntentDecision) -> bool:
    return decision.action in {"search", "add", "replace"}
