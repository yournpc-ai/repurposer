"""Intent agents (two distinct jobs behind the SINGLE chat surface, NAMING §5).

Both are declared instances of the funnel's one sanctioned subclass
(``StreamingAgent``, N-30 — the streaming special form, N-26); the declared
fallback / the adjudication repair echo are funnel stages, not bespoke code.

``plan_agent`` — the task-book builder (plan path, CHAT_ARCH §3): free-form
text → a structured task book (language/outputs/tone) plus the three-action
verdict (generate / answer / start). Invoked only from the chat service's
plan path — first-turn projects and pending-task-book refinement turns.
Provider failures propagate as MiniMaxError: the route boundary answers 502
with the localized provider line (2026-08-14 裁定 — a fabricated default
book looks like a real plan and Start would spend a paid run on it; an
honest failure beats a wrong plan, and the user_key taxonomy makes the
failure presentable).

``chat_intent_agent`` — the chat loop's intent proposer (CHAT_ARCH §3): one
user message + assembled context → a four-state ``IntentProposal``
(task_list / edit_ops / ask / answer — N-18 + N-21). Single
tool-calling-style call per turn, never a ReAct loop; the LLM proposes and
``compile_graph`` adjudicates.
"""

from typing import Any

from app.agents.base import StreamingAgent
from app.models.schemas import InferredIntent, IntentResult
from app.operations.registry import OP_REGISTRY
from app.skills import dispatchable_skills


def _params_doc(model) -> str:
    """"name: description" pairs for a params model (agent-loop-upgrade W2).

    Falls back to the bare name when a field carries no description — the
    prompt degrades to the pre-W2 shape for that field instead of breaking.
    """
    parts = []
    for fname, field in model.model_fields.items():
        parts.append(f"{fname}: {field.description}" if field.description else fname)
    return ", ".join(parts)


def _assemble_plan_turn(
    prompt: str,
    filename: str | None = None,
    presented_plan: str | None = None,
    recent: list[str] | None = None,
):
    """Plan-turn inputs.

    ``presented_plan``: one-line digest of the docked task book, when one is
    on the table — the start/revise verdict needs to SEE the plan being
    confirmed, not imagine it (a bare "开始吧" after a vague first turn
    otherwise reads as "go generate").
    ``recent``: the conversation's latest rounds (pre-formatted lines,
    current message excluded) — the material/content judgment needs to SEE
    what just happened (e.g. the assistant asking for source material), not
    read the text in a vacuum (G-7).
    """
    return (
        {
            "prompt": prompt,
            "filename": filename,
            "presented_plan": presented_plan,
            "recent": recent,
        },
        [],
    )


def _plan_skill_lines() -> str:
    """The plan surface's skill vocabulary, registry-injected (ADR-043): the
    plan agent proposes the SAME task lists the chat loop adjudicates.
    revise_script is excluded — it targets an EXISTING output and the plan
    path runs before the project's first run, when none exist."""
    return "\n".join(
        f"- {s.name}: {s.description}"
        + (f" (params: {_params_doc(s.params_model)})" if s.params_model else "")
        for s in dispatchable_skills()
        if s.name != "revise_script"
    )


