"""Pipeline execution error taxonomy (agent-loop-upgrade W3).

Kept import-free so every layer (tools / node classes / orchestrator) can
share it without cycles.

**User-facing failure lines** (provider 错误人话化): exceptions carry a
``user_key`` — a machine key into ``USER_ERROR_LINES`` — and the orchestrator
bakes the localized line into ``node.error`` at fail time (the same
bake-at-write, UI-locale discipline as step summaries). Raw innards
(SQL/SQLAlchemy/httpx/pydantic dumps) stay in structlog only. Deterministic
input errors (plain ``ValueError`` sites, ``HTTPException.detail``) keep
their authored messages — a separate i18n debt, deliberately out of this
taxonomy.
"""

class TransientNodeError(Exception):
    """A retryable step failure: provider / network / storage hiccups.

    ``execute_step`` resets the node to ``pending`` (the worker's next tick is
    the backoff) when the kind carries retry budget (``NodeBase.retries``);
    anything else fails fast. Deterministic failures — missing inputs, empty
    batches, validation errors — must raise ordinary exceptions so they never
    burn retry budget.

    ``user_key`` names the user-facing line for the exhausted/terminal case.
    """

    def __init__(self, message: str, *, user_key: str | None = None) -> None:
        super().__init__(message)
        self.user_key = user_key


# Failure lines shown on the failed step row / clip card. Keys follow the
# UI locale (en/zh today); unknown locales fall back to English — the same
# fallback rule as summary_templates. Copy doctrine: plain and factual, an
# honest next step, no jargon ("provider" never appears).
USER_ERROR_LINES: dict[str, dict[str, str]] = {
    "provider_rate_limited": {
        "en": "The AI service is busy right now — please try again in a moment",
        "zh": "AI 服务正忙，请稍后重试",
    },
    "provider_quota_exhausted": {
        "en": "The AI service is out of quota — please try again later",
        "zh": "AI 服务额度已用完，请稍后再试",
    },
    "provider_unavailable": {
        "en": "The AI service is unavailable right now — please try again later",
        "zh": "AI 服务暂时不可用，请稍后重试",
    },
    "provider_unreachable": {
        "en": "Couldn't reach the AI service — please try again in a moment",
        "zh": "暂时连不上 AI 服务，请稍后重试",
    },
    "ai_unreadable": {
        # 第一人称认领 (2026-09-11 服务感): the two-strike schema rejection's
        # terminal line owns the failure instead of blaming "the AI" as a
        # third party — the assistant IS the speaker here.
        "en": "My answer came back unusable — that's on me, not you. Please try again.",
        "zh": "我给出的回答没法用——是我的问题，请再试一次",
    },
    "voice_unavailable": {
        "en": "The voice service is unavailable right now — please try again later",
        "zh": "配音服务暂时不可用，请稍后重试",
    },
    # A film narration line does not fit its scene even after the bounded
    # speed ladder — a design problem (the line is too long), never an
    # outage. The fix is a shorter line via the design beat.
    "film_narration_fit": {
        "en": "One narration line ran longer than its scene even after pacing adjustments — ask me to redesign the storyboard with a shorter line.",
        "zh": "有一句旁白调速后仍然放不下它的场景——让我重新设计分镜，把这句改短一点。",
    },
    "storage_unavailable": {
        "en": "Saving the file failed — please try again",
        "zh": "文件保存失败，请重试",
    },
    "delivery_missing": {
        "en": "The task finished without all deliverable files",
        "zh": "任务未能交付全部可用文件",
    },
    "render_upload_failed": {
        "en": "Video generated, but upload failed — retry to upload it again",
        "zh": "视频已生成，但上传失败，请重试上传",
    },
    "render_upload": {
        "en": "Upload video",
        "zh": "上传视频",
    },
    "render_recovery_required": {
        "en": "The generated video is no longer available for upload-only recovery — render it again",
        "zh": "已生成的视频缓存已不可用，无法只重传——请重新渲染",
    },
    "render_failed": {
        "en": "Video rendering failed — please try again",
        "zh": "视频渲染失败，请重试",
    },
    # Not a failure: the terminal mirror line for a render DISCARDED as
    # superseded (a morph re-pended the row mid-render) — the running step
    # settles done with this summary (rendering._mirror_superseded_node).
    "render_superseded": {
        "en": "Replaced by a newer render",
        "zh": "已被新的渲染取代",
    },
    # Poison-pill terminals (R1 B4a): the attempt cap gave up — the honest
    # next step is the manual reset (reprocess / re-render), which restarts
    # the budget.
    "processing_gave_up": {
        "en": "This file couldn't be processed after several attempts — reprocess it to start fresh.",
        "zh": "这个文件多次处理都失败了——重新处理可以从头再来。",
    },
    "render_gave_up": {
        "en": "This clip couldn't be rendered after several attempts — queue the render again to start fresh.",
        "zh": "这条视频多次渲染都失败了——重新发起渲染可以从头再来。",
    },
    "step_failed": {
        "en": "This step hit an unexpected error",
        "zh": "这一步出了意外错误",
    },
    # The film storyboard's bounded rewrite exhausted (3 candidates, each
    # rejected by the grounding validator) — the honest line names what the
    # film is made of, never the machinery.
    "film_storyboard_timeout": {
        "en": "The storyboard took too long. No production has started; ask me to retry the storyboard.",
        "zh": "分镜设计等待过久，尚未开工。可以让我重新设计分镜。",
    },
    # The design beat's capture wait outlasted its ceiling — the draft
    # refused a half-captured world; nothing was designed, nothing started.
    "film_capture_timeout": {
        "en": "I didn't finish reading the pages in time, so no storyboard was designed — ask me to design it again.",
        "zh": "网页没能及时读完，分镜尚未设计。可以让我重新设计。",
    },
    "film_storyboard_ungrounded": {
        "en": "I couldn't draft a faithful film of that page — try a page with clearer copy, or tell me what to lead with.",
        "zh": "没能为那个页面写出忠实的短片文案——换一页文案更清楚的，或告诉我先突出什么。",
    },
    "film_timing_invalid": {
        "en": "The storyboard's timing failed validation. Adjust the scene or animation timing before retrying production.",
        "zh": "分镜的时间设置未通过校验，需要调整幕长或动画时间后再制作。",
    },
    # The TEXT source's ladder terminal (素材源抽象): every candidate failed
    # the checks. The copy itself already passed the feasibility preflight,
    # so this line never blames the user's words or their named numbers —
    # it owns the miss and names what the system can do next.
    "film_text_ungrounded": {
        "en": "I couldn't arrange that text into a readable storyboard — the copy itself is fine; my layout didn't pass the checks. Ask me to try again, or tell me how to adjust it (distill the key points, change the pacing).",
        "zh": "这段文字没能排成可读的分镜——文字本身没问题，是我的编排没通过校验。可以让我重试一次，或告诉我怎么调整（比如提炼重点、换个节奏）。",
    },
    # The text source's material preflight: at the DEFAULT (natural reading)
    # pace the full copy runs past the single-film frame cap — named BEFORE
    # any design attempt, with the actions the system can actually take
    # (including the user's explicit faster-pace choice — the reading
    # estimate recommends, it never bounds). Never dressed up as the user's
    # parameter mistake.
    "film_text_beyond_reach": {
        "en": "At a natural reading pace that text runs past one film's length limit. I can distill it, you can trim it, we can split it into several films — or name a duration and I'll pace it faster (the text will move quickly).",
        "zh": "这段文字按自然语速读完会超过一支片子的时长上限。我可以提炼改编，你可以删短一些，或者我们拆成几支——也可以点名一个时长，我按更快的节奏排（文字会过得比较快）。",
    },
    # The text source's named-target preflight: the named duration is over
    # the render frame cap, or the named scene count sits outside the copy's
    # real satisfiable span (screen overflow / scenes with nothing to cite)
    # — the honest conflict plus the workable options (never a silent
    # squeeze; a named FASTER pace is legal and never lands here).
    "film_text_target_overflow": {
        "en": "That doesn't fit as named — the duration is over the film's length limit, or that scene count can't hold this copy. Adjust the number, trim the words, or let me distill it.",
        "zh": "按你点名的排不下——时长超过了片子上限，或这个幕数装不下这段文字（有真实可行区间）。可以改一下数字、删短文字，或让我提炼改编。",
    },
    # The text source's zero-copy preflight (the text film's birth gate):
    # no words arrived at all — the remedy is the copy itself or a brief.
    "film_text_empty": {
        "en": "There's no text to work from yet — paste the copy itself, or tell me what the film should say.",
        "zh": "还没有可用的文字——把文案贴进来，或告诉我片子要说什么。",
    },
    # The direction preflight found a view-poor world: the page's VISUALS
    # never captured (a blocked / timed-out browser half), rejected before
    # any LLM call. The honest remedy is a re-capture (re-sending the link
    # re-arms the hollow asset — the dedup seat's law) or user-supplied
    # shots — never clearer copy.
    "film_views_missing": {
        "en": "I couldn't capture that page's visuals — re-send the link so I can retry, or paste a few screenshots of the page and I'll design from those.",
        "zh": "那个页面的画面没能抓下来——重发一次链接让我重抓，或直接贴几张页面截图，我照着设计。",
    },
}


