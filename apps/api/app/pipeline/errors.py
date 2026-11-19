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
    "provider_image_outcome_unknown": {
        "en": (
            "The image request may have been processed, but its result is unconfirmed. "
            "No second request was sent and no image was delivered. Check AI service "
            "usage before explicitly regenerating."
        ),
        "zh": (
            "图片请求可能已执行，但结果未确认。系统未再次提交，也未交付图片；"
            "请核对 AI 服务用量后，再决定是否明确重新生成。"
        ),
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
    "narration_window_conflict": {
        "en": "This scene's narration is too long for its reviewed cut. The cut and text were not changed; shorten the narration before producing again.",
        "zh": "这一幕的旁白超过了已确认的镜头长度。镜头和文字均未改动；请缩短旁白后再制作。",
    },
    "narration_budget_exceeded": {
        "en": "This production needs more narration characters than its authorized quote. No extra synthesis was submitted; revise the narration or explicitly authorize a new production.",
        "zh": "本次制作需要的旁白字符数超出已授权报价。系统未提交额外合成；请修改旁白，或明确授权一次新的制作。",
    },
    "provider_narration_outcome_unknown": {
        "en": "The narration request may have been processed, but its result is unconfirmed. No second request was sent and no audio was delivered. Check voice-service usage before explicitly trying again.",
        "zh": "旁白请求可能已执行，但结果未确认。系统未再次提交，也未交付音频；请核对配音服务用量后，再决定是否明确重试。",
    },
    # A film narration line does not fit its scene even after the bounded
    # speed ladder — a design problem (the line is too long), never an
    # outage. The fix is a shorter line via the design beat.
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
    "audio_loudness_failed": {
        "en": "The audio was generated. Loudness and true peak could not be verified for playback.",
        "zh": "音频已生成。响度与真峰值校验失败，试听交付已暂停。",
    },
    # The film storyboard's bounded rewrite exhausted (3 candidates, each
    # rejected by the grounding validator) — the honest line names what the
    # film is made of, never the machinery.
    # The design beat's capture wait outlasted its ceiling — the draft
    # refused a half-captured world; nothing was designed, nothing started.
    # The TEXT source's ladder terminal (素材源抽象): every candidate failed
    # the checks. The copy itself already passed the feasibility preflight,
    # so this line never blames the user's words or their named numbers —
    # it owns the miss and names what the system can do next.
    # The text source's material preflight: at the DEFAULT (natural reading)
    # pace the full copy runs past the single-film frame cap — named BEFORE
    # any design attempt, with the actions the system can actually take
    # (including the user's explicit faster-pace choice — the reading
    # estimate recommends, it never bounds). Never dressed up as the user's
    # parameter mistake.
    # The text source's named-target preflight: the named duration is over
    # the render frame cap, or the named scene count sits outside the copy's
    # real satisfiable span (screen overflow / scenes with nothing to cite)
    # — the honest conflict plus the workable options (never a silent
    # squeeze; a named FASTER pace is legal and never lands here).
    # The text source's zero-copy preflight (the text film's birth gate):
    # no words arrived at all — the remedy is the copy itself or a brief.
    # The direction preflight found a view-poor world: the page's VISUALS
    # never captured (a blocked / timed-out browser half), rejected before
    # any LLM call. The honest remedy is a re-capture (re-sending the link
    # re-arms the hollow asset — the dedup seat's law) or user-supplied
    # shots — never clearer copy.
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
