"""Prompt-surface verification (08-21 gate, recipe-gallery v2): every
recipe-card prefilled template → plan path → does the proposed task book
reliably include the card's expected node kinds?

Mirrors the gallery (recipe-gallery-v2 brief §6): a fresh project with
the card's declared input asset, first message = the card's template
copy. TRIALS_PER_LANG trials per language (LLM variance — one run is a
coin flip, never a verdict). Per-card ``trials`` overrides the default.
Plan-only: no book is ever confirmed, nothing renders.

Each card declares its ``expected_tools`` list — the validator asserts
all of those tool kinds appear in the compiled plan, in order. The card's
own ``RecipeEntry.tasks`` (the registry's declared compile shape,
ADR-043) stays the design-time truth; the validator just confirms the
template INFERRED that shape from the user's free-form message.

Recipe gallery v2 additions:
- voice-dub is now in scope (was merged back into a card on 2026-08-23,
  ADR-048 §4.5).
- The text-tribe cards (social-post / quote-cards / carousel) landed
  2026-08-24 (recipes/tasks/text-tribe-live.md): bake harvest + skill
  packs + 12/12 prompt-surface gate = status flipped from reserved to
  live. The gate asserts each writer template lands on its own writer
  kind only (no write_post / write_quotes / write_carousel cross-talk).
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
            (
                "zh",
                "用上传的双人对话录像（最佳为左右对坐的访谈或对谈节目，横屏）剪 2-4 段竖屏分镜——每段独立成片，9:16：说话人切换 = 静态分镜模式：检测当前说话人（左侧或右侧），镜头切换到对应人物；切换要平滑（最短驻留 + 缓动），不要硬切眩晕；竖屏构图 = 单人在画面中央偏上，下方留字幕空间，不要塞两个人在画面里；字幕 = 单行替换（catalog 6 种样式可换），字号按画幅等比缩放，左右边距 8%；横竖比转换 = 9:16 object-contain 不裁切，上下留黑保原比例。输出 = 2-4 段竖屏短片，每段覆盖一次完整的话轮切换（提问→回答），原视频保留不动。",
            ),
            (
                "en",
                "From the uploaded two-person conversation recording (landscape left-right interview / talk show works best), cut 2-4 vertical reframe clips — each a separate 9:16 clip: speaker switching = static-reframe mode: detect who's currently speaking (left or right), cut to that person; transitions must be smooth (min dwell + easing), no jarring hard cuts; vertical framing = single speaker centered upper-middle, caption space below — don't try to fit both in frame; captions = single-line replacement (catalog 6 presets), font size scales with frame, 8% side margins; aspect conversion = 9:16 object-contain, letterboxed, source frame preserved. Output = 2-4 vertical clips, each covering one complete turn switch (question → answer); original video untouched.",
            ),
        ],
    },
    "高光切片/highlight-clips": {
        "asset_type": AssetType.VIDEO,
        "asset": "xy_2-keynote.mp4",
        "expected_tools": ["select_clips", "reframe_clip"],
        "templates": [
            (
                "zh",
                "用上传的长演讲视频（最佳为大型中景登台演讲）剪 3-5 段高光切片——每段独立成片，竖屏 9:16：选段标准 = 信息密度最高的几个瞬间（结论性句子、关键数据点、最有共鸣的表达），agent 标出首推段（最值得先发的）；竖屏构图 = 镜头自动跟人（reframe_clip dynamic mode），speaker 居中偏上，下方留出字幕空间，不要固定中央裁切；字幕 = 单行替换（catalog 6 种样式可换），字号按画幅等比缩放（皮肤默认 68），左右边距 8%，不要堆叠；横竖比转换 = 9:16 渲染端按帧高缩放，原画幅用 object-contain 不裁切，上下留黑。输出 = 3-5 段独立短片，每段 15-60 秒，原视频保留不动。",
            ),
            (
                "en",
                "From the uploaded long talk recording (large mid-shot stage talk works best), cut 3-5 highlight clips — each a separate vertical 9:16 clip: selection = highest information-density moments (concluding statements, key data points, most resonant lines); agent flags the top pick (the one to post first); vertical framing = camera follows the speaker automatically (reframe_clip dynamic mode), speaker centered upper-middle, caption space below — not fixed center-crop; captions = single-line replacement (catalog 6 presets), font size scales with frame (skin default 68), 8% side margins — no stacking; aspect conversion = 9:16 scales by frame height, source frame letterboxed via object-contain, no crop. Output = 3-5 short clips, each 15-60 seconds; original video untouched.",
            ),
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
                "用上传的整段视频做 3 版 AI 配音——每版独立成片，原始视频不动：中文版（用我的声音从原声克隆声纹替换原音轨，ZH 单行字幕），法语版（同上 FR），西语版（同上 ES）。3 版都保留我的音色指纹——AI 通用合成声不要。原声轨作为对照层压在主轨之下，方便我对照自然度。1:1 原画幅不裁切，上下留黑保原比例。字幕字号按画幅等比缩放（皮肤默认 68 → 1:1 得 38），左右边距 8%。声画对齐按 ASR 词级时间戳回配，不要音画漂移。",
            ),
            (
                "en",
                "From the uploaded full video, make 3 voice-cloned dub versions — each a separate clip, source untouched: ZH dub (replace original audio with my cloned voice from the source, ZH single-line captions), FR dub (same, French), ES dub (same, Spanish). All 3 keep my voice fingerprint — no stock narrator. The original soundtrack stays as a reference layer below the main track so I can hear how natural the clone sounds. Keep the 1:1 source frame, letterboxed, never cropped. Caption font size scales with frame (skin default 68 → 38 at 1:1), 8% side margins. Audio re-times to ASR word-level timestamps — no drift.",
            ),
        ],
    },
    # === Text-tribe (RECIPES §4.6, 2026-08-24 12/12 gate) ===
    # Each writer template must land on its own writer kind only — the
    # chain is single-task, no select_clips / clip tools to confuse the
    # LLM, so a leak into write_article / dub_clip / etc. is the gate's
    # failure mode. 2 trials per language × 3 cards × 2 langs = 12.
    "社媒帖/social-post": {
        "asset_type": AssetType.TRANSCRIPT,
        "asset": "demo-article.md",
        "expected_tools": ["write_post"],
        "trials": 2,
        "templates": [
            (
                "zh",
                "把这段演讲变成 LinkedIn 帖，按我的风格来。哪个平台发——你选合适的就行。",
            ),
            (
                "en",
                "Turn this talk into a LinkedIn post in my style. The platform is up to you — pick whatever fits.",
            ),
        ],
    },
    "金句卡/quote-cards": {
        "asset_type": AssetType.TRANSCRIPT,
        "asset": "demo-article.md",
        "expected_tools": ["write_quotes"],
        "trials": 2,
        "templates": [
            ("zh", "从这场演讲里挑最亮的金句，做成可以直接发的金句卡。"),
            ("en", "Pull the strongest quotes from this talk and turn them into quote cards ready to share."),
        ],
    },
    "轮播图/carousel": {
        "asset_type": AssetType.TRANSCRIPT,
        "asset": "demo-article.md",
        "expected_tools": ["write_carousel"],
        "trials": 2,
        "templates": [
            ("zh", "把这场演讲做成一组轮播幻灯——一图一意，可以直接发。"),
            ("en", "Turn this talk into a carousel of slides — one idea per slide, ready to post."),
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
            trials = cfg.get("trials", TRIALS_PER_LANG)
            for lang, template in cfg["templates"]:
                for i in range(trials):
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
