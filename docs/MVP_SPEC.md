# Repurposer MVP 产品规格文档

> 版本：2026-07-04  
> 状态：已实现基准规格（随代码迭代持续更新）  
> 背景：基于 OpusClip / Seedance 调研以及当前 Repurposer 已有代码，收敛出投资人 demo 阶段的最小闭环。

---

## 1. 核心产品决策

### 1.1 定位不变

- **目标用户**：欧洲学术/企业演讲者、研究机构
- **核心输入**：演讲/访谈/会议视频、音频、文字稿
- **核心输出**：vertical clips、LinkedIn 长文、quote cards、多语言 summary
- **差异化**：多语言、以知识资产而非病毒内容为导向

### 1.2 关键设计决策

| 决策 | 内容 | 原因 |
|------|------|------|
| 不用 `/workflow` 独立路由 | workflow 能力内嵌在 Home 的 composer 里 | 减少跳转，用户上传/粘贴即可开始 |
| 保留 `project = 一次创作会话` | `/projects/$id` 作为该会话的结果页路由 | 数据模型不变，只是不在 sidebar 暴露 |
| Sidebar 移除 Projects | sidebar 只保留 Home / Brand template / Library / Speakers | project 不是一级导航，Home 和 Library 已经能覆盖 |
| 结果用 Tab 展示 | 一次生成的多种产物在结果页按类型 Tab 展示 | Opus 结果页只有 clips，我们有 heterogeneous outputs，Tab 最清晰 |
| **Clip editor 已作为 MVP 入口保留** | 结果页 Clip 卡片提供 **Edit** 按钮，进入 `/projects/$id/clips/$clipId` 做 transcript/trim/caption 精修 | 代码已实现，editor 和 AI chat 互为补充；复杂多轨剪辑仍交给 CapCut/Premiere |
| Chat 是 asset-scoped 快捷服务 | chat 从具体产物卡片进入，用于模糊/快捷修改指令；以 **Modal** 形式承载 | 主流程不依赖 chat；chat 不是全局 thread |

---

## 2. 用户主流程

```
┌─────────────────────────────────────────────────────────────┐
│ Home `/`                                                    │
│  • Hero + composer（内嵌 workflow 参数）                     │
│  • Recent projects（含内置 demo project）                    │
└───────────────────────┬─────────────────────────────────────┘
                        │ 用户上传/粘贴 + 选参数 → 提交
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ Project results page `/projects/$id`                        │
│  • 顶部显示原始 prompt                                       │
│  • Tabs: [Clips] [LinkedIn] [Quotes] [Summary]              │
│  • 每个产物卡片可 Download / Regenerate / AI chat            │
│  • Clip 卡片额外提供 Edit 按钮进入 clip editor               │
└───────────────────────┬─────────────────────────────────────┘
                        │ 下载 / Edit 精修 / AI chat 快捷修改
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ Library `/library`                                          │
│  • 按日期分组展示所有产物                                    │
│  • 可下载/删除                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 路由与导航

### 3.1 Sidebar（全局导航）

移除 **Projects**。保留：

| 项 | 路由 | 说明 |
|---|---|---|
| Home | `/` | 首页，创建入口，recent projects |
| Brand template | `/brand-template` | 品牌模板设置，保持现有实现 |
| Library | `/library` | 资产库，新增/完善 |
| Speakers | `/speakers` | speaker 管理，保持现有实现 |

Account dropdown 保留：Profile / Settings / Logout（当前已有）。

### 3.2 存在的路由

```
/                         → Home
/brand-template          → Brand template（不变）
/library                 → Library（已实现）
/speakers                → Speakers（不变）
/projects/$id            → Project results page（产物结果页）
/projects/$id/clips/$clipId → Clip editor（transcript/trim/caption 精修）
```

`/projects`（不带参数的列表页）**不在 MVP 路由内**；项目入口通过 Home 的 Recent projects 和 Library 覆盖。
`/c/$projectId` 之前已删除，确认不存在。

---

## 4. Home 页面规格

### 4.1 总体原则

- **除了 composer 之外，其他布局不变**
- Recent projects 区域保留在页面最下方
- Demo project 就是 Recent projects 区域中的一个真实 project item，**不单独做一个 “Demo showcase” 模块**

### 4.2 页面状态

#### 状态 A：用户无 project（首次访问）

```
┌────────────────────────────────────────────────────────────┐
│  Hero: "Turn your talks into reusable knowledge assets"     │
│  Subtitle + composer                                       │
├────────────────────────────────────────────────────────────┤
│  Recent projects                                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  [Demo Project Card]                                  │  │
│  │  标题：Example: AI Ethics Keynote                     │  │
│  │  标签：Demo                                           │  │
│  │  预览：clips / LinkedIn / quotes / summary            │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

