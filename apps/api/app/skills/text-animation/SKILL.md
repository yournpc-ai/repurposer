---
name: text-animation
description: First-version direction for a native text-animation video using exact user copy and content-driven native text and shape animation.
license: Proprietary
compatibility: Repurposer create_video native text/title/list scenes and static or entrance title motion; optional video-template.json and arbitrary component demos are not executed.
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - text-animation
    - motion-graphics
    - native-preset
---

## 文字动画的创作方法

将用户提供的确切屏幕文案编排成简短、易读的原生文字场景。建立清晰的视觉层级，每场围绕一个意思安排节奏，用时序独立的原生文字块和几何图形支撑内容。通过 text_beats 在同一场景内切换重点、形成空间对比、安排先后阅读的节拍；避免让整段文字只播放同一种动画。按本作品需要选择切镜位置、字体、配色、对齐、入场及阅读停留。无需按段落切场，也无需固定为三幕。不要把示例片的深色背景、强调色、第二场强调、结尾打字效果或音效套用到每部作品。

除非用户选了 Preset，否则采用导演设计的原生运动。Preset 是可选的可编辑运动效果。每个文字对象内部，按词和按字素定位的方式须兼容。

所有事实性措辞都应有给定文案依据。不要添加用户未提供或要求的产品、受众、平台、结果、引语或行动号召。只有用户明确要求时才启用旁白。

### 输入与边界

- 需要用户原文，或用户明确要求提炼文案的 Brief。无需 video-template.json 或媒体素材。
- 使用原生动态图形设计流程，可展开用户选定的 Preset。没有 StylePack 层、第二套模板语言、组件运行时、隐藏执行工具或特定渲染器专用字段。
- 本 Skill 指导首稿。制作时直接使用已保存的 CompositionVersion。
