---
name: stills-editing-craft
description: Photo-slideshow editing conventions (产物质量线 craft 语法 v0 图文表) — hook-first image order, dwell sweet zone, motivated Ken Burns motion with alternating directions, cuts on clause boundaries, scarce varied emphasis, structural breathing every 12–18s. Woven into the stills editor agents' prompts at assembly time; the model never loads it at runtime.
license: Proprietary
compatibility: Repurposer stills tool (stills_editor / stills_editor_outline agent prompt injection).
allowed-tools:
  - select_clips
  - align_stills
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - editing-craft
    - stills
    - beat-plan
---

## 剪辑工艺约定（图文视频——照片 + 文字稿/旁白）

这些是先验惯例（编辑部经验的起点），不是硬门槛——素材贫困时（图少话长）优先保诚实，dwell 超带优于复用同一张图。

### 视觉钩子匹配
首图 ≤0.6s 出现，且其主体对应对白首个强调短语——第一拍决定完播，首图永远是最强的那张。

### 图停甜区
均停 2.4–4.8s；强调词处可短至 1.6–2.4s（短停 = 强调）；任何一拍永不 <1.3s（频闪）/ 不宜 >4s（boredom）。素材不够时坦白拉长，**一图只用一次**。

### 运动带原因
Ken Burns 缩放率 1.05–1.20×/段；相邻运动拍**交替方向**（zoom_in ↔ zoom_out、pan_left ↔ pan_right）；运动随内容起（推近 = 强调，拉远 = 释然/复位），不为动而动。

### 切在意义上
图切换落从句/句边界，永不落词中——锚点吸附已保证词界，你选 marker 时选语义边界的开头。

### 强调隔离
强调是稀缺资源：至多约 1/3 的拍带强调；同一装置不连用——hold（长停）/ punch_in（推近）/ caption_pop（字幕炸出）三种换着来；强调词应对齐旁白的语义/声学峰（提示里给了证据），不是"看起来重要"的词。

### 结构呼吸
每 12–18s 一次复位拍（`reset: true`）：更宽构图、更慢运动或静帧、更长停——观众需要喘口气，无休止感 = 廉价感。

### 收束
payoff 落最后 15–20%；最后一拍宁可多停半秒，不要"就这么没了"。

### 音频闪避（编译侧常量，无需你决定）
BGM 对人声 -18~-22dB；人声 -14 LUFS ±1。
