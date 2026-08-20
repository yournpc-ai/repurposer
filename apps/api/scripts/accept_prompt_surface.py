"""Prompt-surface verification (08-21 gate): recipe-card prefilled template →
plan path → does the proposed task book reliably include reframe_clip?

Mirrors the twin cards' launch (RECIPES §4.3): a fresh project with a video
asset, first message = the card's template copy. 3 zh + 3 en trials per card
(LLM variance — one run is a coin flip, never a verdict). Plan-only: no book
is ever confirmed, nothing renders.
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_scenarios import Ctx, make_user, seed_asset, pending_book, book_tasks
from app.models.schemas import AssetType

CARDS = {
    # The twin cards' real promptTemplate strings （配方 = 提示词 — the
    # template IS the launch payload; the API registry never carries them).
    # _assert_templates_in_sync() below enforces these equal the web locales
    # verbatim — a gate testing a paraphrase proves a paraphrase, not the
    # card; a stale mirror certifies a string the card no longer launches.
    "访谈分镜/reframe": {
        "asset": "xy_1-interview.mp4",
        "templates": [
            ("zh", "把我的双人访谈剪成竖屏短片，镜头跟着说话人切换。"),
            ("en", "Recut my two-person interview into vertical clips that follow whoever is speaking."),
        ],
    },
    "高光切片/highlight-clips": {
        "asset": "xy_2-keynote.mp4",
        "templates": [
            ("zh", "帮我把这个视频里最好的几段剪出来，做成竖屏短片，镜头跟着人走。"),
            ("en", "Find the best moments of this video and cut them into vertical clips — the camera follows the speaker."),
        ],
    },
}
TRIALS_PER_LANG = 3

_LOCALES = Path(__file__).resolve().parents[3] / "apps/web/src/lib/i18n/locales"


def _card_block(src: str, card_id: str) -> str:
    """The card's i18n block (quoted or bare key), up to its closing brace."""
    m = re.search(rf'(?:"{re.escape(card_id)}"|{re.escape(card_id)}):\s*\{{(.*?)\n\s*\}}', src, re.S)
    if not m:
        raise SystemExit(f"card block not found in locale: {card_id}")
    return m.group(1)


def _locale_template(lang: str, card_id: str) -> str:
    """promptTemplate straight from the locale file (single- or multi-line)."""
    src = (_LOCALES / f"{lang}.ts").read_text()
    m = re.search(r'promptTemplate:\s*\n?\s*"((?:[^"\\]|\\.)*)"', _card_block(src, card_id))
    if not m:
        raise SystemExit(f"promptTemplate not found: {lang} {card_id}")
    return m.group(1)


def _assert_templates_in_sync() -> None:
    """Drift guard: CARDS mirrors the locales BY HAND — fail loud when an
    edit to the real copy leaves the gate testing its own stale strings."""
    drift = []
    for label, cfg in CARDS.items():
        card_id = label.split("/")[-1]
        for lang, template in cfg["templates"]:
            real = _locale_template(lang, card_id)
            if real != template:
                drift.append(f"{card_id}/{lang}:\n  gate:   {template!r}\n  locale: {real!r}")
    if drift:
        raise SystemExit("gate templates out of sync with web locales:\n" + "\n".join(drift))


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
    _assert_templates_in_sync()
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


if __name__ == "__main__":
    asyncio.run(main())
