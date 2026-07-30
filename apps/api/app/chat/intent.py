"""Intent agents (two distinct jobs, NAMING §5 same-name audit).

``ComposerIntentAgent`` — the Home composer's /infer-intent parser: free-form
prompt → structured generation parameters (language/outputs/tone).

``ChatIntentAgent`` — the chat loop's intent proposer (CHAT_ARCH §3): one
user message + assembled context → a four-state ``IntentProposal``
(task_list / edit_ops / ask / answer — N-18 + N-21). Single
tool-calling-style call per turn, never a ReAct loop; the LLM proposes and
``compile_graph`` adjudicates.
"""

from app.clients.minimax import MiniMaxClient, MiniMaxError
from app.models.schemas import InferredIntent, IntentResult, IntentSlot
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
            "providing source material to repurpose. 'start' ONLY when a task "
            "book (a plan of outputs) is already on the table and the user's "
            "message confirms it and asks to begin — a confirmation is not a "
            "revision.\n"
            "  Examples for action='answer': 'what can you generate?', "
            "'what formats do you support?', 'how does this work?', "
            "'can you make short videos?', 'what is repurposer?'.\n"
            "  Examples for action='generate': 'turn this talk into social posts', "
            "'summarize my keynote in German', [a long pasted transcript], "
            "'5 clips from the interview', 'also add a German post'.\n"
            "  Examples for action='start': 'looks good, start', 'go ahead', "
            "'perfect, run it', '好的开始吧', '可以了，开始', 'start it' — the "
            "user approves the presented plan WITHOUT asking for any change. "
            "If the message asks for any modification (add/remove/change an "
            "output, language, focus), it is 'generate', never 'start'.\n"
            "  The prompt may accumulate several user turns; judge the action "
            "by the LAST line. When earlier turns requested outputs but the "
            "last line is a short approval or go-ahead, the action is 'start' "
            "— those requests are already captured in the presented plan.\n"
            "- answer: when action is 'answer', provide a concise, helpful response "
            "(max 200 words) in the same language as the user prompt that explains "
            "the tool's capabilities and invites the user to upload or paste talk "
            "content. Set to null when action is 'generate' or 'start'.\n"
            "- language: ISO code (en/fr/de/es/it/zh). Infer from the prompt "
            "language or explicit requests like 'in German'. Default to en if "
            "unclear.\n"
            "- language_explicit: true only when the language was clearly "
            "inferred from the prompt (either the prompt's own language or an "
            "explicit 'in German' / 'auf Deutsch' style request). false when "
            "falling back to the default.\n"
            "- outputs: array of requested task slots — one object per "
            "requested output:\n"
            '  {"type": "clips"|"post"|"quotes"|"carousel"|"article", '
            '"count": int|null, "focus": string|null, "language": string|null, '
            '"tone_override": string|null, "explicit": false}\n'
            "  Default to bare slots (all fields null) for clips, post, quotes "
            "and article when unclear.\n"
            "  IMPORTANT: only include a 'clips' slot when a media source file "
            "(video, audio, or image) is attached — clips are rendered videos "
            "and need visual or audio source material. When no file is "
            "uploaded, or the uploaded file is a document/text file, exclude "
            "'clips' (default to post/quotes/article slots instead).\n"
            "  If the user explicitly asks for only some types, return only "
            "those slots.\n"
            "  If the user says 'no clips', 'without clips', 'just a post', or "
            "excludes an output type, respect that.\n"
            "  Only include 'carousel' if the user explicitly asks for a carousel, "
            "slide deck, or swipeable post; otherwise leave it out.\n"
            "  - count: the quantity the user asked for ON THAT SLOT "
            "(e.g. '5 clips' → clips slot count 5, '8 张金句卡' → quotes slot "
            "count 8, 'a 10-slide carousel' → carousel slot count 10). null "
            "when no quantity is mentioned for that type.\n"
            "  - focus: a short angle phrase when the user assigns a specific "
            "angle to an output (e.g. '切片剪定价争议' → clips slot focus "
            "'pricing debate', 'the post should summarize the whole talk' → "
            "post slot focus). null when the user gives no per-output angle.\n"
            "  - language: ISO code ONLY when this slot's language differs "
            "from the top-level language — the classic case is the user "
            "asking for several LANGUAGE VERSIONS of the same output (e.g. "
            "'一版英文帖和一版德语帖' / 'an English and a German LinkedIn "
            "post' → TWO post slots, one language 'en', one language 'de'). "
            "For ordinary single-language requests keep every slot's "
            "language null (the top-level language covers all slots).\n"
            "  - Same-type multi slots are allowed ONLY for such multi-version "
            "requests (different language or clearly different angle). Never "
            "emit more than one 'clips' slot — clips is a single aggregate "
            "slot; its count covers the batch.\n"
            "  - tone_override: a short tone note when the user asks for a "
            "per-output tone (e.g. '帖子正式一点、金句活泼一点' → post slot "
            "'formal', quotes slot 'playful'). Otherwise null.\n"
            "  - explicit: always false — it is a UI-side marker, never "
            "inferred.\n"
            "- dub_languages: array of ISO codes when the user asks for VOICE "
            "DUBBING of their clips into other languages — the speaker's own "
            "cloned voice speaking another language (e.g. '配音成德语和法语', "
            "'dub my clips into German and French', '再来一版西语配音'). "
            "Empty array otherwise. This is distinct from slot languages "
            "(which set an output's text language) — dubbing produces extra "
            "VOICE-OVER versions of the same clips. Same gating as clips: "
            "only when a media source file (video/audio/image) is attached; "
            "text-only input gets an empty array.\n"
            "- outputs_explicit: true only when the user explicitly asked for "
            "specific outputs (e.g. 'just clips', 'a post and quotes', "
            "'no carousel'). false when using the default set.\n"
            "- tone: one of professional, thoughtLeadership, conversational, "
            "academic. Default professional.\n"
            "- specific_instruction: a short distilled instruction for the "
            "generator. Capture what the user wants, excluding "
            "language/output/tone/slot fields. For action='answer' or 'start', "
            "set this to null.\n"
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
                language_explicit=False,
                outputs=(
                    [
                        IntentSlot(type="clips"),
                        IntentSlot(type="post"),
                        IntentSlot(type="quotes"),
                        IntentSlot(type="article"),
                    ]
                    if has_media
                    else [
                        IntentSlot(type="post"),
                        IntentSlot(type="quotes"),
                        IntentSlot(type="article"),
                    ]
                ),
                outputs_explicit=False,
                tone="professional",
                specific_instruction=prompt.strip() or None,
                confidence=0.0,
            )