- Demo project card 与真实 project card 样式一致，左上角有一个 `Demo` badge
- 行为和真实 project 完全相同，只有内容不同
- 点击 demo card → 进入 `/projects/{demo_project_uuid}`

#### 状态 B：用户已有 project

```
┌────────────────────────────────────────────────────────────┐
│  Hero + composer                                           │
├────────────────────────────────────────────────────────────┤
│  Recent projects                                           │
│  [Project 1] [Project 2] [Demo Project] ...                │
└────────────────────────────────────────────────────────────┘
```

- Demo project 固定在 Recent projects 的**最后**
- 真实 project 按更新时间倒序排列在前面
- 如果用户没有任何真实 project，demo 自然显示在最前面
- 每个 project card 展示：标题、最后更新时间、产物类型标签、缩略图/图标

### 4.3 Composer / 内嵌 Workflow

位置：Hero 下方，替代当前 Home 的 prompt input。

设计参考 Opus Pro：**先输入，再确认 AI 识别的意图，最后生成**。

结构：

```
┌────────────────────────────────────────────────────────────┐
│  ┌─────┐                                                   │
│  │ +   │  Paste transcript or upload a video/audio/file... │
│  └─────┘                                                   │
│                                                            │
│                   [ Generate knowledge assets → ]          │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ AI detected your intent — edit below before generating │  │
│  │                                                       │  │
│  │  Speaker ▾  Brand ▾  Tone ▾  Language ▾  Outputs ▾   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

#### 意图识别层

- 用户在 textarea 输入 prompt 后，前端 **debounce 600ms** 调用 `POST /api/v1/infer-intent`
- 后端使用 **MiniMax M3** 识别：
  - `language`：提示词语言或显式语言请求（如 "in German"）
  - `outputs`：请求的产物类型（clips / linkedin / quote_cards / summary）
  - `tone`：professional / thoughtLeadership / conversational / academic
  - `specific_instruction`： distilled 后的具体指令
- 识别结果展示在输入区下方的确认面板中
- 用户可以手动修改任何参数；被修改的参数会被 **锁定**，后续 prompt 变化不再覆盖
- 如果识别失败或服务不可用，fallback 到高置信度默认值

#### 参数说明

| 参数 | 默认值 | 选项 | 来源 |
|---|---|---|---|
| Speaker | 当前用户的第一个 speaker | 下拉选择所有 speakers | 用户选择 |
| Brand template | 默认 brand template | 下拉选择所有 brand templates | 用户选择 |
| Tone | `professional` | 现有 TONES 枚举 | AI 推断 + 可改 |
| Language | `en` | en / fr / de / es / it / zh | AI 推断 + 可改 |
| Outputs | clips + linkedin + quote_cards + summary | 可多选；clips 始终生成 | AI 推断 + 可改 |

#### 行为

1. 用户上传/粘贴后，file/prompt 变为有效状态
2. 用户输入 prompt 时，AI 实时推断意图并在下方展示可编辑的确认面板
3. 点击 Generate → 调用 `POST /api/v1/projects` 创建 project → 上传 asset → 创建 user message → 触发 generation
4. **页面跳转到 `/projects/$id`**（Home 保持原样，不原地变形）
5. 前端通过轮询 `GET /api/v1/projects/{id}/results` 等待生成完成并展示结果卡片

### 4.4 Show Grid（能力展示，非操作入口）

Hero 与 composer 下方有一排 icon grid。它不是 tool grid，而是 **show grid** —— 用来快速告诉用户 Repurposer 能把演讲内容变成哪些知识资产。

- **不可用于切换 outputs**：点击任何 icon 只提示 “coming soon” 或什么都不做
- **不联动 composer 中的任何参数**
- **视觉作用大于交互作用**：让首次访问者一眼理解产品能力边界

当前展示的 9 个能力中，MVP 实际生成的是：Clips、LinkedIn、Quote cards、Summary。其余（newsletter、key insights、one-pager、slides、blog post、social carousel）是 Phase 2/3 能力，提前展示以建立产品想象。

### 4.5 Prompt → Results 的完整链路

用户点击 Generate 后，系统按以下链路执行：

```
Home composer
    │
    ├─ 意图识别 ───── POST /api/v1/infer-intent（LLM 推断 language/outputs/tone）
    │
    ├─ 创建 Project ── POST /api/v1/projects
    ├─ 上传 Asset ───── POST /api/v1/projects/{id}/assets
    │      └─ Worker: ASR / 文本提取 / PDF 转图片
    └─ 触发 Generation ─ POST /api/v1/projects/{id}/generate
              │              └─ 同时创建 project-scoped ChatSession，prompt 存为第一条 user message
              ▼
        WorkflowRun (PENDING)
              │
              ▼
        Worker 认领并执行
              │
              ├─ 1. Content Director：基于材料、GenerationContext 产出统一 ContentPlan
              │     （core thesis / themes / target audience / 每个 output 的 DerivativePlan）
              ├─ 2. Clip Agent：基于 ContentPlan 规划 clips（选段 + script）
              ├─ 3. 对每个非 clip output 调用对应 agent
              │      ├─ clips → build_clip_spec + render_spec
              │      ├─ linkedin → LinkedIn agent
              │      ├─ quote_cards → Quote agent + MiniMax image-01
              │      ├─ carousel → Carousel agent
              │      ├─ summary → Summary agent
              │      └─ blog → Blog agent
              ├─ 4. 保存 Clip / Derivative 到数据库 + assets/
              └─ 5. WorkflowRun completed
              │
              ▼
    Results Page 轮询 /api/v1/projects/{id}/results
        展示 Clips / LinkedIn / Quotes / Summary Tabs（Carousel / Blog 后端已生成，前端待补充）
