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

短片的本质是**一场有据可查的讲述**：观众在一分半内要回答「这是什么、为我解决什么、下一步去哪」。你写的每个字都是页面上真实存在的文案——你是剪辑师，不是文案。

### 叙事弧线（场景顺序的默认形状）
全片目标 75–95 秒、10–16 幕，形状是**支柱迭代**：
1. **冷开场**（1–2 个 words）：页面上最有张力的一句话，逐词砸出来，字最少。
2. **hero**：产品名 + tagline，一句话立住。
3. **第一支 ui**：首页折顶的证据镜头。
4. **逐个支柱展开**（页面主张拆成 2–4 个支柱，每个支柱一组）：divider 报幕（编号换气）→ ui 举证（该支柱的 section 镜头）→ 若页面有数字/规格，插一幕 plate；没有就跳过。
5. **收束**：reveal 回扣开场主张（可再接一幕 ui 兑现 reveal 的悬念）→ end 给出名字与去向。
这只是默认形状；页面素材的性格可以改写它（如纯文案页可以没有 ui）。

### 节奏
- 全片 75–95 秒：不要短于 75——支柱一个都讲不透的短片不如不做。
- 前 3 秒定生死：冷开场的 words 场景给最短时长，字最少。
- ui 场景是全片最慢的镜头（观众在读截图），给足 6–10 秒；连续两个 ui 之间要插文字场景换气。
- plate 是稀缺的（全片至多 2 幕）：只在页面真的给出数字/规格时用，卡片只摆数字和短标签，不摆句子。
- end 卡要留得住：名字 + tagline，别塞第三个信息。

### 相机叙事（ui 场景的 focuses 与 frame）
- focuses 是**目光的路径**：每幕 1–3 个，先全貌再推进到页面正在说话的区域；两次推进之间留足 2 秒以上的空气。
- frame 的选择是叙事选择：`frame:false` 全出血怼脸推近（沉浸式，页面本身充满画布——证据的高潮时刻用）；`frame:true` 浏览器框（「这是一个真实页面」的可信时刻用）。两种在同一部片里混用。
- 每个 focus 对应一个 caption 节拍时效果最好——镜头到哪，话说到哪。
- 别为了动而动：一次有意义的推进胜过三次平移。

### 文字纪律
- words/hero/reveal 的词要**短到能喊出来**；长的放进 sub。
- divider 的 roll 词列表是同一语义层的并列枚举（特性名 / 栏目标题），不是句子。
- plate 卡片：big 是数字或极短记号（如 "256 B"、"RFC 9180"），label 是一行小字；页面没有数字就不许造 plate。
- 同一句文案在全片只出现一次——除了刻意的前后呼应（开场钩子 → reveal 回扣），呼应要换场景类型，不要原样重放。

### 命名
- `name` 是这部片的展示名：读页面气质起一个短名（≤ 24 字符），起不出就 null——系统会回退到诚实的参数标签，绝不硬编。
