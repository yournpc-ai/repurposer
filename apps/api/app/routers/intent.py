"""Intent inference router."""

from fastapi import APIRouter

from app.agents.intent import intent_agent
from app.models.schemas import InferIntentRequest, InferIntentResponse

router = APIRouter()


@router.post("/infer-intent", response_model=InferIntentResponse)
async def infer_intent(request: InferIntentRequest) -> InferIntentResponse:
    """Infer structured generation intent from a user prompt.

    Returns suggested language, outputs, tone and a distilled instruction.
    The frontend presents these as an editable confirmation layer.
    """
    intent = await intent_agent.infer(
        prompt=request.prompt,
        filename=request.filename,
    )
    return InferIntentResponse(intent=intent)
