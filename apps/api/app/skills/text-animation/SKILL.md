---
name: text-animation
description: First-version direction for a beat-led kinetic text video driven by musical rhythm, high-impact typography presets, native motion blocks, and v2 sound effects.
license: Proprietary
compatibility: Repurposer create_video native motion blocks, 11 text style presets, 4 CompositionStyle presets, and 22 v2 sound recipes; no narration, website capture, or footage required.
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - text-animation
    - kinetic-typography
    - beat-led
---

## 动态文字视频的创作方法

以**节拍与音乐网格作为主时钟（Beat-Led Master Clock）**设计首版动态文字短片。不强加旁白：先确立配乐氛围、BPM 节拍密度与情绪曲线，再将切镜点、标题冲击、转场与长短音效严格踩拍落位，用字重反差、节奏留白和视觉律动支撑观点的说服力。

### 风格包、文字预设与动效幕组合

1. **先定全片视觉风格（`CompositionStyle`）**：在四套正交风格包中选择与文案气质最契合的一套，统一整片的画布底色、对比度、字重层级与默认转场：
   - `kinetic_anime`：深色斜线海报美学、900 Black 冲击字、强对比偏移阴影与 `whip_pan` 甩镜，适合宣发预告、金句冲击与高能观点。
   - `vox_editorial`：暖纸面杂志质感、左向右高亮扫条、硬边报刊框线与 `wipe_reveal` 擦除，适合深度观点、媒体评论与节奏拆解。
   - `swiss_paper`：瑞士网格白底、极细 1.5px 标尺线、零多余阴影与 `wipe_reveal`，适合理性宣言、设计发布与极简数据陈述。
   - `institutional_dark`：深墨色柔光玻璃卡片、青蓝强调色与 `crossfade` 叠化，适合克制权威的行业主张与品牌定调。
2. **组合 13 个原生动效幕（`MotionBlockObject`）**：优先选用文字、对比、数据与引证核心幕（`statement_hook`、`kinetic_title`、`metric_grid`、`quote_proof`、`split_compare`、`closing_cta`），在需要展开论据或流程时衔接 `bento_features`、`flow_diagram`、`step_timeline`、`data_chart`、`chat_demo`、`product_showcase`、`device_mockup`；搭配五种无缝转场（`crossfade`、`whip_pan`、`wipe_reveal`、`zoom_through`、`iris_focus`）推进幕间张力。
3. **运用 11 套原生文字样式预设（`insert_text` / `edit_text`）**：按语义角色挑选行业预设——主标题/强钩子用 `kinetic_impact`、`vox_highlighter` 或 `creator_pop`，逐词踩拍强调与节奏卡点用 `karaoke_focus`，双语字幕用 `bilingual_cinema`，轻量标注/角标用 `vox_label`、`editorial_callout`、`lower_third_tag`，常规清晰阅读用 `clean_broadcast`、`cinema_glass`、`minimal_light`。
4. **用 22 配方 v2 音效（`generate_sfx`）堆叠起势与重击**：在关键切镜与核心金句落点前叠加起势（`riser`、`sub_swell`、`shimmer_lift`），在字块定帧瞬间落重击或清脆提示（`impact`、`deep_hit`、`kinetic_thud`、`sub_drop`、`stinger`、`title_bloom`、`metric_chime`、`callout_ping`），在转场中点贴合扫风（`whoosh`、`swoosh_cut`、`velvet_pass`、`page_turn`），用短促交互音（`click`、`soft_pop`、`toggle_on`、`select_tick`、`confirm_chime`）与空间铺底（`studio_air`、`pulse_bed`）拉开呼吸层次。

### 输入与边界

- 纯观点、金句、宣发文案、活动预告或品牌口号即可独立成片；无需实拍录像、网站采集、外部图片或旁白录音。
- 若用户要求保留原文措辞，必须逐字忠实保留用户文案，仅通过断句、字号层级、节拍停顿与动效强化表达。
- 严禁编造不存在的引语出处、人物背书、统计数字或对比结论；无真实数据来源时不得凭空捏造指标。
- 严禁仅为纯色底、渐变或抽象几何背景调用付费 `generate_image`；画布纹理与层次由 `CompositionStyle` 及原生动效幕确定性渲染完成。
- 所有独立标题、标注、文字和音轨均保持为可继续编辑的原生对象。本 Skill 不授予额外工具、网络、文件、制作或计费权限。
