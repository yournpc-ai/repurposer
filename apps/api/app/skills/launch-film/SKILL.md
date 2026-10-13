---
name: launch-film
description: Launch-film storyboard craft — scene semantics, pacing rhythm, quoted-copy discipline, camera storytelling over a page screenshot, naming. Woven into the launch_film tool's storyboarder prompt at assembly time; the model never loads it at runtime.
license: Proprietary
compatibility: Repurposer launch_film tool (film_storyboarder agent prompt injection).
allowed-tools:
  - launch_film
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - launch-film
    - storyboard
    - web-page-film
---

## 发布短片 storyboard 工艺约定

短片的本质是**一场有据可查的讲述**：观众 30 秒内要回答「这是什么、为我解决什么、下一步去哪」。你写的每个字都是页面上真实存在的文案——你是剪辑师，不是文案。

### 叙事弧线（场景顺序的默认形状）
1. **钩子开场**（hero 或 words）：页面上最有张力的一句话/一个数字，先声夺人。
2. **展开**（words / divider / ui 交替）：把主张拆成 2-4 个节拍；divider 用来换气分段，ui 场景是「证据」——让页面自己说话。
3. **收束**（reveal → end）：reveal 回扣开场的主张，end 给出名字与去向。
这只是默认形状；页面素材的性格可以改写它（如纯文案页可以没有 ui）。

### 节奏
- 前 3 秒定生死：开场场景给最短时长，字最少。
- ui 场景是全片最慢的镜头（观众在读截图），给足时长；连续两个 ui 之间要插文字场景换气。
- end 卡要留得住：名字 + tagline，别塞第三个信息。

### 相机叙事（ui 场景的 focuses）
- focuses 是**目光的路径**：先全貌（zoom 1），再推进到页面正在说话的区域。
- 每个 focus 对应一个 caption 节拍时效果最好——镜头到哪，话说到哪。
- 别为了动而动：一次有意义的推进胜过三次平移。

### 文字纪律
- words/hero/reveal 的词要**短到能喊出来**；长的放进 sub。
- divider 的 roll 词列表是同一语义层的并列枚举（特性名 / 栏目标题），不是句子。
- 同一句文案在全片只出现一次——除了刻意的前后呼应（开场钩子 → reveal 回扣），呼应要换场景类型，不要原样重放。

### 命名
- `name` 是这部片的展示名：读页面气质起一个短名（≤ 24 字符），起不出就 null——系统会回退到诚实的参数标签，绝不硬编。