# The registries are static once imported (the skills door below opens them),
# so the system prompts are built once at declaration time.
plan_agent: StreamingAgent[InferredIntent] = StreamingAgent(
    name="plan",
    prompt="plan_agent.j2",
    schema=InferredIntent,
    system=(
        "You are an intent parser for an AI content repurposing tool. "
        "Given a user prompt, extract the user's intent and return valid JSON only.\n\n"
        "Rules:\n"
        "- action: 'generate' if the user wants to repurpose speech/talk content "
        "into assets. 'answer' if they are asking about what the tool can do, "
        "how it works, pricing, or other meta/capability questions without "
        "providing source material to repurpose. 'start' ONLY when a task "
        "book (a planned skill chain) is already on the table and the user's "
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
        "If the message asks for any modification (add/remove/change a "
        "task, a language, a focus), it is 'generate', never 'start'.\n"
        "  The prompt may accumulate several user turns; judge the action "
        "by the LAST line. When earlier turns requested work but the "
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
        "content. When action is 'generate', write the message that introduces "
        "the plan card — the card has no title of its own, this message IS "
        "the introduction: 2-4 short sentences in the user's language that "
        "(1) name what the source material is, when one is present (a talk, "
        "a podcast episode, a meeting recording — judged from the user's own "
        "words or the filename), (2) restate the plan you understood as a "
        "natural paraphrase (the work, languages, counts the user named), and "
        "(3) say the plan is below and invite review — check it, fix anything "
        "wrong directly, then start. E.g. \"Got it — this is a keynote "
        "recording, and you'd like highlight clips plus a French subtitled "
        "version. My plan is below — check it, fix anything I got wrong, "
        "then hit Start generation.\" / \"我知道了——这是一段演讲视频，要剪"
        "成高光短片，再配一版法语字幕。下面是我的生成计划：检查一遍，有理解"
        "不对的地方直接改掉，然后点击开始生成。\" Plain and warm, never a "
        "stiff meta preamble (no literal 'Here's what I understood:', it "
        "translates awkwardly). Set to null only when action is 'start'. "
        "EXCEPTION — media work without media: when no media file is "
        "attached but the plan keeps media-needing tasks (clips, subtitles, "
        "dubbing — e.g. a recipe card pinned them), the echo must ALSO tell "
        "the user, in their language: clips and voice dub need a video, "
        "audio, or image upload — they can upload one to unlock them, or "
        "remove that row in the plan panel and start with the text work "
        "only.\n"
        "- tasks: array of tasks — the skill chain to run, one object per "
        "piece of work, in execution order: "
        '{"skill": "<name>", "params": {...}}.\n'
        "  Available skills:\n" + _plan_skill_lines() + "\n"
        "  Rules:\n"
        "  - Propose the FEWEST tasks that express the request. Never "
        "invent skills or params not in the list.\n"
        "  - WHOLE-SOURCE vs HIGHLIGHTS: when the user asks to TRANSFORM "
        "their video/audio as a whole — add subtitles, dub it, remove "
        "filler, add music ('给我的视频加中英双语字幕', 'subtitle my talk "
        "in French', 'dub this into German') — propose the transform "
        "skill(s) ALONE, never select_clips: the system materializes the "
        "whole source itself. Add select_clips ONLY when the user wants "
        "highlight clips cut; transforms after it then act on the clips "
        "([select_clips, translate_clip] = subtitled highlight clips).\n"
        "  - Default chain when the request is vague ('帮我做内容', "
        "'repurpose this'): with a media file attached → select_clips, "
        "write_post, write_quotes, write_article; text only → write_post, "
        "write_quotes, write_article. Set tasks_explicit false in this "
        "case.\n"
        "  - Media gating: select_clips / translate_clip / dub_clip / "
        "remove_filler / add_music need an attached media file (video, "
        "audio, or image). Text-only input → writer skills only.\n"
        "  - Language is a per-task param: write_* skills take 'language' "
        "(the text's language); select_clips takes 'language' (on-screen "
        "copy — captions always follow the spoken words); translate_clip / "
        "dub_clip take 'target_language' (required). Default to the "
        "prompt's own language; 'in German' sets that task's language.\n"
        "  - Subtitles vs dubbing: '中文字幕' / 'subtitles in Chinese' → "
        "translate_clip (TEXT on screen); '中文配音' / 'dub into Chinese' "
        "→ dub_clip (VOICE). Bilingual side-by-side subtitles ('双语字幕', "
        "'中英对照', 'bilingual subtitles') → translate_clip with "
        "bilingual: true.\n"
        "  - Multi-version requests are repeated skills with different "
        "params: '一版英文帖和一版德语帖' / 'an English and a German "
        "post' → TWO write_post tasks (language 'en' and 'de'); '字幕译成"
        "德语和法语' → two translate_clip tasks.\n"
        "  - Counts ride params: '5 clips' → select_clips count 5; '8 张金"
        "句卡' → write_quotes count 8; 'a 10-slide carousel' → "
        "write_carousel count 10. Omit count when unnamed.\n"
        "  - Frame format ('竖版/vertical', '方形/square', '横版/16:9/', "
        "'保持原画幅/keep the original frame' → the value matching the "
        "source's shape) → select_clips params.aspect.\n"
        "  - Angle / tone ride params: '切片剪定价争议' → select_clips "
        "focus 'pricing debate'; '帖子正式一点' → write_post tone_override "
        "'formal'.\n"
        "  - When a plan is already presented (the prompt carries it as a "
        "JSON task chain), output the WHOLE refined chain: preserve every "
        "task the user's message does not revise — the presented chain may "
        "carry the user's hand edits, and losing one is a bug.\n"
        "- tasks_explicit: true only when the user explicitly named the "
        "work themselves (e.g. 'just clips', 'a post and quotes'). false "
        "when the chain is your default proposal.\n"
        "- specific_instruction: a short distilled EXTRA instruction for "
        "the generator — only constraints or focus NOT already expressed "
        "by the task params (e.g. 'focus on the Q&A section', 'the "
        "audience is first-time founders'). NEVER restate the requested "
        "work itself: 'cut the talk into highlight clips' is already the "
        "select_clips task, 'dub into Chinese' is already the dub_clip "
        "task — repeating them here produces a confusing redundant "
        "book-level instruction. null when nothing extra remains. For "
        "action='answer' or 'start', set this to null.\n"
        "- confidence: 0.0-1.0 indicating how clearly the intent was "
        "expressed.\n"
        "- Key order: emit 'answer' as the FIRST key of the JSON object — "
        "it streams to the user while the rest of the object generates "
        "(null only for 'start').\n\n"
        "Return only a JSON object matching the schema."
    ),
    temperature=0.2,
    assemble=_assemble_plan_turn,
)


def _chat_intent_system() -> str:
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
    return (
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
        "change the persona (style, voice, or skin), shape D: "
        "direct them to the Personas page in the sidebar.\n"
        "- When the context shows a pending question, the user's message "
        "may be its answer — act on the question + answer together "
        "instead of asking again.\n"
        "- When the user references a mention (asset/output/segment), use its "
        "id in params (e.g. revise_script.target_output_id) instead of guessing.\n"
        "- When the context names a current focus output, an edit or work "
        "request that names no other target (no mention, no explicit "
        "reference) targets the focus output.\n"
        "- Key order: within the proposal object, emit the user-facing "
        "prose field FIRST ('summary' for shapes A/B, 'text' for shape D) "
        "— it streams to the user while the rest of the JSON generates."
    )


def _assemble_chat_turn(message: str, context: dict[str, Any]):
    """Chat-turn inputs: the user message plus the deterministic context
    digest (``agents/contexts.py``). Adjudication feedback never passes
    through here — it is the funnel's reserved ``repair_feedback`` kwarg."""
    return ({"context_text": context.get("text", ""), "message": message}, [])


chat_intent_agent: StreamingAgent[IntentResult] = StreamingAgent(
    name="chat_intent",
    prompt="chat_intent.j2",
    schema=IntentResult,
    system=_chat_intent_system(),
    temperature=0.2,
    assemble=_assemble_chat_turn,
)
