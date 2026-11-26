---
name: kinetic-launch
description: Direct beat-led product launches, high-energy UI teasers and kinetic typography films from real product screens and short copy.
license: Proprietary
compatibility: Native motion blocks, pinned screenshots, instrumental music and sound-engine v2.
metadata:
  version: "1.0.0"
  author: repurposer
  tags: [product-launch, kinetic-typography, beat-led]
---

以强鼓点为主时钟。先用 `search_music` 选择节奏清晰的纯器乐 BGM，在重拍、切分和乐句收束处落幕。默认零旁白、零字幕，仅在用户明确要求时编排配音。

- 15–30 秒用 16–30 幕，45–60 秒用 30–48 幕。文字拍 0.4–1.6 秒，UI 闪切 0.35–2.0 秒。关键主张定格一拍，让观众读完。
- 全屏单幕只放 2–5 个词。用 `kinetic_beat` 的 `inline_badge_split` 开场，`impact_cut` 落观点，`typewriter_swap` 退格换词，`slot_flip` 锁定前缀，`marquee_wall` 推进高潮。相邻幕大胆切换 `theme: light` 与 `theme: dark`，高潮可从白场硬切黑场。
- 多张实拍界面用 `ui_montage`（`rapid_cut` 随鼓点快闪、`fan_slide` 横掠功能组、`cascade_3d` 纵深巡航），搭配 `browser_url_load` 地址栏键入加载、`zoom_follows_click` 光标点击推镜、`device_mockup`（`dual` 双端画中画 / `split_focus` 分屏）以及 `product_showcase`（`callout_steps` 聚光遮罩 + `dolly_zoom`）。场景大切换交替配 `whip_pan` / `zoom_through` / `wipe_reveal` / `iris_focus` 遮罩转场，高频快切之间保持利落硬切。产品数字与主张须有来源。
- 高密度声画绑定：优先用 `search_sfx_library` 选实录 Foley（`sfx_slug`），并用 sound-engine v3 的 `deep_hit` 压重拍、`select_tick` 贴光标操作、`sub_drop` 收束、`riser` 峰值对齐揭示；`whip_pan` / `zoom_through` 转场配 `swoosh_cut` 横扫声，结尾配 `brand_stinger`。
- 原生画布承担纯色底，勿为底色调用付费 `generate_image`。多幕成稿后调用 `preview_range` 复查快切、字幅和真实 UI 的可读性。