```

#### 参数在链路中的作用

| 参数 | 进入哪一步 | 影响什么 | 由谁决定 |
|---|---|---|---|
| **Prompt** | Message.content / instruction | 贯穿所有 agent：决定内容主题、hook 角度、文案风格 | 用户 |
| **Speaker** | Project.speaker_id | 选择/创建 Speaker，提取 persona，影响文案语气和 clip 选题 | 用户 |
| **Brand template** | generate request.brand_template_id | 被 bake 进每个 clip 的 `render_spec`，控制字体、颜色、logo、CTA | 用户 |
| **Tone** | generate request.tone_settings | 影响所有文案 agent 的风格 | AI 推断 + 用户确认 |
| **Language** | generate request.target_language | 影响文案语言、clip 字幕语言 | AI 推断 + 用户确认 |
| **Outputs** | generate request.outputs | 决定 worker 执行哪些 agent | AI 推断 + 用户确认 |

#### 关于 LLM Intent 识别

`/api/v1/infer-intent` 是一个轻量级的 LLM 调用，职责是把自然语言 prompt 转成结构化的生成参数：

- **比 keyword 匹配更鲁棒**：能理解 "give me German social posts" → language=de, outputs=[linkedin]
- **有 fallback**：识别失败时返回默认值，不阻断用户
- **可覆盖**：用户手动修改的参数会被锁定，后续 prompt 变化不会覆盖
- **MVP 范围**：识别 language / outputs / tone / specific_instruction；不识别 speaker、brand、clip count

这样 Prompt 和 Outputs/Language 不再是两个并行的输入源，而是 **Prompt 是意图源头，Outputs/Language 是 AI 对意图的结构化呈现**。

---

## 4.6 Brand Template 内容策略

Brand template 不只是视觉皮肤，还承担**内容策略**角色。

### 当前字段

| 字段 | 用途 | 影响阶段 |
|---|---|---|
| 视觉（font / color / logo / position） | 渲染样式 | `render_spec` → Remotion |
| CTA | 视频底部行动号召文案 | `render_spec` + Content Director / Clip Agent（作为转化目标） |
| voice | 品牌语气 | Content Director 定调 + Clip Agent 选片段/写 hook |
| audience | 目标受众 | Content Director 定调 + Clip Agent 选角度 |
| contentGuidelines | 内容 guideline / 禁忌 | Content Director + Clip Agent 过滤片段 |

### 为什么内容策略要放进 Brand template

同一个 Speaker 可以服务多个 Brand。例如：

- Speaker：某 AI 伦理学者
- Brand A（大学官方）：voice = academic, audience = researchers
- Brand B（个人 IP）：voice = provocative, audience = tech Twitter

如果没有 Brand 内容策略，Content Director 和 Clip Agent 只能按 speaker persona 定调，无法体现“这是官方账号还是个人账号”的差异。

### 实现

- `/brand-template` 页面新增 **Content strategy** Tab
- 用户填写 voice / audience / contentGuidelines / CTA
- 生成时后端调用 `content_strategy_from_template()` 提取内容策略
- Content Director 和 Clip Agent prompt 增加 `## Brand Content Strategy` 段落，并明确告知：
  - “你正在为这个 speaker 的受众定调和选 clip”
  - “hook 要符合 brand voice”
  - “CTA 是 {{ cta }}，尽量选能自然过渡到这个行动的片段”

