"""Intent agents (two distinct jobs, NAMING §5 same-name audit).

``ComposerIntentAgent`` — the Home composer's /infer-intent parser: free-form
prompt → structured generation parameters (language/outputs/tone).

``ChatIntentAgent`` — the chat loop's intent proposer (CHAT_ARCH §3): one
user message + assembled context → a two-state ``IntentProposal`` (task_list
/ edit_ops). Single tool-calling-style call per turn, never a ReAct loop;
the LLM proposes and ``compile_graph`` adjudicates.
"""

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import InferredIntent, IntentResult
from app.operations.registry import OP_REGISTRY
from app.pipeline.registry import dispatchable_skills


class ComposerIntentAgent:
    """Agent that infers structured intent from a composer prompt."""

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
            "- action: 'generate' if the user wants to repurpose speech/talk content "
            "into assets. 'answer' if they are asking about what the tool can do, "
            "how it works, pricing, or other meta/capability questions without "
            "providing source material to repurpose.\n"
            "  Examples for action='answer': 'what can you generate?', "
            "'what formats do you support?', 'how does this work?', "
            "'can you make short videos?', 'what is repurposer?'.\n"
            "  Examples for action='generate': 'turn this talk into social posts', "
            "'summarize my keynote in German', [a long pasted transcript], "
            "'5 clips from the interview'.\n"
            "- answer: when action is 'answer', provide a concise, helpful response "
            "(max 200 words) in the same language as the user prompt that explains "
            "the tool's capabilities and invites the user to upload or paste talk "
            "content. Set to null when action is 'generate'.\n"
            "- language: ISO code (en/fr/de/es/it/zh). Infer from the prompt "
            "language or explicit requests like 'in German'. Default to en if "
            "unclear.\n"
            "- outputs: array of requested asset types. Valid values: clips, post, "
            "quotes, carousel, article.\n"
            "  Default to [\"clips\", \"post\", \"quotes\", \"article\"] when "
            "unclear.\n"
            "  IMPORTANT: only include 'clips' when a media source file "
            "(video, audio, or image) is attached — clips are rendered videos "
            "and need visual or audio source material. When no file is "
            "uploaded, or the uploaded file is a document/text file, exclude "
            "'clips' (default to [\"post\", \"quotes\", \"article\"] instead).\n"
            "  If the user explicitly asks for only some types, return only those.\n"
            "  If the user says 'no clips', 'without clips', 'just a post', or "
            "excludes an output type, respect that.\n"
            "  Only include 'carousel' if the user explicitly asks for a carousel, "
            "slide deck, or swipeable post; otherwise leave it out.\n"
            "- clip_count: integer number of clips the user wants (e.g. '5 clips' "
            "→ 5, 'a few clips' → 3, 'no clips' → 0).\n"
            "  Only set this when the user mentions a quantity of clips. Otherwise "
            "null.\n"
            "- tone: one of professional, thoughtLeadership, conversational, "
            "academic. Default professional.\n"
            "- specific_instruction: a short distilled instruction for the "
            "generator. Capture what the user wants, excluding "
            "language/output/tone/clip_count. For action='answer', set this to "
            "null.\n"
            "- confidence: 0.0-1.0 indicating how clearly the intent was "
            "expressed.\n\n"
            "Return only a JSON object matching the schema."
        )

        context = f"User prompt: {prompt}"
        if filename:
            context += f"\nUploaded file: {filename}"
        else:
            context += "\nNo file uploaded (text-only input)."

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
            # Fall back to defaults so the UI never breaks. Clips need a media
            # source file, so text-only input falls back to text outputs.
            has_media = filename is not None and filename.lower().endswith(
                (".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a", ".aac",
                 ".ogg", ".png", ".jpg", ".jpeg", ".webp")
            )
            return InferredIntent(
                action="generate",
                answer=None,
                language="en",
                outputs=(
                    ["clips", "post", "quotes", "article"]
                    if has_media
                    else ["post", "quotes", "article"]
                ),
                clip_count=None,
                tone="professional",
                specific_instruction=prompt.strip() or None,
                confidence=0.0,
            )


composer_intent_agent = ComposerIntentAgent()


class ChatIntentAgent:
    """Proposes what to do with one chat message (propose-only, no execution).

    One call per turn. The proposal space is the dispatchable skill registry;
    empty task list = ask back (a legal answer, not a failure).
    """

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def propose(self, message: str, context: dict) -> IntentResult:
        """Return the two-state proposal for one user message."""
        skills = dispatchable_skills()
        skill_lines = "\n".join(
            f"- {s.name}: {s.description}"
            + (f" (params: {list(s.params_model.model_fields)})" if s.params_model else "")
            for s in skills
        )
        # The edit-ops vocabulary comes from the operations registry (ADR-032)
        # — same pattern as the skill list; precomputed ops (translate/dub)
        # are deliberately proposed as task_list skills instead.
        op_lines = "\n".join(
            f"- {name}: {opdef.description} (params: {list(opdef.params_model.model_fields)})"
            for name, opdef in OP_REGISTRY.items()
            if opdef.client_allowed and not opdef.precomputed
        )
        system_prompt = (
            "You are the intent proposer of an AI content repurposing tool. "
            "Given one user message and the assembled context, decide what to do "
            "and return valid JSON only.\n\n"
            'Return a single JSON object {"proposal": PROPOSAL} where PROPOSAL '
            "is exactly one of two shapes:\n"
            'A. {"type": "task_list", "tasks": [{"skill": "<name>", "params": {...}}], '
            '"summary": "<one user-facing sentence>"} — run new work. Only use '
            "skills from the list below; leave tasks EMPTY when the message is "
            "ambiguous and you need to ask back (the summary then holds your "
            "clarifying question — asking back is a legal answer, not a failure).\n"
            'B. {"type": "edit_ops", "target_output_id": "<uuid>", '
            '"ops": [{"op": "<name>", "params": {...}}], '
            '"summary": "<one user-facing sentence>"} — the user wants a precise '
            "edit of ONE existing output (trim a moment, cut a time range, tweak "
            "a caption, change title/music/crop). Use this shape whenever the "
            "instruction targets an existing output with clip-level precision, "
            "using ONLY the ops below.\n\n"
            "Available skills:\n" + skill_lines + "\n\n"
            "Available edit ops (shape B only):\n" + op_lines + "\n\n"
            "Rules:\n"
            "- Never invent skills, ops, or params not in the lists.\n"
            "- Translating captions or dubbing a voice is shape A "
            "(translate_clip / dub_clip), never shape B.\n"
            "- Prefer the fewest tasks/ops that express the instruction.\n"
            "- summary is written for the user, in the user's language.\n"
            "- When the user references a mention (asset/output/segment), use its "
            "id in params (e.g. revise_script.target_output_id) instead of guessing."
        )

        user_content = (
            f"Context:\n{context.get('text', '')}\n\nUser message: {message}"
        )
        if context.get("repair_feedback"):
            user_content += (
                "\n\nYour previous proposal was rejected: "
                f"{context['repair_feedback']}. Fix it and return a valid proposal."
            )

        return await self.client.generate(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_model=IntentResult,
            temperature=0.2,
        )


chat_intent_agent = ChatIntentAgent()
