"""Reproduce the caption-recipe intent_router turn (2026-09-10 走查失败取证).

User 实拍：caption 配方卡原样发送 → 回声散文到达 → "Drafting the plan…"
冻住（修复轮隐形窗）→ turn.failed "ai_unreadable"（MiniMaxSchemaError
两连败）。本脚本用原样 promptTemplate + 当时的 filename/file_language
上下文直连 intent_router，抓模型原始输出与校验错误。

只读 LLM 调用——无 DB、无 run。用法（apps/api/ 下，API 无需在跑）：
    uv run python scratch/repro_caption_router.py [N次，默认5]
"""

import asyncio
import sys

from app.chat.intent import intent_router

PROMPT = (
    "From the uploaded full video (demo source 1:1), make 4 multilingual "
    "caption versions — each a separate clip, source untouched: EN original "
    "(English voice + English single-line captions, keep 1:1 frame); ZH "
    "bilingual (Chinese translation on the main line at font ×0.82 with "
    "English original below at ×0.55, translation_track; title overlays "
    "translated to Chinese); FR single-line (French single-line captions, "
    "original soundtrack stays untouched); ES dub (replace original audio "
    "with my cloned voice from the source, ES single-line captions; keep my "
    "voice fingerprint — no stock narrator). Caption font size scales with "
    "frame (skin default 68 → 38 at 1:1), 8% side margins. Bilingual uses "
    "stack layout with only the translation track + a smaller English line — "
    "no stacked wall. All versions stay at 1:1 source frame, letterboxed, "
    "never cropped."
)


async def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    for i in range(n):
        try:
            intent = await intent_router.call(
                message=PROMPT,
                brief=None,
                persona=None,
                pending_question=None,
                filename="xy_1.mp4",
                presented_book=None,
                recent=None,
                file_language="en",
                material_excerpt=None,
            )
            print(
                f"[{i}] OK action={intent.action} "
                f"tasks={[(t.tool, t.params) for t in intent.tasks]} "
                f"name={intent.name!r}"
            )
        except Exception as e:  # noqa: BLE001 — 取证脚本，全类型都要看
            print(f"[{i}] FAIL {type(e).__name__}")
            print(str(e)[:3000])
            print("---")


asyncio.run(main())