---

## 5. Project Results Page 规格

### 5.1 定位

`/projects/$id` 不再是 chat thread，而是 **Results page**。它用于展示一次生成的所有产物，并作为进入 editor / asset-scoped chat 的入口。

### 5.2 页面结构

```
┌────────────────────────────────────────────────────────────┐
│  Header: Project title                        [Share?]    │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Prompt: "Turn this keynote into LinkedIn posts..."        │
│                                                            │
│  [All] [Clips] [LinkedIn] [Quotes] [Summary]    [Filter]   │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Tab: Clips                                          │   │
│  │                                                     │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐             │   │
│  │  │ ▶️      │  │ ▶️      │  │ ▶️      │             │   │
│  │  │ 00:37   │  │ 00:52   │  │ 01:08   │             │   │
│  │  ├─────────┤  ├─────────┤  ├─────────┤             │   │
│  │  │ Hook 1  │  │ Hook 2  │  │ Hook 3  │             │   │
│  │  │ ✏️ 💬 ⬇️ 🔄│  │ ✏️ 💬 ⬇️ 🔄│  │ ✏️ 💬 ⬇️ 🔄│             │   │
│  │  └─────────┘  └─────────┘  └─────────┘             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ LinkedIn post                                        │   │
│  │ ────────────────────────────────                    │   │
│  │ AI ethics is not just about regulation...           │   │
│  │ [💬 Chat] [⬇ Download] [🔄 Regenerate]              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 5.3 Tabs

- Tabs 放在页面**顶部**
- Tabs **隔离**不同产物类型
- 顺序：`Clips` → `LinkedIn` → `Quotes` → `Summary`
- 默认激活：`Clips`
- `All` tab 可选：混排所有产物，MVP 阶段可不实现

### 5.4 产物卡片与操作

每个产物卡片 hover 或常驻显示操作栏：

| 产物 | 操作 | 说明 |
|---|---|---|
| Clip | **Edit** / **AI chat** / Download / Regenerate | Edit 进入 `/projects/$id/clips/$clipId` 做 transcript/trim/caption 精修；未渲染时 Download 禁用 |
| LinkedIn | **AI chat** / Download / Regenerate | Markdown/Text |
| Quote | **AI chat** / Download / Regenerate | MiniMax image-01 生成的 PNG 金句卡片；未生成图片时 Download 禁用 |
| Summary | **AI chat** / Download / Regenerate | Markdown/Text |

设计原则：
- **AI chat**：模糊/快捷修改（“再短一点”、“翻译成德语”），以 Modal 弹窗承载。
- **Edit（仅 Clip）**：精确控制（剪到具体时间点、调整字幕），进入独立 editor 页面。
- **Regenerate**：基于相同参数重新生成一版新变体。
- **Download**：导出当前产物。
- **不做 Copy**：文本产物通过 Download 获取，避免 clipboard 兼容性和“复制了什么”的歧义。

### 5.5 Asset-Scoped Chat：chat 的正确位置

**核心认知：chat 不是主导航，而是“快捷精修服务”。**

Chat 不应该以全局 thread 形式存在，而应该从 **某个具体产物卡片** 进入，用于对该产物下达模糊/笼统的修改指令。

例如：
- 对 clip 说：“再短一点”、“换个更正式的开头”、“翻译成德语”
- 对 LinkedIn post 说：“更口语化”、“加一个 CTA”
- 对 quote card 说：“换一张更正式的配图风格”

触发方式：
- 产物卡片操作栏中有一个 **Chat** 按钮
- 点击后打开一个 **Modal 弹窗**，上下文是该产物
- Modal 内支持多轮对话，用户输入模糊指令，AI 生成新的产物变体
- 如果指令需要精确控制（如剪到具体时间点），提示用户“请使用 Editor”

数据模型：
- `Message` 可以关联到 `asset_id`（clip_id 或 derivative_id）
- Chat session 是针对单个产物的，不是整个 project
- 生成的新变体会出现在原产物附近或作为新卡片插入

MVP 阶段：
- **已实现 Asset-Scoped Chat Modal**
- 每个产物卡片常驻显示 Chat 按钮，点击弹出 modal
- 与 Edit/Regenerate 并存，构成精修三角

### 5.6 从 Results Page 进入 Editor

Clip 卡片操作栏 → **Edit** → `/projects/$id/clips/$clipId`

Editor 当前能力：
- 左侧/上方：Remotion Player 实时预览
- 右侧/下方：transcript 文字稿编辑（点击单词 seek、删除句子标记为 hidden）
- 单轨 trim：通过滑块调整片段起止
- Caption 目标语言切换（en / fr / de / es / it / zh）
- Voice dubbing（基于 Speaker voiceprint 的 MiniMax T2A）
- 保存后返回 results page

明确不做（交给 CapCut/Premiere）：多轨 timeline、B-Roll、转场、自动人脸追踪、复杂字幕样式自由布局。

### 5.7 为什么这是正确的 chat 应用

| 场景 | 用 Editor | 用 Asset-Scoped Chat |
|---|---|---|
| 精确剪到第 5 秒 | ✅ | ❌ |
| 调整字幕字体/颜色 | ✅ | ❌ |
| “再短一点” | 有点重 | ✅ |
| “换成德语” | 不适合 | ✅ |
| “更正式一点” | 不适合 | ✅ |
| “给我 3 个不同 hook 的版本” | 不适合 | ✅ |

Chat 是“用语言快速告诉 AI 要什么样”，Editor 是“用手动控制精确调整”。两者互补，但都不应该是主流程入口。

---

## 6. Library 页面规格

### 6.1 目的

**Asset Library**：用户的资产库，包含所有生成的产物和原始上传素材，方便用户回头查找、下载、复用。

Library **不按 project 分组**，它是一个扁平的资产时间线。

### 6.2 布局

```
┌────────────────────────────────────────────────────────────┐
│  Asset Library                        [Filter ▾] [Search]  │
├────────────────────────────────────────────────────────────┤
│  Filter tabs: [All] [Uploads] [Clips] [LinkedIn] [Quotes] [Summary] │
├────────────────────────────────────────────────────────────┤
│  July 3, 2026                                              │
│  [upload] [clip] [quote] [linkedin] [summary]              │
│                                                            │
│  June 28, 2026                                             │
│  [upload] [clip] [clip] [quote]                            │
└────────────────────────────────────────────────────────────┘
```

### 6.3 数据聚合

- Library 从 `assets` 表拉取（包括原始上传 + 生成的 clips/derivatives）
- 按 `created_at` 倒序分组（“今天 / 昨天 / 更早”）
- 每个 asset card 显示：
  - 类型图标（upload / clip / linkedin / quote / summary）
  - 文件名/标题/摘要
  - 创建时间
  - 下载入口
- 点击 asset card 可跳转回对应 `/projects/$id`（可选，MVP 阶段下载优先）

### 6.4 资产类型

| 类型 | 来源 | 展示方式 |
|---|---|---|
| Upload | 用户上传的原始视频/音频/文稿 | 文件名 + 上传时间 + 下载 |
| Clip | 生成的 vertical short | 缩略图 + 时长 + 下载 |
| LinkedIn | 生成的 LinkedIn post | 文本摘要 + 下载 |
| Quote | 生成的 quote card | 缩略图 + 下载 |
| Summary | 生成的 summary | 文本摘要 + 下载 |

---

## 7. Asset 本地存储规格

### 7.1 当前问题

当前实现：

```
data/uploads/projects/{project_id}/{filename}
data/uploads/speakers/{speaker_id}/{filename}
data/outputs/{project_id}/{filename}
```

问题：

1. 没有 `user_id` 层级，无法做用户隔离
2. `Asset` 表没有 `user_id` 字段
3. `/api/v1/files/{path}` 没有校验所有权
4. Demo 资产没有固定位置

### 7.2 MVP 目标结构

```
assets/
├── demo/
│   ├── uploads/
│   │   └── projects/{demo_project_id}/demo_video.mp4
│   └── outputs/
│       └── projects/{demo_project_id}/
│           ├── clip_1.mp4
│           ├── linkedin_post.txt
│           ├── quote_card_1.png
│           └── summary.json
└── {user_id}/
    ├── uploads/
    │   └── projects/{project_id}/{filename}
    ├── speakers/{speaker_id}/{filename}
    └── outputs/
        └── projects/{project_id}/{filename}   # 含渲染后的 MP4/SRT、quote card PNG