composer_intent_agent = ComposerIntentAgent()


class ChatIntentAgent:
    """Proposes what to do with one chat message (propose-only, no execution).

    One call per turn. The proposal space is the dispatchable skill registry
    plus the ask state (N-18) and the direct answer state (N-21): an
    ambiguous or forking message gets a structured question (options +
    freeform fallback), a purely informational one gets a prose answer —
    asking is a legal answer, not a failure, and so is simply answering.
    """

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def propose(self, message: str, context: dict) -> IntentResult:
        """Return the four-state proposal for one user message."""
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
            "is exactly one of four shapes:\n"
            'A. {"type": "task_list", "tasks": [{"skill": "<name>", "params": {...}}], '
            '"summary": "<one user-facing sentence>"} — run new work. Only use '
            "skills from the list below; tasks is never empty (when you need to "
            "ask the user first, use shape C instead).\n"
            'B. {"type": "edit_ops", "target_output_id": "<uuid>", '
            '"ops": [{"op": "<name>", "params": {...}}], '
            '"summary": "<one user-facing sentence>"} — the user wants a precise '
            "edit of ONE existing output (trim a moment, cut a time range, tweak "
            "a caption, change title/music/crop). Use this shape whenever the "
            "instruction targets an existing output with clip-level precision, "
            "using ONLY the ops below.\n"
            'C. {"type": "ask", "question": "<one clear question in the user\'s '
            'language>", "kind": "choice", "options": [{"id": "a", "label": '
            '"<short label>"}, ...], "allow_freeform": true} — you cannot '
            "responsibly pick between two or more readings of the message, so "
            "you ask before proposing work. Give 2-4 concrete options the user "
            "can pick with one word (ids: lowercase letters a, b, c...). Use an "
            "empty options list only when no sensible options exist (a freeform "
            "ask). kind is always 'choice' — task_book and confirm are raised "
            "by the system, never by you.\n"
            'D. {"type": "answer", "text": "<helpful reply in the user\'s '
            'language>"} — a purely informational reply: what you can do, how '
            "things work, the run's progress (the context carries a per-step "
            "status section — quote real node states from it), an explanation "
            "of an existing output, or small talk. Nothing is dispatched, no "
            "run starts, no question docks.\n\n"
            "Available skills:\n" + skill_lines + "\n\n"
            "Available edit ops (shape B only):\n" + op_lines + "\n\n"
            "Rules:\n"
            "- Never invent skills, ops, or params not in the lists.\n"
            "- Translating captions or dubbing a voice is shape A "
            "(translate_clip / dub_clip), never shape B.\n"
            "- Prefer the fewest tasks/ops that express the instruction.\n"
            "- summary is written for the user, in the user's language.\n"
            "- Shape D is ONLY for messages that request information, not "
            "work. If the user asks you to do anything (create, rewrite, "
            "translate, dub, trim, remove, ...), propose shape A or B — never "
            "answer with a description of the work instead of doing it.\n"
            "- If the request is work but ambiguous between two or more "
            "readings, use shape C — never use shape D to dodge a decision.\n"
            "- Asking (shape C) is a legal answer, not a failure — but only "
            "ask when no reasonable default exists; never ask about things "
            "you can infer from the context.\n"
            "- Progress questions ('how far along', '还要多久', 'what's the "
            "status') are shape D: answer from the per-step status section — "
            "which steps are done, which is running, and whether one is "
            "waiting for the user's answer. Never guess beyond it.\n"
            "- You cannot publish or share outputs to social platforms from "
            "chat. When the user asks to publish ('发到 LinkedIn', 'post this "
            "to TikTok'), shape D: point them to the publish button on each "
            "output card.\n"
            "- Identity settings are not chat work. When the user wants to "
            "change the brand template or the speaker/persona, shape D: "
            "direct them to the Brand template / Speakers pages in the "
            "sidebar.\n"
            "- When the context shows a pending question, the user's message "
            "may be its answer — act on the question + answer together "
            "instead of asking again.\n"
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
