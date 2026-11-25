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
- 全屏单幕只放 2–5 个词。用 `kinetic_beat` 的 `inline_badge_split` 开场，`impact_cut` 落观点，`typewriter_swap` 退格换词，`slot_flip` 锁定前缀，`marquee_wall` 推进高潮。相邻幕切换 `theme: light` 与 `theme: dark`，高潮可从白场硬切黑场。
- 多张实拍界面用 `ui_montage`，`rapid_cut` 随鼓点快闪，`fan_slide` 横掠功能组，`cascade_3d` 沿界面纵深巡航。单张关键操作接 `product_showcase` 聚焦。产品数字与主张须有来源。
- 用 sound-engine v2 的 `deep_hit` 压重拍，`select_tick` 贴操作，`sub_drop` 收束，`riser` 的峰值对齐揭示；`whip_pan` 转场配 `swoosh_cut` 横扫声。
- 原生画布承担纯色底，勿为底色调用付费 `generate_image`。多幕成稿后调用 `preview_range` 复查快切、字幅和真实 UI 的可读性。