```

说明：

- 顶层目录直接用 `assets/`，不再包一层 `data/`
- 按 `user_id` 隔离；demo 资产使用固定的 `demo/` 前缀（如 `demo/uploads/projects/{demo_project_id}/...`）
- Demo project 的 `id` 是一个固定的 UUID（数据库 `Project.id` 为 UUID 类型，不能存字符串 `"demo"`）
- Demo project 和用户创建的正式项目**没有任何区别**，只有内容不同
- `uploads` 和 `outputs` 内部保留 project/speaker 子目录，方便按 project 清理
- Remotion 渲染服务直接输出到 `assets/`，`rendering.py` 通过 `out_subdir = "{user_id}/outputs/projects/{project_id}"` 保证路径一致

### 7.3 数据库变更

- `Asset` 表新增 `user_id: UUID`（nullable 或默认 demo user）
- `Speaker` 表已有 `user_id`，确保一致
- `Project` 表确认有 `user_id`（当前已有）

### 7.4 API / 服务层变更

- `app/services/storage.py`：
  - `save_upload(project_id, user_id, file)` → `assets/{user_id}/uploads/projects/{project_id}/{filename}`
  - `save_speaker_upload(speaker_id, user_id, file)` → `assets/{user_id}/speakers/{speaker_id}/{filename}`
  - `save_output(project_id, user_id, filename, content)` → `assets/{user_id}/outputs/projects/{project_id}/{filename}`
  - 所有读取/删除路径同步更新
- `app/routers/files.py`：
  - `/api/v1/files/{path}` 与 `/api/v1/outputs/{path}` 统一在 `assets/` 下解析
  - 读取 `user_id` 从 session/token，校验 path 是否属于该 user；`demo/` 前缀的资产作为公开 demo 放行
- `app/config.py`：
  - `asset_dir = Path("assets")`
  - 废弃或重定向旧的 `upload_dir` / `output_dir`（保留兼容也可）
- Remotion 渲染服务：
  - 输出目录指向 `assets/`
  - `app/services/rendering.py` 传 `out_subdir = "{user_id}/outputs/projects/{project_id}"`

注意：`assets/` 目录必须加入 `.gitignore`，避免上传用户文件到仓库。

### 7.5 迁移策略

MVP 阶段允许“破坏性”迁移（因为是 demo 环境）：

1. 新增 `user_id` 列，默认填充当前默认用户
2. 运行一次性脚本把旧的 `data/uploads/` 和 `data/outputs/` 移动到 `assets/{default_user_id}/`
3. 更新 `Asset.file_url` 相对路径前缀
4. 在 `.gitignore` 中加入 `assets/`

如果旧数据不需要保留，也可以直接清空并重新 seed。

---

## 8. Demo Project 规格

### 8.1 目标

让新用户首次进入 Home 时，能直接看到一个完整跑通的示例项目，证明产品价值。

### 8.2 实现方式

- 使用一个固定的 demo 用户 ID（可与默认用户一致，简化鉴权）
- 使用一个固定的 demo project UUID（例如 `11111111-1111-1111-1111-111111111111`），因为 `Project.id` 是 UUID 类型，不能存字符串 `"demo"`
- 在 `assets/demo/` 放置：
  - `uploads/projects/{demo_project_id}/demo_talk.mp4`（本地演讲视频，~2-5 分钟）
  - `outputs/projects/{demo_project_id}/` 下预生成产物
- 在数据库 seed 中创建：
  - `Project`：`id = {demo_project_uuid}`，`user_id = demo_user_id`，`title = "Example: AI Ethics Keynote"`
  - `Asset`：指向 demo 视频（`file_url` 以 `demo/...` 开头）
  - `Speaker`：demo speaker
  - `Derivative`：LinkedIn post、summary、quotes（quote card 带 `image_url`）
  - `Clip`：若干 clips（已有渲染文件，video_url 指向 demo 输出）
  - `Message`：一条 user message + 一条 assistant message（含 Tab 产物）

### 8.3 前端展示

- Demo project 出现在 Home 的 Recent projects 区域
- 与真实 project card 样式一致，左上角 `Demo` badge
- 行为和真实 project 完全相同，只有内容不同
- 在 Recent projects 列表中固定放在**最后**
- 如果用户没有任何 project，demo 自然显示在最前面
- 点击进入 `/projects/{demo_project_uuid}`，可播放、可下载、可 regenerate

---

## 9. 输出类型与 Tab 设计

### 9.1 MVP 输出类型

| 类型 | 后端 agent | 前端 Tab | 产物 |
|---|---|---|---|
| clips | clip generation | Clips | MP4 视频 |
| linkedin | derivative generation | LinkedIn | Markdown/Text |
| quote_cards | derivative generation + MiniMax image-01 | Quotes | PNG 图片（文生图） |
| summary | derivative generation | Summary | Markdown/Text |

### 9.2 意图识别（MVP 轻量版）

- **主机制**：用户通过 composer 的 checkbox 显式选择输出类型
- **辅助机制**：prompt 关键词匹配
  - prompt 含 “clip/short/video” → 自动勾选 clips
  - prompt 含 “linkedin/post” → 自动勾选 linkedin
  - prompt 含 “quote/card” → 自动勾选 quote_cards
  - prompt 含 “summary/abstract” → 自动勾选 summary
- **不做**：LLM 意图解析、自动推断语气/语言

### 9.3 多语言

- composer 中 `Language` 是主生成语言
- follow-up 可以用 `"generate German version"` 生成额外语言版本
- 每个 assistant message 的 Tab 内产物都是单一语言；如果需要多语言 summary，可以生成多个 assistant message，或在一个 Summary Tab 内用二级 tabs 切换语言

---

## 10. 组件清单

### 10.1 需要新增/重写的组件

| 组件 | 位置建议 | 说明 |
|---|---|---|
| `HomeComposer` | `apps/web/src/components/home/HomeComposer.tsx` | 内嵌 workflow 的 composer，替换当前首页输入 |
| `ProjectCard` | `apps/web/src/components/project/ProjectCard.tsx` | Home Recent projects 的卡片 |
| `RecentProjects` | `apps/web/src/components/home/RecentProjects.tsx` | 底部列表，含 demo |
| `ProjectResultsPage` | `apps/web/src/routes/projects.$id.tsx` | project 结果页 |
| `ResultsTabs` | `apps/web/src/components/results/ResultsTabs.tsx` | 顶部产物类型 Tabs |
| `ClipCard` | `apps/web/src/components/results/ClipCard.tsx` | clip 结果卡片 |
| `LinkedInCard` | `apps/web/src/components/results/LinkedInCard.tsx` | LinkedIn 文本卡片 |
| `QuoteCard` | `apps/web/src/components/results/QuoteCard.tsx` | quote card 图片卡片 |
| `SummaryCard` | `apps/web/src/components/results/SummaryCard.tsx` | summary 文本卡片 |
| `AssetActionBar` | `apps/web/src/components/results/AssetActionBar.tsx` | 产物卡片 hover/常驻操作栏（Edit / Chat / Download / Regenerate） |
| `AssetChatModal` | `apps/web/src/components/results/AssetChatModal.tsx` | 产物级 chat 精修弹窗 |
| `LibraryPage` | `apps/web/src/routes/library.tsx` | 资产库页面 |
| `AssetGrid` | `apps/web/src/components/library/AssetGrid.tsx` | Library 网格 |

### 10.2 需要调整的现有组件

| 组件 | 调整 |
|---|---|
| `app-sidebar.tsx` | 移除 Projects 入口 |
| `index.tsx`（Home） | 接入 HomeComposer + RecentProjects；保留当前其他布局 |
| `projects.$id.tsx` | 改为 ProjectResultsPage，不再展示 chat thread |
| `ChatComposer.tsx` | 用于 Home composer 和 AssetChatModal |
| `useGenerationFlow.ts` | 确保生成后正确跳转到 `/projects/$id` 并刷新结果 |

---

## 11. 后端 API 需求

### 11.1 已有 API（确认可用）

- `POST /api/v1/infer-intent` — 根据 prompt 推断生成参数（language/outputs/tone/instruction）
- `POST /api/v1/projects` — 创建 project
- `POST /api/v1/projects/{id}/assets` — 上传 asset
- `POST /api/v1/projects/{id}/generate` — 触发 generation（同时创建 ChatSession 并保存 prompt）
- `POST /api/v1/chat` — 产物级 chat：发送 message，解析意图并触发 background run
- `GET /api/v1/chat/session` — 获取或创建 project/asset chat session
- `GET /api/v1/projects/{id}` — 获取 project 元数据
- `GET /api/v1/projects/{id}/results` — 聚合查询：project + prompt + clips + derivatives + latest job
- `GET /api/v1/projects/{id}/assets/{asset_id}` — 查询 asset 处理状态
- `GET /api/v1/files/{path}` — 文件流
- `GET /api/v1/outputs/{path}` — 输出流

### 11.2 需要新增/修改的 API

| API | 方法 | 说明 |
|---|---|---|
| `GET /api/v1/projects/{id}/results` | GET | 聚合返回 project、原始 prompt、clips、derivatives、latest job |
| `GET /api/v1/library` | GET | 拉取当前用户的所有产物（uploads + clips + derivatives），支持 filter/type |
| `POST /api/v1/derivatives/{derivative_id}/regenerate` | POST | regenerate 某个 derivative（现有接口） |
| `POST /api/v1/clips/{clip_id}/regenerate` | POST | regenerate 某个 clip |
| `quote_cards` 图片生成 | - | 调用 MiniMax `image-01` 生成 PNG，保存到 outputs 目录 |
| `storage.py` 路径重构 | - | 见第 7 节 |
| `files.py` 鉴权 | - | 校验 user_id 所有权；`demo/` 前缀公开 |

---

## 12. 数据模型补充

### 12.1 Asset 表

新增字段：

```sql
ALTER TABLE assets ADD COLUMN user_id UUID REFERENCES users(id);
```

现有数据回填默认用户。

### 12.2 Derivative / Clip

确认已有 `project_id`、`target_language`、`derivative_type` 等字段。
Library 查询主要基于这两张表 + `assets`。

### 12.3 ChatSession & Message

MVP 阶段不展示全局 chat thread，但后端使用 `ChatSession` + `Message` 记录创作历史，并支撑产物级 chat：

```sql
-- ChatSession: project-scoped 或 asset-scoped 的聊天容器
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    project_id UUID REFERENCES projects(id),
    asset_id UUID NULL,
    asset_type VARCHAR(50) NULL, -- 'clip' | 'derivative'
    title VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

