---
name: quote-cards
description: Quote-card craft conventions — self-contained one-liners, attribution discipline, hook-first ordering, rhetorical-mode variety, persona voice fidelity. Woven into the write_quotes tool's writer prompt at assembly time; the model never loads it at runtime.
license: Proprietary
compatibility: Repurposer write_quotes tool (quotes_writer agent prompt injection).
allowed-tools:
  - write_quotes
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - quote-cards
    - writing-conventions
    - social-content
---

## Quote 卡片工艺约定

引用卡的核心 = **脱离上下文也成立**。每条 quote 都要能独立成图、独立传播、独立说服——读者没看过原稿也应该被击中。

### 自包含性（最高优先级）
每条 quote 单看即懂：禁用"这一点"、"上述"、"接下来"等需要上下文的指代；首次出现的概念必须自释（"我们 2024 年那次实验" 而不是 "那次实验"）；如果原话需要背景，把它融进 quote 里（"在我带队做那场 6 个月实验时，我学到..."），不要做外部引用。

### 单条长度
- 英文 ≤ 200 字符（约 30-40 词）
- 中文 ≤ 80 字
- 一口气念完的长度——读者默读一遍就是它朗读时的字数
- 超过长度 = 拆成两条 / 砍掉修饰 / 换更短的同义说法

### attribution（出处）纪律
- 必填（schema 强约束）
- 形式：speaker name + 上下文锚（演讲标题 / 文章 / 场合）
- 例子：`"Sarah Chen · WFT 2024 keynote"` / `"陈思远 · 复杂系统公开课"`
- 不要堆头衔（CEO / 教授 / 创始人）除非这个身份本身是 quote 的力量点
- 不要空着或写"讲者" / "本文" 等占位词

### 排序 = 钩子优先
返回的 quotes 列表第 0 条 = **视觉冲击最强的那条**——读者第 1 秒看到的那张图；不按原 transcript 顺序，不按"重要性均匀分布"，按"独立能炸的程度"排；中间几条 = 论据 / 反差 / 类比；最后一条 ≠ 收束，而是另一个能独立站的强 quote（不是空泛的总结）。

### 修辞多样性
4 张卡片默认要至少覆盖 3 种修辞模式：
- 断言（"X 就是 Y"）
- 反差（"我们以为 X，其实是 Y"）
- 反问（"为什么 X？"）
- 类比（"X 像 Y 一样..."）
- 数据 / 类目（"6 个月 / 4 个版本 / 30% 提升"）

禁止 4 张全是断言——视觉单调，引用卡墙失去节奏。

### 人设风格保真
quote 必须读起来像这个人会说的话——不是"AI 改写过的更顺"；保留原话的口语节奏、不完美的句法、个人化的措辞（"我们" vs "研究者" vs "用户"）；人设 `voice.tone` 决定正式程度（学术腔 vs 朋友腔），但**不**意味着改写事实。

### 配图责任（图像层自行决定）
`_save_quote_card_image` 单独渲染首张 PNG：黑底白字 / 引号装饰 / attribution 角标；卡片内容与你无关，工艺层按字数自动调字号 / 折行；quote 文本本身别带 Markdown 强调符号（** / `）——会原样进图。
