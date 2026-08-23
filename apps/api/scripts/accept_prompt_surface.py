"""Prompt-surface verification (08-21 gate, recipe-gallery v2): every
recipe-card prefilled template → plan path → does the proposed task book
reliably include the card's expected node kinds?

Mirrors the gallery (recipe-gallery-v2 brief §6): a fresh project with
the card's declared input asset, first message = the card's template
copy. 3 zh + 3 en trials per card (LLM variance — one run is a coin
flip, never a verdict). Plan-only: no book is ever confirmed, nothing
renders.

Each card declares its ``expected_tools`` list — the validator asserts
all of those tool kinds appear in the compiled plan, in order. The card's
own ``RecipeEntry.tasks`` (the registry's declared compile shape,
ADR-043) stays the design-time truth; the validator just confirms the
template INFERRED that shape from the user's free-form message.

Recipe gallery v2 additions:
- voice-dub is now in scope (was merged back into a card on 2026-08-23,
  ADR-048 §4.5).
- The text-tribe cards (social-post / quote-cards / carousel) are
  referenced as DRAFT entries below — they stay commented until the
  bake harvest lands (recipe-gallery-v2 brief §6: "拿不出成对示例的卡
  不进网格"). When the entries uncomment, the gate will test them.
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_scenarios import Ctx, make_user, seed_asset, pending_book, book_tasks
from app.models.schemas import AssetType

# Per-card expected plan shape. ``expected_tools`` is an ORDERED subset of
# the card's RecipeEntry.tasks — every kind here must appear, in this
# relative order. The validator never asserts the absence of OTHER tools
# (the chat path may pick adjacent helpers like add_music / remove_filler).
CARDS = {
    "访谈分镜/reframe": {
        "asset_type": AssetType.VIDEO,
        "asset": "xy_1-interview.mp4",
        "expected_tools": ["select_clips", "reframe_clip"],
        "templates": [
            ("zh", "把我的双人访谈剪成竖屏短片，镜头跟着说话人切换。"),
            ("en", "Recut my two-person interview into vertical clips that follow whoever is speaking."),
        ],
    },
    "高光切片/highlight-clips": {
        "asset_type": AssetType.VIDEO,
        "asset": "xy_2-keynote.mp4",
        "expected_tools": ["select_clips", "reframe_clip"],
        "templates": [
            ("zh", "帮我把这个视频里最好的几段剪出来，做成竖屏短片，镜头跟着人走。"),
            ("en", "Find the best moments of this video and cut them into vertical clips — the camera follows the speaker."),
        ],
    },
    # Recipe-gallery v2 (ADR-048, 2026-08-23): the dub card is back to its
    # own seat. The validator checks the template infers a `dub_clip` task
    # — voice-cloning is the dish's moat; the template must produce at
    # least one dub variant.
    "原声AI配音/voice-dub": {
        "asset_type": AssetType.VIDEO,
        "asset": "demo_talk.mp4",
        "expected_tools": ["dub_clip"],
        "templates": [
            (
                "zh",
                "把我的演讲用我的声音配音成西班牙语和法语——原声轨留着顶在头上，方便我听自然度。",
            ),
            (
                "en",
                "Dub my talk into Spanish and French in my own voice — keep the original soundtrack on top so I can hear how natural it sounds.",
            ),
        ],
    },
    # === DRAFT: text-tribe cards — uncomment when the bake harvest lands. ===
    # Brief §6: "新卡未过「成对示例烘焙 + 验收闸全绿」双闸，禁止注册进 recipes.py"
    # The entries below assume the eventual asset is a transcript article.
    # Pre-bake referencing them would test a template against unregistered
    # cards — wrong-shaped invariant. When the bake finishes, flip these on.
    #
    # "社媒帖/social-post": {
    #     "asset_type": AssetType.TRANSCRIPT,
    #     "asset": "demo-article.md",
    #     "expected_tools": ["write_post"],
    #     "templates": [
    #         (
    #             "zh",
    #             "把这段演讲变成 LinkedIn 帖，按我的风格来。哪个平台发——你选合适的就行。",
    #         ),
    #         (
    #             "en",
    #             "Turn this talk into a LinkedIn post in my style. The platform is up to you — pick whatever fits.",
    #         ),
    #     ],
    # },
    # "金句卡/quote-cards": {
    #     "asset_type": AssetType.TRANSCRIPT,
    #     "asset": "demo-article.md",
    #     "expected_tools": ["write_quotes"],
    #     "templates": [
    #         ("zh", "从这场演讲里挑最亮的金句，做成可以直接发的金句卡。"),
    #         ("en", "Pull the strongest quotes from this talk and turn them into quote cards ready to share."),
    #     ],
    # },
    # "轮播图/carousel": {
    #     "asset_type": AssetType.TRANSCRIPT,
    #     "asset": "demo-article.md",
    #     "expected_tools": ["write_carousel"],
    #     "templates": [
    #         ("zh", "把这场演讲做成一组轮播幻灯——一图一意，可以直接发。"),
    #         ("en", "Turn this talk into a carousel of slides — one idea per slide, ready to post."),
    #     ],
    # },
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


async def one_trial(
    ctx: Ctx, card: str, lang: str, message: str, expected: list[str]
) -> tuple[bool, list, dict]:
    pid = await ctx.new_project(f"prompt-surface {card} {lang}")
    cfg = CARDS[card]
    await seed_asset(
        pid,
        ctx.user_id,
        cfg["asset_type"],
        cfg["asset"],
        meta={"language": "zh" if lang == "zh" else "en"},
    )
    turn = await ctx.chat(pid, message)
    book = await pending_book(ctx, pid)
    tasks = book_tasks(book)
    kinds = [t.get("tool") for t in tasks]

    # Ordered subset check: every expected kind must appear, in declared
    # order. Adjacent helpers the chat path sneaks in (add_music /
    # remove_filler / etc.) don't fail the gate.
    indices = []
    for exp in expected:
        if exp not in kinds:
            return False, kinds, turn
        indices.append(kinds.index(exp))
    ok = indices == sorted(indices)
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
                        ok, kinds, turn = await one_trial(
                            ctx, card, lang, template, cfg["expected_tools"]
                        )
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