-- Message: 归属于一个 ChatSession
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES chat_sessions(id),
    role VARCHAR(50), -- 'user' | 'assistant' | 'system'
    content TEXT,
    attachments JSONB DEFAULT '[]',
    workflow_run_id UUID REFERENCES workflow_runs(id),
    intent JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);
```

`/api/v1/projects/{id}/generate` 会自动创建 project-scoped `ChatSession`，并把用户的 prompt 存为第一条 `Message`。`AssetChatModal` 读取/写入关联到 `asset_id` 的 session/message 记录，使每个产物拥有独立的 chat 上下文。

---

## 13. MVP 明确不做

| 不做 | 原因 |
|---|---|
| AI enhance（filler removal、hook、B-roll） | 后端/前端都重，Phase 2 |
| YouTube / 链接导入 | 下载/版权复杂，MVP 上传即可 |
| 多用户权限系统（完整 RBAC） | 默认用户即可，Phase 2 |
| Subscription / 支付 | 先 mock credits |
| Social 发布集成 | Phase 3 |
| Analytics / Calendar | 不是核心内容生成链路 |
| 复杂 onboarding tour | 最多 1-2 个 tooltip |
| LLM 意图识别 | 用显式 checkbox + 关键词 fallback |
| 多轨 NLE / B-Roll / 转场 / 自动人脸追踪 | 交给 CapCut/Premiere，不在 Repurposer 内做 |

---

## 14. 投资人 Demo 验收标准

1. 新用户打开 Home，看到 Hero + composer + Demo project card
2. 点击 Demo project，进入 `/projects/{demo_project_uuid}` **results page**，顶部看到 Tabs：Clips / LinkedIn / Quotes / Summary
3. 用户可以点击播放 clip、下载 quote card PNG、下载 LinkedIn/Summary Markdown
4. Clip 卡片提供 **Edit** 按钮进入 clip editor，提供 **Chat** 按钮打开 asset-scoped chat modal
5. 用户上传自己的素材、选参数、Generate，跳转到新 project 的 results page
6. 新 project results page 默认展示 Clips Tab，按网格展示生成结果
7. 用户可以切换 Tab 查看 LinkedIn / Quotes / Summary
8. Library 页面能看到所有产物
9. 文件存储按 user 隔离，demo 资产独立；quote cards 由 MiniMax image-01 生成 PNG

---

## 15. 备注

- 本规格基于当前代码（2026-07-04），如果实现时发现后端 agent 输出格式与前端卡片不匹配，优先调整前端适配后端
- UI 风格保持现有 shadcn/ui + Tailwind v4，禁止手写 SVG，icon 统一用 lucide-react
- 所有新增 copy 必须通过 i18n（先 en.ts，后 zh.ts）
- 不要为 demo 引入额外付费依赖或外部 object storage，全部走本地文件系统
- Quote card PNG 使用 MiniMax `image-01` 文生图接口生成，不手动拼接
- Demo project 使用固定 UUID 而非字符串 `"demo"`，因为数据库 `Project.id` 为 UUID 类型
