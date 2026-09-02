"""Prompt-surface verification (08-21 gate, recipe-gallery v2): every
recipe-card prefilled template → book path → does the proposed task book
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
- 2026-08-24 dual-template split (RECIPES §7.2): copy-writer cards ship
  TWO locale templates — ``promptTemplate`` (no-material beginner voice)
  and ``promptTemplateWithMaterial`` (specific, grounded). The composer
  picks by file attachment at launch time; the gate tests both, asserting
  each one independently maps to the same writer kind (no cross-talk).
  Cards without dual templates keep a flat ``templates`` list.
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_scenarios import Ctx, book_tasks, make_user, pending_book, seed_asset

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
    # failure mode. 2026-08-24 dual-template split (RECIPES §7.2): the
    # composer picks by file attachment at launch — ``variants`` carries
    # both voices and the gate tests them independently.
    # 2 trials × 3 cards × 2 langs × 2 variants = 24 trials.
    "社媒帖/social-post": {
        "asset_type": AssetType.TRANSCRIPT,
        "asset": "demo-article.md",
        "expected_tools": ["write_post"],
        "trials": 2,
        "variants": {
            "no_material": [
                ("zh", "帮我写一条社媒帖。"),
                ("en", "I want a social post."),
            ],
            "with_material": [
                (
                    "zh",
                    "把这段素材写成一条社媒帖，按我的风格来。哪个平台发——你选合适的就行。纯文本——不要 Markdown（不要 **加粗** / _斜体_ / # 标题 / [链接](url) / 代码块）；主流社交平台都把 Markdown 当源文渲染，看起来是碎的。",
                ),
                (
                    "en",
                    "Turn my source into a social post in my style. The platform is up to you — pick whatever fits. Plain text only — no Markdown (no **bold**, _italic_, # headers, [links](url), or code blocks); every mainstream social platform renders Markdown as raw source, which looks broken.",
                ),
            ],
        },
    },
    "金句卡/quote-cards": {
        "asset_type": AssetType.TRANSCRIPT,
        "asset": "demo-article.md",
        "expected_tools": ["write_quotes"],
        "trials": 2,
        "variants": {
            "no_material": [
                # 2026-08-25 Phase 4 — bilingual default example (real
                # bilingual user voice). Recipe contract: video + transcript
                # required; the no-material template is what users see BEFORE
                # attaching files (intent preview); chat docks for material.
                ("zh", "做一张中英双语金句卡。"),
                ("en", "Make a bilingual quote card."),
            ],
            "with_material": [
                (
                    "zh",
                    "从我的演讲里挑几句最亮的，做成中英双语金句卡。",
                ),
                (
                    "en",
                    "From my talk, pick the sharpest lines and turn them into a bilingual quote card.",
                ),
            ],
        },
    },
    "轮播图/carousel": {
        "asset_type": AssetType.TRANSCRIPT,
        "asset": "demo-article.md",
        "expected_tools": ["write_carousel"],
        "trials": 2,
        "variants": {
            "no_material": [
                ("zh", "帮我做一组轮播。"),
                ("en", "I want a carousel."),
            ],
            "with_material": [
                ("zh", "把这段素材做成一组轮播幻灯——一图一意，可以直接发。"),
                (
                    "en",
                    "Turn my source into a carousel of slides — one idea per slide, ready to post.",
                ),
            ],
        },
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


def _locale_template(lang: str, card_id: str, key: str = "promptTemplate") -> str:
    """The card's prompt template straight from the locale file. ``key`` is
    either ``promptTemplate`` (no-material voice) or
    ``promptTemplateWithMaterial`` (with-material voice, copy-writer
    dual-template split). Both follow the same ``key:``/value layout in
    the locale block — same regex, same multi-line tolerant."""
    src = (_LOCALES / f"{lang}.ts").read_text()
    m = re.search(rf'{re.escape(key)}:\s*\n?\s*"((?:[^"\\]|\\.)*)"', _card_block(src, card_id))
    if not m:
        raise SystemExit(f"{key} not found: {lang} {card_id}")
    return m.group(1)


def _assert_templates_in_sync() -> None:
    """Drift guard: CARDS mirrors the locales BY HAND — fail loud when an
    edit to the real copy leaves the gate testing its own stale strings.

    Cards with a flat ``templates`` list read from ``promptTemplate``.
    Cards with a ``variants`` dict (copy-writer dual-template split) read
    from ``promptTemplate`` + ``promptTemplateWithMaterial`` per variant
    key — both must stay in lockstep with the locale."""
    drift = []
    for label, cfg in CARDS.items():
        card_id = label.split("/")[-1]
        if "variants" in cfg:
            for variant_key, entries in cfg["variants"].items():
                locale_key = (
                    "promptTemplateWithMaterial"
                    if variant_key == "with_material"
                    else "promptTemplate"
                )
                for lang, template in entries:
                    real = _locale_template(lang, card_id, locale_key)
                    if real != template:
                        drift.append(
                            f"{card_id}/{lang}/{variant_key}:\n  gate:   {template!r}\n  locale: {real!r}"
                        )
        else:
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
            # Dual-template cards (RECIPES §7.2): flatten the variants into
            # (variant, lang, template) tuples so the trial loop stays linear.
            # The variant tag rides the log line for the gate report.
            if "variants" in cfg:
                entries: list[tuple[str, str, str]] = [
                    (variant_key, lang, template)
                    for variant_key, items in cfg["variants"].items()
                    for lang, template in items
                ]
            else:
                entries = [
                    ("", lang, template) for lang, template in cfg["templates"]
                ]
            for variant_key, lang, template in entries:
                for i in range(trials):
                    try:
                        ok, kinds, turn = await one_trial(
                            ctx, card, lang, template, cfg["expected_tools"]
                        )
                    except Exception as e:
                        ok, kinds, turn = False, [f"ERROR: {e}"], None
                    passed += ok
                    failed += not ok
                    tag = f"/{variant_key}" if variant_key else ""
                    print(
                        f"{'PASS' if ok else 'FAIL'} {card}{tag} {lang}#{i + 1}: {kinds}",
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
