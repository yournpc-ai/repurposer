"""Intent recognition agent.

Translates a free-form user prompt into structured generation parameters.
Used by the Home composer confirmation layer so the user sees what the AI
understood and can edit it before generating.
"""

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import InferredIntent


class IntentAgent:
    """Agent that infers structured intent from a user prompt."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def infer(
        self, prompt: str, filename: str | None = None
    ) -> InferredIntent:
        """Infer language, outputs, tone and instruction from prompt.

        Args:
            prompt: The user's free-form prompt or pasted transcript.
            filename: Optional uploaded filename for extra context.

        Returns:
            InferredIntent with defaults when inference fails.
        """
        system_prompt = (
            "You are an intent parser for an AI content repurposing tool. "
            "Given a user prompt, extract the user's intent and return valid JSON only.\n\n"
            "Rules:\n"
            "- language: ISO code (en/fr/de/es/it/zh). Infer from the prompt language or explicit requests like 'in German'. Default to en if unclear.\n"
            "- outputs: array of requested asset types. Valid values: clips, linkedin, quote_cards, summary.\n"
            "  Default to [\"clips\", \"linkedin\", \"quote_cards\", \"summary\"] when unclear.\n"
            "  If the user explicitly asks for only some types, return only those.\n"
            "  If the user says 'no clips' or 'just LinkedIn', respect that.\n"
            "- tone: one of professional, thoughtLeadership, conversational, academic. Default professional.\n"
            "- specific_instruction: a short distilled instruction for the generator. Capture what the user wants, excluding language/output/tone.\n"
            "- confidence: 0.0-1.0 indicating how clearly the intent was expressed.\n\n"
            "Return only a JSON object matching the schema."
        )

        context = f"User prompt: {prompt}"
        if filename:
            context += f"\nUploaded file: {filename}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]

        try:
            return await self.client.generate(
                messages=messages,
                response_model=InferredIntent,
                temperature=0.2,
            )
        except MiniMaxError:
            # Fall back to defaults so the UI never breaks.
            return InferredIntent(
                language="en",
                outputs=["clips", "linkedin", "quote_cards", "summary"],
                tone="professional",
                specific_instruction=prompt.strip() or None,
                confidence=0.0,
            )


intent_agent = IntentAgent()
