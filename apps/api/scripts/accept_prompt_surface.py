"""Prompt-surface verification (08-21 gate): recipe-card prefilled template →
plan path → does the proposed task book reliably include reframe_clip?

Mirrors the future twin cards' launch (RECIPES §4.3): a fresh project with a
video asset, first message = the card's template copy. 3 zh + 3 en trials per
card (LLM variance — one run is a coin flip, never a verdict). Plan-only:
no book is ever confirmed, nothing renders.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_scenarios import Ctx, make_user, seed_asset, pending_book, book_tasks
from app.models.schemas import AssetType

CARDS = {
    # The twin cards' real promptTemplate strings （配方 = 提示词 — the
    # template IS the launch payload; the API registry never carries them,
    # so this gate mirrors the web locales by hand and must stay in sync
    # with apps/web/src/lib/i18n/locales/{en,zh}.ts).
    "访谈分镜/reframe": {
        "asset": "xy_1-interview.mp4",
        "templates": [
            ("zh", "把我的双人访谈剪成竖屏短片，镜头跟着说话人切换。"),
            ("en", "Recut my two-person interview into vertical clips that follow whoever is speaking."),
        ],
    },
    "演讲短片/highlight-clips": {
        "asset": "xy_2-keynote.mp4",
        "templates": [
            ("zh", "帮我把这个视频里最好的几段剪出来，做成竖屏短片，镜头跟着人走。"),
            ("en", "Find the best moments of this video and cut them into vertical clips — the camera follows the speaker."),
        ],
    },
}
TRIALS_PER_LANG = 3


async def one_trial(ctx: Ctx, card: str, lang: str, message: str) -> tuple[bool, list, dict]:
    pid = await ctx.new_project(f"prompt-surface {card} {lang}")
    await seed_asset(pid, ctx.user_id, AssetType.VIDEO, CARDS[card]["asset"],
                     meta={"language": "zh" if lang == "zh" else "en"})
    turn = await ctx.chat(pid, message)
    book = await pending_book(ctx, pid)
    tasks = book_tasks(book)
    kinds = [t.get("skill") for t in tasks]
    ok = "select_clips" in kinds and "reframe_clip" in kinds and (
        kinds.index("reframe_clip") > kinds.index("select_clips")
    )
    return ok, kinds, turn


async def main() -> None:
    user = await make_user()
    ctx = Ctx(user, keep=False)
    passed = failed = 0
    try:
        for card, cfg in CARDS.items():
            for lang, template in cfg["templates"]:
                for i in range(TRIALS_PER_LANG):
                    try:
                        ok, kinds, turn = await one_trial(ctx, card, lang, template)
                    except Exception as e:
                        ok, kinds, turn = False, [f"ERROR: {e}"], None
                    passed += ok
                    failed += not ok
                    print(
                        f"{'PASS' if ok else 'FAIL'} {card} {lang}#{i + 1}: {kinds}",
                        flush=True,
                    )
                    if not ok and turn:
                        am = turn["assistant_message"]
                        print(f"    content: {am.get('content')!r}", flush=True)
                        print(f"    question: {am.get('question')!r}", flush=True)
                        print(f"    intent: {am.get('intent')!r}", flush=True)
    finally:
        await ctx.cleanup()
        await ctx.close()
    print(f"\n== {passed} pass / {failed} fail of {passed + failed} ==", flush=True)
    sys.exit(1 if failed else 0)


asyncio.run(main())
