"""Intent agents (two distinct jobs behind the SINGLE chat surface, NAMING §5).

``PlanAgent`` — the task-book builder (plan path, CHAT_ARCH §3): free-form
text → a structured task book (language/outputs/tone) plus the three-action
verdict (generate / answer / start). Invoked only from the chat service's
plan path — first-turn projects and pending-task-book refinement turns.

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


class PlanAgent:
    """Agent that builds the structured task book from free-form text."""

    def __init__(self, client: MiniMaxClient | None = None) -> None:
        self.client = client or MiniMaxClient()

    async def infer(
        self,
        prompt: str,
        filename: str | None = None,
        presented_plan: str | None = None,
        recent: list[str] | None = None,
    ) -> InferredIntent:
        """Infer language, outputs, tone and instruction from prompt.

        Args:
            prompt: The user's free-form prompt or pasted transcript.
            filename: Optional uploaded filename for extra context.
            presented_plan: One-line digest of the docked task book, when one
                is on the table — the start/revise verdict needs to SEE the
                plan being confirmed, not imagine it (a bare "开始吧" after a
                vague first turn otherwise reads as "go generate").
            recent: The conversation's latest rounds (pre-formatted lines,
                current message excluded) — the material/content judgment
                needs to SEE what just happened (e.g. the assistant asking
                for source material), not read the text in a vacuum (G-7).

        Returns:
            InferredIntent with defaults when inference fails.
        """
        try:
            return await self.client.generate(
                messages=self._messages(prompt, filename, presented_plan, recent),
                response_model=InferredIntent,
                temperature=0.2,
            )
        except MiniMaxError:
            return self._fallback(prompt, filename)

    async def infer_stream(
        self,
        prompt: str,
        filename: str | None = None,
        presented_plan: str | None = None,
        recent: list[str] | None = None,
        on_delta=None,
        on_reasoning=None,
    ) -> InferredIntent:
        """Streaming variant of ``infer`` (chat SSE): identical verdict, but
        raw response fragments flow through ``on_delta`` so the service can
        preview the ``answer`` prose while the rest of the JSON generates.
        ``on_reasoning`` receives reasoning fragments (liveness signal only —
        never shown to the user, never parsed)."""
        try:
            return await self.client.generate_stream(
                messages=self._messages(prompt, filename, presented_plan, recent),
                response_model=InferredIntent,
                temperature=0.2,
                on_delta=on_delta,
                on_reasoning=on_reasoning,
            )
        except MiniMaxError:
            return self._fallback(prompt, filename)

    def _fallback(self, prompt: str, filename: str | None) -> InferredIntent:
        # Fall back to defaults so the UI never breaks. Clips need a media
        # source file, so text-only input falls back to text outputs. Every
        # slot carries a concrete language (per-slot property since the
        # 2026-08-05 restructure — no book-level field anymore).
        has_media = filename is not None and filename.lower().endswith(
            (".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a", ".aac",
             ".ogg", ".png", ".jpg", ".jpeg", ".webp")
        )
        types = (
            ["clips", "post", "quotes", "article"]
            if has_media
            else ["post", "quotes", "article"]
        )
        return InferredIntent(
            action="generate",
            answer=None,
            outputs=[IntentSlot(type=t, language="en") for t in types],  # type: ignore[arg-type]
            outputs_explicit=False,
            tone="professional",
            specific_instruction=prompt.strip() or None,
            confidence=0.0,
        )

    def _messages(
        self,
        prompt: str,
        filename: str | None,
        presented_plan: str | None,
        recent: list[str] | None,
    ) -> list[dict]:
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
            "  'generate' requires source material: when NO file is attached "
            "and the user's message is not itself source content (see "
            "material_text), never guess a task book — use action='answer' "
            "and ask what content to work from, in the user's language: they "
            "can attach files with the chat input's attachment button, or "
            "simply paste their text into the chat (pasted content is "
            "understood as material — no special formatting needed).\n"
            "- material_text: when the user's message IS their own source "
            "content — a pasted transcript, speech draft, article, or notes, "
            "with or without an explicit 'this is my …' declaration — copy "
            "that text VERBATIM into material_text (dropping any framing "
            "line like 'this is my transcript:'). A message that ASKS for "
            "something is never material, no matter how long it is. When you "
            "genuinely cannot tell whether the text is content or a request, "
            "leave material_text null and ask. Null for action='start'.\n"
            "- answer: when action is 'answer', provide a concise, helpful response "
            "(max 200 words) in the same language as the user prompt that explains "
            "the tool's capabilities and invites the user to upload or paste talk "
            "content. When action is 'generate', write ONE short sentence in the "
            "user's language stating the plan you understood — a natural "
            "paraphrase, never a stiff meta preamble (no literal 'Here's what "
            "I understood:', it translates awkwardly): e.g. \"Got it — 5 clips, "
            "3 quote cards and an article in English, dubbed into German.\" / "
            "\"好的——5 条切片、3 张金句卡和 1 篇文章，中文版，再配德语配音。\" "
            "— it is shown above the plan card as the plan's own words. Set to "
            "null only when action is 'start'. "
            "EXCEPTION — clips without media: when no media file is attached "
            "but the plan keeps a clips slot (e.g. a recipe card pinned it), "
            "the echo must ALSO tell the user, in their language: clips and "
            "voice dub need a video, audio, or image upload — they can upload "
            "one to unlock them, or remove the clips row in the plan panel "
            "and start with the text outputs only.\n"
            "- outputs: array of requested task slots — one object per "
            "requested output:\n"
            '  {"type": "clips"|"post"|"quotes"|"carousel"|"article", '
            '"count": int|null, "focus": string|null, "language": string, '
            '"tone_override": string|null, "explicit": false}\n'
            "  Default to bare slots (count/focus/tone null) for clips, post, "
            "quotes and article when unclear.\n"
            "  - language: REQUIRED on every slot — the ISO code this output "
            "is written/shown in (posts, quotes, articles: the text; clips: "
            "the subtitles). Infer from the prompt's own language or explicit "
            "requests like 'in German'; default to the prompt language, or "
            "en when unclear. Language is a PER-SLOT property — there is no "
            "book-level language field.\n"
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
            "  - Multi-version requests are the classic multi-slot case: "
            "'一版英文帖和一版德语帖' / 'an English and a German LinkedIn "
            "post' → TWO post slots, one language 'en', one language 'de'.\n"
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
            "DUBBING of their clips into other languages — the persona's own "
            "cloned voice speaking another language (e.g. '配音成德语和法语', "
            "'dub my clips into German and French', '再来一版西语配音'). "
            "Empty array otherwise. If the user asks for dubbing but names no "
            "specific languages, return an empty array — downstream defaults "
            "will apply; never invent languages. This is distinct from slot languages "
            "(which set an output's text language) — dubbing produces extra "
            "VOICE-OVER versions of the same clips. Same gating as clips: "
            "only when a media source file (video/audio/image) is attached; "
            "text-only input gets an empty array.\n"
            "  A voice-dub request ALWAYS lands in dub_languages, never in "
            "a slot's language: 'dub them into Chinese' / '配音成中文' → "
            "dub_languages ['zh']. A slot's language is the WRITTEN-text "
            "language of posts/quotes/subtitles; only change it when the "
            "user asks for the text itself in another language.\n"
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
            "expressed.\n"
            "- Key order: emit 'answer' as the FIRST key of the JSON object — "
            "it streams to the user while the rest of the object generates "
            "(null only for 'start').\n\n"
            "Return only a JSON object matching the schema."
        )

        context = f"User prompt: {prompt}"
        if filename:
            context += f"\nUploaded file: {filename}"
        else:
            context += "\nNo file uploaded (text-only input)."
        if recent:
            # The conversation's latest rounds (current message excluded) —
            # what just happened is often the disambiguator (the assistant
            # asked for material; the user then pastes it). Context only,
            # no steering: the judgment stays the model's.
            context = "Recent conversation:\n" + "\n".join(recent) + "\n\n" + context
        if presented_plan:
            context += (
                f"\nA task book has already been presented to the user and "
                f"is awaiting confirmation: {presented_plan}\n"
                f"This digest is the CURRENT book — it may include edits the "
                f"user made directly in the plan panel, which never appear in "
                f"the conversation. Emit the FULL revised book: keep every "
                f"value the user's message does not revise (quantities, "
                f"languages, angles shown in the digest), and when the "
                f"message revises a value — 'clips only needs 2', 'make the "
                f"post German', 'drop the quotes' — emit exactly that "
                f"revision. The latest user message always wins."
            )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]


plan_agent = PlanAgent()


def _params_doc(model) -> str:
    """"name: description" pairs for a params model (agent-loop-upgrade W2).

    Falls back to the bare name when a field carries no description — the
    prompt degrades to the pre-W2 shape for that field instead of breaking.
    """
    parts = []
    for fname, field in model.model_fields.items():
        parts.append(f"{fname}: {field.description}" if field.description else fname)
    return ", ".join(parts)


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
        return await self.client.generate(
            messages=self._messages(message, context),
            response_model=IntentResult,
            temperature=0.2,
        )

    async def propose_stream(
        self, message: str, context: dict, on_delta=None, on_reasoning=None
    ) -> IntentResult:
        """Streaming variant of ``propose`` (chat SSE): identical verdict, raw
        fragments flow through ``on_delta`` for the prose preview channel.
        ``on_reasoning`` receives reasoning fragments as a liveness signal.
        Repair rounds keep calling the non-streaming ``propose`` — two
        interleaved delta streams for one bubble is a worse failure than a
        text swap at the envelope."""
        return await self.client.generate_stream(
            messages=self._messages(message, context),
            response_model=IntentResult,
            temperature=0.2,
            on_delta=on_delta,
            on_reasoning=on_reasoning,
        )

    def _messages(self, message: str, context: dict) -> list[dict]:
        skills = dispatchable_skills()
        # Params are injected as "name: description" (agent-loop-upgrade W2) —
        # the Field descriptions in the registry's params models ARE the LLM's
        # parameter documentation.
        skill_lines = "\n".join(
            f"- {s.name}: {s.description}"
            + (f" (params: {_params_doc(s.params_model)})" if s.params_model else "")
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
            "change the brand template or the persona, shape D: "
            "direct them to the Brand template / Personas pages in the "
            "sidebar.\n"
            "- When the context shows a pending question, the user's message "
            "may be its answer — act on the question + answer together "
            "instead of asking again.\n"
            "- When the user references a mention (asset/output/segment), use its "
            "id in params (e.g. revise_script.target_output_id) instead of guessing.\n"
            "- Key order: within the proposal object, emit the user-facing "
            "prose field FIRST ('summary' for shapes A/B, 'text' for shape D) "
            "— it streams to the user while the rest of the JSON generates."
        )

        user_content = (
            f"Context:\n{context.get('text', '')}\n\nUser message: {message}"
        )
        if context.get("repair_feedback"):
            user_content += (
                "\n\nYour previous proposal was rejected: "
                f"{context['repair_feedback']}. Fix it and return a valid proposal."
            )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]


chat_intent_agent = ChatIntentAgent()