def user_line(key: str, ui_language: str = "en") -> str:
    """The localized user-facing line for ``key``. Unknown keys/locales fall
    back to the generic line in English."""
    lines = USER_ERROR_LINES.get(key) or USER_ERROR_LINES["step_failed"]
    lang = (ui_language or "en").lower()
    return lines.get(lang) or lines["en"]


def user_error_line(exc: BaseException, ui_language: str = "en") -> str:
    """The localized user-facing line for ``exc``:

    1. ``user_key`` attr → the keyed localized line;
    2. **exact** ``ValueError`` → the authored message passes through (our
       deterministic raise sites speak human text — but pydantic's
       ``ValidationError`` IS a ValueError subclass whose str() is a
       technical dump, so the test is the exact type, never isinstance);
    3. a string ``detail`` attr (HTTPException — duck-typed to keep this
       module import-free) → the client-facing detail passes through;
    4. everything else (TypeError / SQLAlchemy / httpx innards) → the
       generic ``step_failed`` line.
    """
    key = getattr(exc, "user_key", None)
    if key:
        return user_line(key, ui_language)
    if type(exc) is ValueError:
        return str(exc)[:500]
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail:
        return detail[:500]
    return user_line("step_failed", ui_language)


def propagate_key(cause: BaseException, default: str) -> str:
    """The wrapper-site rule: a wrapped provider error keeps its own key;
    anything else gets the wrapper's family default."""
    return getattr(cause, "user_key", None) or default


__all__ = [
    "TransientNodeError",
    "USER_ERROR_LINES",
    "user_line",
    "user_error_line",
    "propagate_key",
]
