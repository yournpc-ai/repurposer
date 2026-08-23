---
name: carousel
description: LinkedIn / IG carousel craft conventions — cover-hook-first structure, one-point-per-slide cognitive load, progressive logic flow, explicit CTA close, title scannability, slide-count sweet spot. Woven into the write_carousel tool's writer prompt at assembly time; the model never loads it at runtime.
license: Proprietary
compatibility: Repurposer write_carousel tool (carousel_writer agent prompt injection).
allowed-tools:
  - write_carousel
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - carousel
    - writing-conventions
    - social-content
---

## 轮播图工艺约定

轮播 = **多页叙事**。每张幻灯是认知节点，全套是论证链路。读者滑得快（3-5 秒/张），结构纪律是命。

### 三段式骨架（必守）
1. **封面（slides[0]）** = 钩子——读者停下来点开的那一页
2. **正文（slides[1:-1]）** = 1 张 1 个要点，递进论证
3. **收束（slides[-1]）** = 显式 CTA / 总结问题 / 引导动作

永远不要"开场陈述 → 6 张平行要点 → 没了"——平铺无钩子的轮播 = 完播率天然低。

### 封面纪律
- 标题 ≤ 8 词（中 ≤ 20 字）
- 形态四选一：
  - 反直觉声明（"研究者花 10 年解决的问题，工程师 6 个月就够了"）
  - 数字钩子（"3 个步骤，把你的周会从 90 分钟压到 20 分钟"）
  - 强对比（"我以前 vs 现在"）
  - 直接提问（"你团队里的会议，为什么总是超时？"）
- 禁止把论文摘要 / 第一段作为封面（= 没钩子）

### 正文（一要点一张）
- 每张幻灯 **只承载 1 个独立要点**
- 截图 / 数字 / 类比 任选其一作为视觉锚
- 标题（`title`）= 这张幻灯要解决的那个问题
- 正文（`body`）= 答案 / 数据 / 例证，1-3 行内
- 最多 5 行中文 / 3 行英文（视觉上限，超出 = 缩字，不是换行）
- 不要在一张里塞两个并列点（"X 和 Y 都..."）——拆成两张

### 顺序 = 论证链路
不是 transcript 段落顺序，是**逻辑依赖**：
- 平行结构：先列共性，再展开每个分支
- 因果链：A → B → C，按读者接受的因果序
- 时间链：可按时间，但每张必须自包含一个时刻
- 反转结构：先常规认知 → 反例 → 新解释

**任意相邻两张之间都要能写一句"所以..."**——检验论证是否连贯。

### 收束（CTA）
- 形态四选一：
  1. 评论邀请（"你怎么看？说说你的版本"）
  2. 转发邀请（"如果你认识会需要这个的人"）
  3. 收藏邀请（"收藏这篇，下次会议前翻一下"）
  4. 私信邀请（"DM 我，告诉我你的场景"）
- 不要"谢谢观看" / "希望对你有帮助"——空收束 = 浪费最后一张的注意力峰值
- 标题比正文更重要——读者滑到底常常只看最后一帧的标题

### 张数
- 6 张甜区（recipe 默认 = 6）
- 8-10 张可接受，前提是每张都有独立价值
- < 4 张 = 不值得轮播（用单图帖更好）
- > 12 张 = 完播率掉；强约束：除非论点必须多于 12 个独立要点，否则不超 10

### 视觉一致性（图像层自行处理）
所有幻灯标题语气统一（不要第 1 张疑问 + 第 2 张断言）；正文长度对齐（每张 1-3 行，不要有的 1 行有的 5 行）；CTA 视觉明显区别于正文（用户滑到底能立刻认出是收束）。
