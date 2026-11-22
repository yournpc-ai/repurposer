---
name: knowledge-explainer
description: First-version direction for a script-led knowledge explainer using READY narration alignment, word anchors, native Presets, and controlled draw-2d or remotion-project Generators.
license: Proprietary
compatibility: Repurposer create_video fixed sources, native text and READY aligned narration; controlled Generator resources require an external Skill and enabled component bake.
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - knowledge-explainer
    - narration-alignment
    - draw-2d
    - remotion-project
---

## 知识讲解视频的创作方法

从用户的文稿中讲清知识，也可使用已明确标明为演示而模拟的知识文稿。从核心概念出发，按能支撑它的要点安排连贯的画面。用受控 Generator 解释概念，避免无关装饰。重要的独立标签、字幕、旁白和声音保留为可编辑的原生对象。模拟文稿仅供创作演示，不能当作访谈、研究引文或事实来源。

若已有最终录音及其确切原稿，使用状态为 READY 的 NarrationAlignment。从中选择真实的句子 ID 和 emphasis_word_ids，由系统解析不可变的音频范围和词锚点。原生 caption-phrases 及 text-impact 效果可直接使用这些事实。不得估算词级时间、编造词 ID，也不要把 PENDING、PROCESSING 或 review_required 当作 READY。当原生对象不足以说明概念时，可选择一个受控 Generator。服务端确定输出时间窗并保存源码供审阅，执行须等待制作授权。

四种基础图元能清楚表达的关系用 draw-2d。有可用且已隔离的组件运行环境时，可用 remotion-project 实现精确布局、多阶段变换或需要受控 TSX 的复杂运动。图形关系本身必需的标签可画入画面，此时不能作为独立的原生文字编辑。

没有适当的 READY 对齐结果，但需要简单的动态示意图时，用 draw-2d 的已声明指令，在限定的输出范围内设计。有隔离运行环境时，多场讲解或较长的连续变换可用组件模式组织普通 Composition 场景。在设计契约允许的范围内，让重要的解释文字保留为原生对象。

### 输入与边界

- 知识内容本身可以是唯一输入，无需真实图片、视频、网页、访谈或其他证据素材。要按源音频对齐设计，则必须有固定音频、逐字定稿及 READY 对齐结果。
- remotion-project 需要 API 显式启用，且渲染运行环境报告隔离已生效。缺少任一条件就不能声称可用 TSX 创作。若 draw-2d 足以表达所需画面则用它，否则说明具体能力缺口。
- 不得编造界面、数据集、引语、用户素材、旁白时间或媒体。图解关系须解释提供的知识。本 Skill 不授予工具、网络、文件、制作或计费权限。后续修订以当前作品和本轮显式选择为准。
