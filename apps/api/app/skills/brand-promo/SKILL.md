---
name: brand-promo
description: Narrated commercial product promo and brand launch films using real website captures, human-cadence voiceover with pauses and emotion, word-anchored motion blocks, and curated BGM/SFX.
license: Proprietary
compatibility: Native motion blocks, pinned website screenshots, MiniMax speech-2.6-hd voiceover, curated music and sound-engine v3.
metadata:
  version: "1.0.0"
  author: repurposer
  tags: [brand-promo, product-promo, voiceover, storytelling, word-sync]
---

以「真实人声节奏 + 画面词级卡点」为主时钟制作商业宣传片。先读官网真实卖点与视觉气质，再按四段叙事弧推进：**反差钩子 → 真实产品实演 → 机制与量化证据 → 品牌收束**。

## 1. 真人感口播与韵律控制

- **短句断气与字数预算，拒绝说明书腔**：按总时长提前控制口播字数（30 秒约 55–70 英文词 / 100–130 中文字；45 秒约 85–105 英文词 / 155–190 中文字；60 秒约 115–145 英文词 / 210–260 中文字），每幕控制在 1–2 句短句（英文 8–16 词、中文 14–28 字），用主动动词和具体数字替代抽象形容词；屏上文字提炼为 2–5 词视觉锚点，与口播形成互补双声部，绝不全文复读。首稿落位在目标时长 ±25% 内即视为自然成立，不要为了硬凑整秒拆删画面或破坏口播呼吸，交付时如实说明实际时长即可。
- **句内停顿与呼吸感**：在核心反差、关键词揭晓或数字抛出前插入 `<#0.3#>` 或 `<#0.4#>` 停顿标签（系统会在派生字幕中自动剥离标签，只保留真实呼吸停顿）；每幕口播结束后留自然气口用于转场切镜，禁止词句贴边硬切。
- **按情绪弧线微调语速与语气**：
  - 开场钩子与痛点转折：`voice_speed: 1.03–1.08`，节奏利落有张力；
  - 真实界面演示与数据证据：`voice_speed: 0.96–1.02`、`voice_emotion: "calm"`（沉稳可信，不念经）；
  - 核心突破或高潮揭示：`voice_emotion: "fluent"` 或 `"happy"`（克制提亮，不夸张）；
  - 结尾品牌定版：`voice_speed: 0.94–0.98`、`voice_emotion: "calm"`，给画面留出 1 秒余韵。
- **视觉冲击拍穿插**：在开场、中段转折与高潮前主动插入 2–4 幕 **0.7–1.5 秒无旁白视觉拍**（`narration` 留空，用 `kinetic_beat` / `ui_montage` 配重拍音效制造呼吸反差），避免从头念到尾的匀速感。

## 2. 词级与停顿卡点（画面跟说话走）

- 给 `product_showcase.callout_steps[]`、`product_showcase.cursor`、`metric_grid.items[]`、`flow_diagram.nodes[]`、`step_timeline.steps[]`、`bento_features.cards[]`、`split_compare` 条目、`data_chart.points[]` 或 `statement_hook` 声明 **`cue_phrase`**（填写该幕 `narration` 中对应的关键词或数字短语，如 `"£18.7m"`、`"four steps"`、`"audit"`），服务端会在合成旁白后按真实语音时间戳自动解算精确出现秒数，让高亮框、光标点击和卡片逐一踩在念到该词的瞬间。
- 幕间转场（`whip_pan` / `zoom_through` / `wipe_reveal` / `iris_focus`）自然落在口播收尾后的停顿气口；0.7–1.5 秒无旁白快切间用干脆硬切。
- `create_video` 返回每幕实测切点与 `narration_clips` 区间后，批量调用 `generate_sfx(align_peak_at_seconds=...)` 将转场扫音、重拍与微点击严丝合缝对齐真实切点与关键词落点。

## 3. 多样化选曲与视觉混搭

- 调用 `search_music({})` 查看全库曲目的 BPM、曲风与情绪，**根据本片叙事方向与品牌气质挑选最匹配的曲目**（如机构/理性叙事选沉稳极简鼓组或电子脉冲，动感产品演示选 Funk / Electro / Tech House，轻快创意品牌选 Upbeat Indie），切勿机械默认只选第一首。
- 混搭真实界面幕（`browser_url_load`、`product_showcase`、`zoom_follows_click`、`device_mockup`、`ui_montage`）与排版/数据幕（`kinetic_beat`、`statement_hook`、`metric_grid`、`flow_diagram`、`data_chart`、`closing_cta`），并在高潮处用 1–2 幕明暗 `theme` 反转制造记忆点。
