# Repurposer · Agent Editor v1

> Iteration 6A/6B（2026-11-21）：原生 export_video 已在隔离环境用私有成片完成真实渲染、审阅、恢复与交付。ExportJob 只处理已固定媒体。现有 TOS 桶允许公开读取，6D 云端验收只使用获准公开的合成素材。[验收与上线边界](agent-editor-evidence/iteration-6/export.md)

## Agent + Tool 唯一创作架构、后台执行退役与五面一体施工总合同

**状态：Iteration 1–5 已有真实成功样本；首次跨素材完整通过率 3/6；当前进行 Iteration 6D。原生媒体和导出在隔离库有 Job 验证记录，十用户和新素材全旅程待验收。**

**施工基线：2026-11-21，`main@fdd21443bed58a8b3a1eea1f7322d501e27f5e91`。开工时必须重新核对远端与本地 HEAD，不得将此 SHA 永久视为最新版本。**

**产品目标：2027 年具有专业剪辑能力、以自然语言为主要交互的 AI 剪辑师。**

**性质：第二次破坏性架构收口。不兼容已退役的 Graph / Plan / Run 创作与生产协议；必须保护真实用户作品、不可变版本、素材、历史交付、权限、费用和可靠执行。**

**本合同是 Agent Editor 的唯一主合同。**

`PROGRESS.md` 管理当前进度，领域文档描述实际机制。其他历史架构、ADR、研究与验收记录只能作为事实和设计依据，不得重新建立与本合同冲突的创作架构。

---

# 0. 总裁决

## 0.1 产品最终目标

Repurposer 是一个真正操作视频工程的 AI 剪辑师。

用户不需要学习时间线、关键帧、节点编辑器、图层管理或传统剪辑工作台。

用户只需要提供素材并通过自然语言表达要求。

例如：

> 这里有一段采访和几张图片，帮我剪成一条 30 秒的 LinkedIn 视频，保留重点，配上字幕和轻音乐。

Agent 应当像人类操作 Final Cut Pro：

1. 查看素材；
2. 理解用户的要求；
3. 创建 Composition；
4. 将素材插入 Track；
5. 分割、裁剪、移动 Clip；
6. 调整人物构图、大小和位置；
7. 插入字幕、图片、旁白和音乐；
8. 播放真实画面；
9. 根据观察继续修改；
10. 再次播放；
11. 判断是否满足用户目标；
12. 正式导出；
13. 审阅真实 Output；
14. 交付；
15. 接受用户后续自然语言修改。

唯一创作循环：

```text
User
  ↕
Agent
  ↓
Native Tools
  ↓
Composition / Media / Renderer
  ↓
Observed Results
  ↺ Agent
```

**作品是持续存在的，Agent 是持续工作的。**

不再通过一次性生成计划图来定义整个创作过程。

未来的画中画、蒙版、关键帧、抠像、运动跟踪和复杂动画，应通过具体 Tool 与领域执行能力逐项扩展，不得要求重新设计 Agent 主循环。

---

## 0.2 为什么必须彻底退役旧 Workflow

### 旧系统的问题

旧系统围绕：

```text
Chat
  ↓
LLM 生成 Plan / Graph
  ↓
系统编译 WorkflowRun
  ↓
创建 WorkflowSteps
  ↓
Worker 按步骤执行
  ↓
Output
```

构建。

这一架构产生于旧 Canvas 产品形态。

LLM 需要提前描述作品生产流程，Graph 固定结构，Run 负责执行，Step 负责具体阶段。

后续逐渐产生：

- `design_video`；
- `revise_video(ops[])`；
- Working Draft；
- Stage Router；
- Plan / Dock；
- 模拟 Start；
- Run / Step；
- 后台 Resume；
- Candidate Repair；
- Canvas Graph；
- 历史 Tool Exchange 回灌；
- 多套执行与展示状态。

真实失败包括：

- LLM 频繁返回错误的复杂 JSON；
- 自动修复循环直到上限；
- 草稿版本与执行身份脱节；
- 图片审阅把模型自选细节升级成硬性条件；
- 配乐已准备却在 Plan / Start 交接失败；
- Chat、Run、Canvas 同时表达创作进度；
- 用户的简单修改被迫进入复杂生产工作流。

这些问题不是通过继续增强 Router、Prompt、Workflow 或 JSON 修复器就能根治。

### 第一次破坏性重构已经完成的方向

Agent 直接调用：

```text
split_clip(...)
trim_clip(...)
move_clip(...)
translate(...)
scale(...)
generate_voice(...)
generate_music(...)
preview_range(...)
export_video(...)
```

真实修改保存在 CompositionVersion。

Agent 自己观察结果，决定下一步。

这已经在 Iteration 1–5 中得到真实验证。

### 第二次破坏性收口的原因

虽然模型已经不再直接理解 Run，部分原生 Tool 的后台实现仍然走：

```text
Native Tool
  ↓
TaskItem
  ↓
submit_confirmed_tasks
  ↓
create_run
  ↓
compile_graph
  ↓
WorkflowRun
  ↓
WorkflowStep
  ↓
Worker
  ↓
Run settlement
  ↓
Chat continuation
```

例如当前 `export_video` 仍会通过 `editor_media.py` 创建内部 `produce_video` 任务。

用户只要求导出一个固定 CompositionVersion，却仍要创建 WorkflowRun、WorkflowStep 和执行图。

更严重的是，同一任务的完成依赖多种状态的组合：

```text
Run.status
  × Step.status
  × Graph node.status
  × Output.render_status
  × Chat resume status
```

这种状态结构不再符合新产品的心智。

当前 Worker 回归已经出现：

- `workflow_step_fenced` 反复发生；
- Step attempt 达到数百次；
- 原本成功的接缝导出失败；
- 原本成功的片尾卡导出失败；
- 固定旁白恢复无法完成；
- Run 被取消而没有正式 Output。

这些是本次架构收口的直接动机。

但尚未证明每个故障的唯一根因都来自旧 Workflow。施工必须先调查实际首错节点，不允许把架构判断冒充故障归因。

### 正式裁决

**Agent Editor 不再使用 WorkflowRun / WorkflowStep 作为创作、媒体生成和视频导出的执行模型。**

删除旧模型并不意味着取消异步任务、Worker、持久执行身份、权限、费用、并发控制和恢复。

真正目标是：

```text
Agent Tool
   ↓
直接编辑
   或
明确的异步作业
   ↓
真实结果
   ↓
Agent 继续决策
```

**删除 Workflow，保留可靠执行。**

不允许把 WorkflowRun 简单更名为 Job，也不允许用第二套通用 DAG 替代旧 DAG。

---

## 0.3 不可妥协的架构原则

### A. Tool 就是操作

模型使用原生 Tool Calling。

Tool 只接受执行操作所需的最少参数。

不得要求模型构造：

- 通用 `ops[]`；
- 完整 Composition；
- Workflow DAG；
- WorkflowStep；
- 生产阶段列表；
- Job 内部状态；
- 费用账本事务。

Tool 负责校验、执行或提交异步任务。

### B. Composition 是唯一作品

Composition 是影片身份。

CompositionVersion 是不可变内容版本。

SourceSnapshot 是固定媒体身份。

Output 是正式渲染产物。

不创建第二套作品模型。

### C. 普通编辑不经过 Worker

分割、裁剪、移动、缩放、插入已经固定的媒体等操作直接通过现有编辑领域算法和 `apply_composition_edits` 保存新版本。

不能因为工具是由 Agent 调用，就把普通编辑包装为后台生产任务。

### D. Worker 不参与创作决策

Worker 不能自主决定：

- 下一步剪什么；
- 是否生成配乐；
- 是否插入旁白；
- 是否再次调整构图；
- 是否正式导出；
- 是否完成用户目标。

Worker 只负责执行一个已经确定的耗时任务。

完成后返回结果，Agent 再决策。

### E. Job 不是第二个 Run

新 Job 仅承担明确的异步操作。

不得拥有：

- 创作 Graph；
- 通用 Workflow Steps；
- 意图 Router；
- 执行 DAG；
- 下一步创作决策；
- 独立 Agent Context；
- 跨工具自动规划。

### F. Chat Activity 是执行事实的投影

用户看到：

- 正在生成配音；
- 正在渲染；
- 正在检查成片；

这些必须来自真实 Tool、Job 或观察动作。

Chat 不再建立一套独立的执行状态机来与后台任务同步。

### G. 五面一体

每个纵向施工切片必须同时实现或验证：

1. Tool Call；
2. Prompt / Context；
3. Chat Message；
4. Execution / State；
5. Recovery / Replay。

### H. 允许破坏性删除

旧路径已被新路径可靠替代时必须删除。

不为了旧协议兼容性维护第二套创作系统。

但历史作品、Output、账本、真实授权及未完成的外部操作，必须经过数据和消费者盘点后安全处置。

---

# 1. 已完成的 Iteration 0–5

本节保留真实历史，不将以前的成功样本改写为当前全面稳定。

## Iteration 0 — 审计与基础工具接通

完成旧架构消费者盘点。

确认现有编辑算法、Composition 写口、权限和费用基础应当复用。

实现第一次直接编辑闭环。

证据：

`docs/tasks/agent-editor-evidence/audit.md`

## Iteration 1 — 单个原生编辑 Tool

真实 MiniMax 调用：

```text
inspect_timeline
→ split_clip
→ preview_range
```

将第二段自身第 5 秒分割，作品时间切点位于第 8 秒。

保存新 CompositionVersion。

真实视频可播放，刷新后仍可恢复。

证据：

`docs/tasks/agent-editor-evidence/iteration-1.md`

## Iteration 2 — 连续基础剪辑

在一个用户回合中完成：

- split；
- trim；
- move；
- scale；
- translate；
- preview。

同一 Composition 从 v1 到 v6。

真实验证了版本竞争、Stop、提交后强杀和恢复。

没有建立第二套编辑引擎。

证据：

`docs/tasks/agent-editor-evidence/iteration-2.md`

## Iteration 3 — 媒体直接 Tool 化

Agent 能够：

- 生成图片；
- 生成旁白；
- 生成音乐；
- 固定媒体；
- 将媒体插入作品；
- 继续预览和编辑。

主样本 v1 → v3。

既有 Worker、SourceSnapshot、对齐和账本仍被复用。

本轮只是删除了模型可见媒体 Dock 和模拟 Start，尚未彻底退役内部 Workflow。

证据：

`docs/tasks/agent-editor-evidence/iteration-3.md`

## Iteration 4 — Studio UI 与多 Tool Calls

### 4A — 共享 Studio Shell

Home、Projects、Agent Thread 统一布局。

保留真实 Composer、附件、mentions、Skill、账户与路由。

首发只创建一个项目、一次用户提交。

### 4B — Agent Thread

真实 Chat、Tool Call、费用确认、Stop、版本和播放器在同一消息线程中工作。

历史消息和媒体可刷新恢复。

### 4C — 原生多 Tool Calls

同一次模型响应可以包含多个原生调用。

独立只读调用可并发。

作品写入按正确版本顺序提交。

媒体生成、费用授权和部分失败逐项处理。

已验证：

- 同名调用；
- 乱序完成；
- 外部版本竞争；
- Stop；
- API 强杀；
- Worker 晚到；
- 已提交结果恢复；
- 重复收费保护。

### 4D — UI 减法

删除失去消费者的旧 Shell、ChatDock、画布和重复呈现状态。

保留真实历史 Output、媒体播放器、费用和消息能力。

证据：

`docs/tasks/agent-editor-evidence/iteration-4/README.md`

## Iteration 5 — 自主审片、导出、交付和连续修改

已验证：

1. Agent 播放真实视频；
2. 发现空黑；
3. 自主移动 Clip；
4. 再次预览；
5. 正式导出 MP4；
6. 审阅真实 Output；
7. 在 Studio 交付；
8. 用户要求“结尾再留半秒”；
9. 保存新版本；
10. 导出新 Output；
11. 历史 Output 继续可播放。

随后完成构图观察与统一首稿的修复。

普通、网站、内置 Skill、外部 Skill 和可迁移历史草稿已统一使用 `create_video` 与唯一 Composition 写口。

旧模型可见 `design_video`、`review_working_draft` 已删除。

### 首次跨素材盲测

六个新独立素材：

| 素材 | 首次结果 |
|---|---|
| 单人讲话 | 部分 |
| 双人采访 | 完整 |
| 带字幕短视频 | 部分 |
| 真实接缝 | 完整 |
| 图片标题与片尾卡 | 完整 |
| 开放真实演讲 | 失败 |

**首次完整率 3/6 = 50%。**

原生 Tool 参数 64/64 合法。

这说明 Tool Schema 不再是唯一或主要产品问题。

Agent 仍需要提高：

- 创作目标理解；
- 实际观察；
- 正确工具选择；
- 停止判断；
- 输出交付；
- 自然语言事实准确性。

证据：

`docs/tasks/agent-editor-evidence/iteration-5/closure/cross-material/README.md`

### 首错最小修复

基线：`fdd21443`。

三项首错已定位：

- 单人讲话：把有限采样扩大为头肩完整性的确定结论；
- 带字幕短视频：审阅发现问题后仍交付且漏报；
- 开放演讲：已有 Composition 上误用 `create_video`。

本次增加证据充分时的停止规则，以及固定源音频事实。

原失败样本同源复测：

- 单人仍部分完成；
- 字幕本轮用户目标完整；
- 开放演讲已能导出并交付，但仍存在极窄留边误述。

新增两个独立素材的主任务完成。

然而三个原成功任务的回归出现：

- 接缝导出反复 fencing；
- 片尾卡导出反复 fencing；
- 固定旁白恢复失控。

因此，Iteration 5 不能宣称跨素材稳定性已关闭。

证据：

`docs/tasks/agent-editor-evidence/iteration-5/closure/cross-material/first-error-repair/README.md`

**以上历史验收全部保留，不回填首次分母，不用旧测试成功遮盖新回归失败。**

---

# 2. 唯一作品模型与直接编辑

## 2.1 保留的领域模型

继续使用：

- Project；
- Composition；
- CompositionVersion；
- Track；
- Clip；
- Object；
- Animation；
- Keyframe；
- Asset；
- SourceSnapshot；
- Output。

Composition 是持续存在的影片。

CompositionVersion 是不可变编辑版本。

SourceSnapshot 固定素材来源。

Output 固定由某个版本产生的正式媒体。

不引入新的 WorkDocument、TimelineRoot 或第二 CompositionStore。

## 2.2 唯一内容写入口

继续使用：

`apps/api/app/editing/store.py::apply_composition_edits`

所有编辑 Tool 必须：

- 校验 owner；
- 校验项目与作品身份；
- 定位真实目标；
- 校验时间和空间参数；
- 保护无关对象；
- 原子提交；
- 使用 CAS；
- 保留请求幂等；
- 返回真实版本和变更事实。

继续复用已有时间、来源映射、对象变换、动画、校验与版本算法。

可以保留内部 Op 数据结构，但不能让模型重新提交通用 Ops JSON。

不得为了消除 Op 名称而复制编辑算法。

## 2.3 并发编辑原则

同一 Composition 可以被不同用户回合或 Agent 操作请求访问。

多个读操作可以并发。

不同已固定媒体的生成可以并发。

同一 CompositionVersion 的竞争写入必须受 CAS 保护。

不允许两个独立写入都假设自己拥有最新 head 并静默覆盖对方。

同一模型响应内的已知顺序写入继续遵守 Iteration 4C 的版本链语义。

不允许通过新的 Job 系统绕开内容写口。

---

# 3. Tool 与 Worker 的唯一职责边界

## 3.1 判断一个操作是否需要 Worker

不能按“是不是 AI Tool”判断。

必须按操作的实际性质判断。

### 类型 A：即时读操作

例如：

- `inspect_timeline`；
- `inspect_clip`；
- 读取媒体元数据；
- 查询已有转录；
- 查询固定 SourceSnapshot；
- 读取 Output；
- 读取当前 Job 结果。

这些通常通过 API 和数据库直接完成。

不创建异步生产任务。

### 类型 B：即时编辑操作

例如：

- `split_clip`；
- `trim_clip`；
- `move_clip`；
- `translate`；
- `scale`；
- `insert_audio`；
- 未来的 `insert_clip`、`remove_clip`、`set_text`、`add_keyframe`。

只修改 Composition 内容。

直接走唯一编辑事务。

**禁止创建 WorkflowRun、WorkflowStep 或异步 Job。**

### 类型 C：有界预览计算

例如：

`preview_range`

正常短窗口直接向 Renderer 请求，获得实际画面与观察事实后返回。

预览不修改 CompositionVersion。

预览必须绑定：

- 确切版本；
- 内容 digest；
- 时间窗；
- 渲染参数；
- 实际解码帧；
- 媒体摘要。

短预览不需要持久 Job。

但必须限制 API 和 Renderer 的并发、内存、时长、字节及超时。

若长预览或高负载需要异步化，可以为预览建立有界作业或专用缓存；不得因此建立通用 Workflow。

### 类型 D：长耗时媒体生产

例如：

- `generate_image`；
- `generate_voice`；
- `generate_music`；
- 未来的视频生成；
- 复杂背景分割；
- 需要远端供应商或较长计算的媒体操作。

这些需要可靠异步执行身份。

Agent Tool 提交确定参数，Worker 执行，结果固定为媒体来源后交回 Agent。

### 类型 E：正式导出

`export_video`

需要固定作品版本、授权、导出规格、执行身份、渲染、上传和校验。

必须是可恢复的异步操作。

### 类型 F：后台业务与维护

例如资产处理、字幕对齐、定时发布、支付告警和清理。

这些可以拥有独立的领域状态与 Worker 消费者。

不要求全部包装为统一 Job。

---

# 4. 新异步执行契约

## 4.1 为什么需要 Job

Job 只解决一个问题：

**一个已确定的耗时操作，如何在多个用户、多个 Worker、进程崩溃、供应商超时和费用约束下可靠完成？**

Job 不是作品。

Job 不是创作计划。

Job 不决定下一步剪辑。

Job 不包含通用任务图。

## 4.2 最小持久 Job

对于 Agent 媒体生成和正式导出，允许使用一个轻量的持久异步执行契约。

逻辑字段包括：

```text
job_id
kind
owner_id
project_id
tool_call_identity
opening_id
input_ref
input_digest
idempotency_key
authorization_ref
status
attempt
claim_token
lease_expires_at
heartbeat_at
result_ref
error
cost / settlement_ref
created_at
updated_at
```

字段形状以真实数据消费者为准。

不要求逐字段新增数据库列。

可以利用现有实体的唯一职责减少字段。

不为了统一形式重复保存同一状态。

如果 MediaJob 与 ExportJob 共享最小执行机制，可以使用统一的作业记录。

不得让所有平台后台任务也强制迁移到这张表。

## 4.3 Job 状态

建议的最小语义：

```text
queued
  ↓
running
  ├─ succeeded
  ├─ failed
  ├─ cancelled
  └─ unknown
```

`unknown` 用于具有不可确认外部副作用的任务，不等同于普通失败。

后台安全重试可以从执行中的可恢复失败回到 `queued`，但必须有明确条件、重试预算和执行身份转换。

不能用无限重试代替失败处理。

不要增加：

- WorkflowStage；
- PlanStatus；
- GraphStatus；
- StepStatus；
- ChatResumeStatus；

作为并列的执行权真相。

## 4.4 唯一执行权

Job 的认领必须原子化。

建议复用现有 PostgreSQL 和 `FOR UPDATE SKIP LOCKED` 能力。

每次合法认领产生唯一 `claim_token`。

失去执行权的旧 Worker 不能再：

- 提交成功；
- 提交失败覆盖新执行；
- 写入正式 Output；
- 修改费用；
- 触发 Agent 继续；
- 重新提交供应商请求。

必须保留 CAS / fencing 的语义。

**可以删除旧 Workflow fencing 实现，但不能删除可靠执行 fencing。**

## 4.5 幂等与外部副作用

数据库事务可以保证一次确定性结果只提交一次。

但不能宣称任意供应商调用天然 exactly-once。

必须区分：

1. 尚未提交供应商；
2. 已提交，结果确认；
3. 已提交，结果未知；
4. 媒体已经固定；
5. 固定结果已结算；
6. 恢复只需继续后处理。

供应商支持请求幂等键时应使用稳定键。

不支持且无法确认结果时，保留 `unknown`，不得盲目重发。

固定 SourceSnapshot、费用和交付回执仍必须幂等。

## 4.6 授权与费用

旧 `hold_run / capture_step / release_run` 以 Run 和 Step 为身份。

新执行层不能继续为了调用这些函数而创建假 Run。

应将其正确的资金语义改接到 Job 执行身份。

必须保持：

- 权限先行；
- 真实估价；
- 费用上限；
- 用户授权；
- 原子预占；
- 成功时结算；
- 失败或取消时释放可释放部分；
- 未知供应商结果的谨慎处理；
- 重放不重复扣款；
- 不跨用户扣费。

同一 Job 的 hold、capture、release 必须有稳定幂等键。

旧账本及交易身份需要保留或经过明确迁移，不得因删除 Run 改写历史资金事实。

不以应用预估 USD 冒充最终供应商账单。

## 4.7 Stop / Cancel

Stop 必须区分：

- 未开始；
- 已领取；
- 正在进行本地计算；
- 已向供应商提交；
- 供应商结果未知；
- 已经固定媒体；
- 已经生成 Output；
- 已经交付。

Stop 阻止尚未发生的动作。

Stop 不能声称撤销已经产生的供应商费用或已固定的媒体。

已经提交的 CompositionVersion 和历史 Output 不应被 Stop 擦除。

取消后不能再因为晚到结果启动新的 Agent 编辑动作。

## 4.8 Worker 崩溃与恢复

Worker 可以被 SIGKILL、重启或失去网络连接。

必须证明：

- 未领取的任务仍可领取；
- 可安全重试的任务可以恢复；
- 已成功结果不会重复执行；
- 失去执行权的 Worker 不得写入；
- Unknown 任务不会自动重发昂贵供应商请求；
- 已固定媒体不会重复生产；
- 费用不会重复扣除；
- Chat 刷新能看到实际状态；
- Agent 可以继续原用户目标。

不新增第二个 Recovery Queue。

恢复依赖持久作业事实与现有 Chat opening / Tool Call 身份。

---

# 5. 十名用户并发：正式施工验收约束

## 5.1 并发不是十个 Run

必须支持至少十名相互独立的测试用户同时使用系统。

典型场景：

- 用户 A 分割视频；
- 用户 B 修改构图；
- 用户 C 生成旁白；
- 用户 D 生成音乐；
- 用户 E 导出 MP4；
- 用户 F 上传长访谈并请求 ASR；
- 用户 G 预览短窗口；
- 用户 H 导出另一部作品；
- 用户 I 查看旧 Output；
- 用户 J 在生成媒体时继续编辑当前作品。

这些操作不应该由于全局 Run 或项目级活跃 Run 限制而被不必要地串行化。

十用户是功能和并发正确性的最低验证场景，**不等于承诺十个大型渲染同时运行或保证特定吞吐与延迟**。

## 5.2 调度原则

后台作业必须具备：

- 有界并发；
- 按资源类型限制；
- 每用户或每租户公平性；
- 有界排队；
- 明确超时；
- 有界重试；
- 可观测队列等待；
- 过载时明确排队或拒绝；
- 多 Worker 安全认领。

不能由十名用户的十个耗时任务无限占满所有进程、数据库连接或供应商额度。

不能让一个用户的大量生成请求长期饿死其他用户。

公平性实现应先复用当前数据库和 Worker，只有实测证明不足才引入复杂调度基础设施。

## 5.3 资源隔离

至少区分：

- 即时 API 编辑；
- 短预览渲染；
- 供应商媒体生成；
- 正式视频渲染；
- ASR / 音频对齐；
- 后台维护任务。

不要求立即部署六套服务。

但必须在执行限制上保证重型任务不会阻塞短编辑与正常 Chat。

Renderer 有自己的并发资源上限。

不能因为十个正式导出请求就让所有短窗口预览超时。

数据库连接池与远端供应商并发必须有界。

## 5.4 并发版本

用户 J 在 v3 上继续剪辑时，用户 E 正在导出 v2，是合法的。

导出始终绑定 v2。

编辑可以保存 v4。

导出完成后 Output 仍指向 v2。

不能自动追随 head。

用户明确要求重新导出新版时，才创建新授权操作。

同一版本、同一规格、同一明确请求的重放应复用原结果。

不同明确请求可以产生独立执行身份，但应优先检查可安全复用的固定 Output，避免无意义重复渲染。

## 5.5 十用户验收

必须用真实数据库、API、Worker 和 Renderer 运行并发场景。

至少覆盖：

- 十用户身份和资源隔离；
- 同一 Composition 的竞争写入；
- 不同 Composition 的并行编辑；
- 两个独立导出；
- 生成与导出同时存在；
- 一名用户 Stop 不影响他人；
- Worker 重启；
- 第二个 Worker 与第一个 Worker 并行；
- 队列超限；
- 一个长任务不阻断其他人的短任务；
- 多个媒体任务完成后不会重复恢复同一 Agent Turn；
- 没有重复 Output、扣费或错误跨用户引用。

必须记录：

- Job 排队时长；
- 领取次数；
- 执行次数；
- 并发峰值；
- 完成及失败原因；
- 实际费用；
- 重复执行数量；
- 用户任务完成结果。

测试可以在有限资源下完成，不要求购买十倍供应商额度。需要付费的外部调用应使用受控预算；但关键生产行为仍须有真实端到端样本，不得仅用 mock 宣称完整验收。

---

# 6. Worker 现有职责最终裁决

本次审查确认 `apps/api/app/worker.py` 当前承担资产处理、Workflow 节点、正式渲染、旁白对齐、定时发布、支付告警和 staging 清理等职责。

不能把这些业务全部当作旧 Workflow 一起删除。

## 6.1 资产处理：保留

现有：

```text
claim_pending_asset
process_asset
```

包括：

- 素材摘要和哈希；
- 媒体探测；
- 文本提取；
- PDF 页面转换；
- ASR；
- 素材理解所需的预处理。

保留真实能力与独立 Asset 状态。

Agent 通过素材读取或明确处理请求触发必要分析。

不应因某个视频导出 Job 被创建，就默认激活所有无关素材。

必须从 `create_run()` 迁出其原有的隐式素材唤醒职责。

保留休眠素材与按需分析语义。

## 6.2 旁白与字幕对齐：保留

现有：

```text
request_alignment
claim_pending_alignment
process_narration_alignment
```

继续使用 NarrationAlignment 的固定媒体、文本摘要、模型版本、算法版本、lease 和 claim_token。

旁白生成完成后可以启动必要对齐。

对齐成功不等于必须把字幕插入作品。

插入仍通过 Agent Tool。

无需 WorkflowStep。

## 6.3 正式渲染：保留 Renderer，替换执行归属

保留：

- `compile_video_spec`；
- 固定来源；
- 真实 Renderer；
- 上传；
- 媒体解码与校验；
- Output；
- 缓存与可安全恢复的上传；
- 历史 Output 读取。

删除 Agent Editor 的：

- Render WorkflowStep；
- Render Step 镜像；
- Run finalization；
- Workflow Render Barrier；
- 因 Run/Step 终态派生的重复执行状态。

如果某个 Render Barrier 仍被非 Agent 业务使用，必须先明确其真实消费者并完成迁移，不能误删仍生效的授权或并发保护。

ExportJob 是导出执行身份。

Output 是最终媒体产物身份。

Job 与 Output 的状态不能成为两套相互竞争的执行权真相。

## 6.4 定时发布：保留

现有：

```text
claim_due_publication
process_publication
```

Publication 是独立业务对象。

保留自己的计划时间、平台回执、重试和失败语义。

不经过视频 Workflow。

未来 Agent 可以调用发布 Tool，但发布操作仍由 Publication 承担持久身份。

## 6.5 支付告警：保留

现有：

```text
flag_stale_webhook_events
claim_payment_alert
process_payment_alert
```

保留 Webhook 回执、outbox、lease、claim_token、有界重试和告警。

它不属于视频创作循环。

不得为了退役 Run 而改写 Stripe 入账和现有购买账本。

## 6.6 临时存储清理：保留

现有：

```text
reap_stale_staging_uploads
```

保留有界枚举、TTL 和引用检查。

不能删除仍被 Asset、SourceSnapshot、Output 或用户项目引用的对象。

清理任务无需 Agent Tool，也无需 WorkflowRun。

## 6.7 旧 Workflow 节点：退役

现有：

```text
claim_ready_node
execute_step
compile_graph
create_run
maybe_finalize_run
```

Agent Editor 不再使用这些函数完成媒体生成或导出。

旧 Workflow 所承担的：

- 权限；
- 报价；
- 预占；
- 认领；
- fencing；
- 超时；
- 结果固定；
- 结算；
- Stop；
- 恢复；

必须迁移到明确的 Tool / Job / 领域服务。

旧 Graph 回写、Step 下游跳过、Run 阶段推进、计划恢复等创作编排职责则直接删除。

不建立通用替代 DAG。

---

# 7. Chat、Activity 与 Agent 续行

## 7.1 Activity 来自真实执行事实

用户可见：

```text
正在查看素材
正在调整画面
正在生成旁白
正在渲染
正在检查成片
已保存版本
已生成素材
已完成交付
```

每条 Activity 必须来自：

- 实际 Tool 接受与执行；
- 已提交的 CompositionVersion；
- 已领取的后台任务；
- 实际媒体结果；
- 已确认的失败或取消；
- 已完成的真实预览或审片。

不能因为模型说“我正在生成”就创建虚假的后台工作。

不能在真实任务失败时把活动自动变成成功。

## 7.2 不要第二套 Chat 执行状态

Chat 的职责是持久消息及其呈现。

Job 的职责是异步操作执行。

Tool Call 记录调用身份与结果。

CompositionVersion 记录编辑内容。

Output 记录正式媒体。

Chat 不再需要独立维护与 Job 相互同步的 Resume 工作流状态。

可以保留必要的 opening、消息顺序、调用结果和恢复领取标识。

这些用于防止同一 Agent Turn 被多个恢复者重复继续，不构成第二套创作流程状态机。

## 7.3 异步工具续行

例如用户要求：

> 生成英文旁白，放到开头，然后导出。

正确行为：

```text
Agent 调用 generate_voice
    ↓
Tool 持久提交媒体 Job
    ↓
Worker 生成并固定 SourceSnapshot
    ↓
持久 Tool 回执确认结果
    ↓
同一 Agent Turn 获得实际结果
    ↓
Agent 调用 insert_audio
    ↓
CompositionVersion 更新
    ↓
Agent 调用 preview_range
    ↓
Agent 自主决定 export_video
    ↓
ExportJob 完成
    ↓
Agent 审阅并交付 Output
```

Worker 不能因为旁白成功就固定执行“插入 → 导出”的旧阶段链。

## 7.4 浏览器关闭与 API 强杀

用户关闭浏览器，不等于取消已经授权的后台生成。

Worker 仍可完成确定的 Job。

用户回来时，Chat 读取持久工具和 Job 回执。

如果原 Agent Turn 尚应继续，系统通过既有 opening / call ID 恢复一次决策。

必须保证：

- 同一个 Job 只对应一个确定结果；
- 同一个 Tool Call 只产生一份有效回执；
- 同一个 Turn 不被多个 Worker 同时恢复；
- 已完成的 Tool 不再次调用供应商；
- 旧版本观察不能替代当前版本；
- Stop 后不继续自动修改；
- 用户可看到真实结果和明确失败。

不恢复旧 `run_completed → trigger → Plan` 链。

## 7.5 多 Tool Calls

沿用 Iteration 4C：

- 独立只读可并发；
- 独立媒体生成在权限和预算内可并发；
- 同一作品写入按正确版本顺序；
- 新 ID 依赖必须等待真实回执；
- 同一回合多个 Job 完成后，只能有一个有效 Agent 续行执行者；
- 部分失败不抹掉独立成功；
- 未执行必须明确显示；
- Stop 按可证明的提交边界处理。

不引入通用 Tool DAG。

---

# 8. Prompt 与 Context 合同

## 8.1 常驻上下文

默认包含：

```text
用户当前目标
用户明确约束
Project
当前 Composition
当前 CompositionVersion
作品简要摘要
可用素材
最近有效观察
已完成操作
必要费用和授权事实
```

不默认注入：

- 全量历史 Tool Exchange；
- 整部 Composition JSON；
- 所有 Animation；
- 过时计划；
- 旧 Run Context；
- 已失效的观察；
- 完整 Job 内部日志。

## 8.2 按需观察

Agent 通过 Tool 获取：

- Clip 时间窗与源映射；
- Track 结构；
- Transform；
- 动画属性；
- 真实预览；
- 来源元数据；
- 字幕；
- 音频技术指标；
- 固定 Output；
- 历史版本。

观察必须绑定真实版本和时间窗。

## 8.3 主观判断的证据限制

模型不能把：

- 单帧观察说成整个时间段；
- 人脸框说成完整头肩；
- 极窄留边说成不存在；
- 静音源说成 Renderer 丢音；
- PCM 和波形说成自己听到了声音；
- Output 成功说成用户硬要求全部满足。

如无足够证据，应明确未知。

不通过无限增加禁词或无意义预览来代替真实判断。

## 8.4 停止条件

用户点名的要求已在当前版本得到必要观察，且没有待修问题时，Agent 应结束或完成明确要求的交付。

不因假设性瑕疵无止境重复审片。

不能仅以“20 次决策尚未用完”作为继续操作理由。

不提高决策上限来掩盖未收敛。

---

# 9. 破坏性删除与文档清理

## 9.1 删除原则

一条旧路径的真实消费者已经迁移并通过五面验收后，应在对应施工切片删除旧实现。

禁止长期保留：

- 新旧两套 Model Tool API；
- Workflow 兼容 Adapter；
- 第二执行队列；
- 旧 Graph 状态同步；
- 旧 Run 恢复路由；
- 过时阶段 Prompt；
- 无实际消费者的 Canvas UI；
- 无真实用途的测试 fixture 和旧工具定义。

不把无消费者代码标记为“暂时留着以备未来使用”。

## 9.2 历史业务数据

必须保护：

- Composition；
- CompositionVersion；
- SourceSnapshot；
- Output；
- 用户资产；
- 历史 Chat；
- 已支付费用；
- 历史交付；
- 正在执行或结果未知的任务。

6D 在独立测试库删除旧 Run、Step、Graph 及其关系。新部署从现行 schema 建立。作品按固定版本、快照、Output 与账本身份读取。旧 Run 数据转换不属于交付范围。

在途付费任务必须先盘点和安全迁移或结算。

不能通过删除表直接消除执行故障。

每片核对模型实际收到的工具名称、Schema、原生调用 ID、权限、处理函数、回执及下一次请求。记录初始、编辑后、媒体完成及恢复后的 Provider 消息。Chat 与 UI 以同一持久身份、顺序、固定版本和 Output 刷新，实测费用确认、Stop、Unknown 及部分成功。复用现有编辑、旁白、对齐、快照、渲染和钱包写口，记录本片删除的重复实现。Chat 契约稳定后在 iteration-6/ui-handoff.md 按文件交接 U3/U4。

## 9.3 文档退役

`new-agent.md` 是现行 Agent Editor 主合同。

必须核对并清理：

- `VIDEO_PROJECT.md`；
- `CHAT_ARCHITECTURE.md`；
- `MODULE_ARCHITECTURE.md`；
- `NAMING.md`；
- `PROGRESS.md`；
- `RENDERING.md`；
- `VERIFICATION.md`；
- `CLAUDE.md` 中与现行实现冲突的章节。

用户允许删除过时内容，而不只是添加“已废弃”的提示。

历史原始验收记录、事故证据和不可篡改的账本不属于可任意删除的过时内容。

删除规范时必须保证仍有一份明确的现行事实源。

---

# 10. Iteration 6：彻底退役 Agent Editor Workflow

**这是当前唯一优先施工主线。**

不是另起产品架构研究。

不是重写 Agent ToolLoop。

不是实现专业视觉功能。

目标是将已经确立的 Agent + Tool 产品心智落实到后台执行。

分为 6A、6B、6C、6D。

每个切片必须五面一体，并在通过真实出口后删除已替代的旧代码。

---

## Iteration 6A — 执行消费者审计与安全基线

**目标：明确删除边界，找到三个 Worker 失败的首错节点，并冻结现行资金、恢复和用户数据保护要求。**

### 代码审计范围

重点：

```text
apps/api/app/chat/editor_media.py
apps/api/app/chat/editor_recovery.py
apps/api/app/pipeline/orchestrator.py
apps/api/app/pipeline/jobs.py
apps/api/app/pipeline/rendering.py
apps/api/app/worker.py
apps/api/app/tools/video/production/
apps/api/app/tools/video/narration_store.py
apps/api/app/platform/billing.py
apps/api/app/tools/video/alignment_store.py
apps/api/app/distribution/
```

逐个回答：

1. 哪些函数仍为 Agent Editor 服务？
2. 哪些仅服务旧 Graph/Run？
3. 哪些拥有真实非视频业务消费者？
4. 哪些保存不可删除的费用和授权事实？
5. 哪些只负责状态镜像？
6. 哪些负责真实外部副作用？
7. 哪些可以由直接 Job 取代？
8. 哪些属于资产、发布、支付等独立领域？

### 必须分析的现有失败

- 真实接缝 `workflow_step_fenced`；
- 图片片尾卡 `workflow_step_fenced`；
- 固定旁白恢复 Unknown；
- Step attempt 数百次。

必须找到：

- 第一次错误认领；
- 实际 Run / Step 状态；
- claim_token 变化；
- 是否有多个 Worker；
- 是否发生启动时错误 reap；
- 是否存在无界重新认领；
- 是否实际重复调用供应商；
- 是否产生重复资金或媒体副作用。

**不允许以“旧架构太复杂”代替首错归因。**

### 五面出口

Tool：列出原生工具到旧 Workflow 的真实调用链。

Context：确认 Agent 实际仍只看到 Tool 和作品事实。

Chat：列出旧 Run 活动和真实媒体回执的消费者。

Execution：冻结版本、Output、资金、权限和异步执行正确性基线。

Recovery：确定 Stop、Crash、Unknown、Replay 的真实归属。

### 完成条件

交付：

- 函数级消费者清单；
- 删除目标；
- 必保留机制；
- 旧数据与在途任务盘点；
- 三项失败首错归因；
- 新 Job 最小字段和事务边界；
- 十用户并发测试准备。

6A 以审计为主，不提前开发新 Framework。

---

## Iteration 6B — 第一刀：ExportJob 替代视频 Workflow

**目标：一份已经保存的 CompositionVersion 可以不创建 WorkflowRun / WorkflowStep，直接可靠导出 MP4。**

### Tool

保留原生：

`export_video`

模型参数仍然最小化。

Tool 负责：

- 校验作品版本；
- 校验用户权限；
- 验证预览证据；
- 固定导出规格；
- 完成费用确认；
- 创建或复用 ExportJob。

### Context

向模型返回：

- 确切版本；
- ExportJob 状态；
- 当前实际结果；
- 已知失败；
- 成功 Output 引用。

不返回旧 Run 结构。

### Chat

用户看到真实的：

```text
正在导出视频
正在渲染
正在上传
正在校验成片
导出完成
```

这些是 Job / Renderer 事实投影。

不增加独立 Chat Resume 状态。

### Execution

保留 Renderer、视频编译、来源固定、上传和媒体校验。

ExportJob 拥有执行身份与恢复。

Output 固定正式产物。

取消对 Agent Editor 的：

- `TaskItem → create_run`；
- `compile_graph`；
- `WorkflowRun`；
- `WorkflowStep`；
- Render Step mirror；
- Run 完成才能交付的约束。

如果某些生产阶段确实需要进度显示，可以作为 ExportJob 内部阶段事实，而不是独立 WorkflowStep。

不允许为了兼容旧渲染器再造一个 Run Wrapper。

### Recovery

必须证明：

- 同一调用重放不重复导出；
- 用户明确再次请求可选择复用已固定 Output；
- Worker 强杀后安全恢复；
- 上传成功、确认前强杀可恢复；
- Stop 不删除历史 Output；
- v2 导出时 v3 可继续编辑；
- 费用只结算一次；
- 多 Worker 不重复提交同一 Job。

### 真实出口

必须复测：

1. 原成功真实接缝；
2. 原成功图片标题与片尾卡；
3. 已保存作品的普通 MP4 导出；
4. 导出中的版本继续编辑；
5. 两个不同用户同时导出；
6. 第二个 Worker 并行认领；
7. API 与 Worker 故障恢复；
8. 浏览器刷新后的正式 Output 播放。

所有出口必须不经过 Agent Editor 的 WorkflowRun / WorkflowStep。

**6B 通过后立即删除已经失去消费者的 Export Workflow 路径。**

---

## Iteration 6C — 第二刀：MediaJob 替代媒体生成 Workflow

2026-11-21 6C 记录为 **部分验收**。三类媒体已在 5966 直接执行。恢复 opening 中的新付费操作按具体 Tool Call、参数指纹和费用上限单独确认。6C 的旧图片归属调查与事故旁白记录归入历史证据。6D 只恢复现行 Job 回执。[本轮证据](agent-editor-evidence/iteration-6/media.md)

**目标：图片、旁白、音乐直接由原生 Tool 提交媒体作业，结果固定后交给 Agent。**

### Tool

保留：

- `generate_image`；
- `generate_voice`；
- `generate_music`；
- `insert_audio`；
- 现有媒体读取与对齐工具。

不新建第二套媒体 API。

### Context

媒体生成完成后返回：

- SourceSnapshot；
- 实际时长；
- 必要音频分析；
- Alignment 状态；
- 供应商结果状态；
- 实际费用；
- 可安全复用的固定媒体引用。

### Chat

Activity 由 MediaJob 的真实状态投影。

费用确认沿用现有用户交互。

用户不需要理解 Run、Step 或模拟 Start。

### Execution

删除 Agent Editor 对：

- `prepare_narration` WorkflowStep；
- `prepare_music` WorkflowStep；
- `prepare_visual_assets` WorkflowStep；
- 媒体 TaskItem → Run；
- 媒体 Run 完成触发器；

的依赖。

复用真实媒体生成与存储算法。

旁白可以继续利用已有 `VideoNarration` 的固定原音、内容哈希、Unknown 保护及对齐能力。

不能让 MediaJob 与 VideoNarration 同时成为两个竞争的供应商执行权真相。

需要明确：

- MediaJob 的请求与授权身份；
- 原音占位及供应商结果的唯一权威；
- SourceSnapshot 的不可变结果；
- 对齐的独立身份。

### Recovery

必须验证：

- 已固定原音复用；
- 音频固定后只恢复对齐；
- 未知结果不盲目重发；
- 同一回合多次生成不会重复扣费；
- 两个并发媒体任务有独立身份；
- 生成期间作品可继续编辑；
- 作品已改版时媒体仍可保留，但不能自动插入过期目标；
- Worker 强杀后结果仍可恢复；
- 多 Job 完成不重复唤醒 Agent。

### 真实出口

必须通过：

1. 原失败固定旁白恢复任务；
2. 同一作品生成旁白并插入；
3. 生成音乐并插入；
4. 图片生成并复看；
5. 旁白与配乐并发；
6. 生成期间用户修改 Composition；
7. 明确供应商 Unknown；
8. Stop；
9. 双 Worker；
10. Chat 刷新与续行；
11. 费用、快照和历史结果一致。

**6C 通过后删除已替代的旧媒体 Workflow。**

---

## Iteration 6D — 第三刀：全量减法与十用户闭环

**目标：Agent Editor 不再依赖旧 Workflow 创作与执行系统，现役后台任务保持正确。**

### 删除

核对并删除已失去真实消费者的：

- Graph 编译与旧节点执行；
- WorkflowRun/WorkflowStep 创作执行；
- Run 完成恢复链；
- Render Step mirror；
- 旧 Plan/Dock/Start；
- 旧专用媒体阶段；
- 无入口 Canvas；
- 无消费者 Prompt；
- 重复状态同步；
- 废弃工具注册；
- 无效兼容 Adapter；
- 失效规范和测试。

若某些 Workflow 仍被独立非 Agent 业务使用，必须明确其消费者，不能谎称全仓已经删除。

删除旧执行表、外键、模型、API、Prompt 与订阅，在独立库实测 DDL 和干净部署。共享库和在途资金须单独确认归属。

### Worker 收口

Worker 保留：

- Asset processing；
- NarrationAlignment；
- MediaJob；
- ExportJob / Renderer；
- Publication；
- Payment alerts；
- Staging GC。

不得恢复通用 Workflow DAG 作为上层调度中心。

### 十用户真实并发

必须包含：

- 即时剪辑；
- 多素材读取；
- 多媒体生成；
- 两个正式导出；
- 编辑与旧版导出并行；
- 对齐；
- Stop；
- Worker 重启；
- 双 Worker；
- 浏览器刷新；
- 权限隔离；
- 费用回放；
- 历史 Output。

记录排队、执行、失败和成本。

### 完整用户旅程

从新的素材开始：

```text
导入素材
  ↓
Agent 查看
  ↓
创建 Composition
  ↓
插入和编辑 Clip
  ↓
播放真实画面
  ↓
发现问题
  ↓
修改
  ↓
再次播放
  ↓
按需生成图片/旁白/音乐
  ↓
继续编辑
  ↓
正式导出
  ↓
审阅 Output
  ↓
交付
  ↓
用户再次修改
```

需要验证每个后台结果都有确切媒体或失败事实，不存在隐藏 Run 阶段。

### 完成条件

- Agent Editor 不再创建 WorkflowRun / WorkflowStep；
- 无第二 ToolLoop；
- 无第二作品模型；
- 无第二费用账本；
- 无第二 Chat 任务状态；
- 十用户并发基本正确性通过；
- 三项原 Worker 失败回归通过；
- 新独立素材完整旅程通过；
- 旧 Output 仍可播放；
- 没有重复扣费和无界领取；
- 失效规范与无消费者代码已经实际删除。

**6D 不得只提交删除清单，必须实际完成删除并提供消费者验证。**

---

# 11. Iteration 7+：专业剪辑能力

Iteration 6 关闭可靠执行之后，再按真实产品需求扩展：

- 插入和重排素材；
- 完整字幕编辑；
- 画中画；
- 多图层合成；
- Keyframe；
- Mask；
- Chroma Key；
- Foreground Segmentation；
- Motion Tracking；
- 高级动画；
- 更完整的视听审阅能力。

每一项新增能力通过具体 Tool 接入现有 Agent 主循环。

不得为专业能力预建第二套视觉工作台、Graph 或生产系统。

复杂操作可以异步计算，但最终写入仍由 Composition 编辑能力承担。

主观音频听感只有实际模型输入支持相应音频且有真实决策证据时才能宣称完成。

---

# 12. 每批五面验收

每一批报告必须包含以下七部分。

## 一、Git 与现场

- 本地及远端 HEAD；
- 工作树；
- 新增提交；
- 实际修改文件；
- 实际删除文件与函数；
- 用户已有修改是否得到保护；
- 是否只在 main 施工；
- 是否推送成功。

## 二、Tool Call

- 模型实际看到的 Schema；
- 原生 call ID；
- 参数；
- 合法率；
- 工具是否真正执行；
- 非法调用如何拒绝；
- 是否存在旧 Workflow 入口。

## 三、Prompt / Context

- 当前用户目标；
- 当前 Composition；
- 当前版本；
- 观察事实；
- 固定素材；
- 媒体 Job 回执；
- 无效历史是否被排除；
- 是否出现错误的版本或来源。

## 四、Chat

- 真实 Activity；
- 正文；
- 费用问题；
- 停止与失败；
- 媒体和 Output 卡；
- Live 与刷新；
- 是否出现重复活动；
- 是否泄漏内部执行身份；
- 是否诚实报告未满足的要求。

## 五、Execution / State

- 版本；
- Clip / Object 变化；
- SourceSnapshot；
- Job；
- Output；
- Renderer；
- 费用；
- 真实媒体；
- 无关内容保持；
- 队列和并发结果。

## 六、Recovery / Replay

- Stop；
- API 强杀；
- Worker 强杀；
- 多 Worker；
- StaleBase；
- 同参重放；
- 供应商 Unknown；
- 上传后中断；
- 幂等；
- 重复收费；
- 历史交付。

## 七、结论

严格使用：

- 通过；
- 有条件通过；
- 未通过；
- 未验证。

给出剩余真实阻塞。

不得用单元测试数量代替真实任务成功。

不得用同一素材反复重跑提高独立样本完成率。

---

# 13. 核心指标

继续记录：

- 首次 Tool 参数合法率；
- Tool 执行成功率；
- Agent 目标选择正确率；
- 真实观察后修订成功率；
- 无关内容保持率；
- 用户任务完整完成率；
- 正确停止率；
- 正式交付率；
- 视觉陈述正确率；
- 版本与 Output 一致率；
- 无效重复观察；
- 无效编辑；
- 模型请求次数；
- 输入与输出 tokens；
- 应用记录费用；
- 重复扣费次数。

Iteration 6 增加：

- Job 领取次数；
- 重试次数；
- 等待时长；
- 执行时长；
- 失去执行权次数；
- 终态收敛率；
- Unknown 结果数量；
- 同身份重复执行次数；
- 十用户并发结果；
- 不同用户间资源和费用隔离；
- 多 Worker 竞争正确率。

**必须区分三个产品成功维度：**

1. 作品是否正确；
2. Agent 判断及陈述是否正确；
3. 交付是否可靠。

完整用户任务需要三个维度共同满足。

---

# 14. 施工权限与停止条件

允许：

- 破坏性删除旧 Agent 创作协议；
- 删除无消费者 Workflow；
- 删除旧 Graph/Run/Step 的 Agent Editor 执行层；
- 删除旧 Prompt 与旧 UI；
- 更改不再使用的内部 API；
- 删除过时规范；
- 迁移与清理失效数据结构；
- 重组 Worker 调用位置；
- 直接在 main 上分片提交。

但以下情况必须停止相关变更并报告：

1. 可能丢失用户作品；
2. 可能丢失历史 Output；
3. 可能丢失已经付款的供应商结果；
4. 可能绕过权限；
5. 可能重复收费；
6. 可能破坏版本 CAS；
7. 可能绕过 Stop；
8. 可能让失去执行权的 Worker 提交结果；
9. 无法确认旧消费者是否仍存在；
10. 新路径未证明正确就准备删除唯一可执行路径；
11. 需要新建第二套 Agent、作品模型、ToolLoop 或 Workflow；
12. 为了通过测试而掩盖真实失败或修改测试分母。

不使用 `reset --hard`、`clean`、强制 checkout 或自动 stash 丢弃用户工作树。

不新建分支或 worktree。

按 main 的当前真实状态施工，保护未提交文件。

普通提交不能推送时报告原因，不强推，不假设远端已更新。

---

# 15. 完成定义

Agent Editor v1 的最终目标不是证明模型会调用工具。

这一点已经经过多轮真实验证。

最终需要证明：

**一个没有传统剪辑工作台的 AI 剪辑师，能面对不同用户与不同素材，理解创作要求，自主操作持续存在的 Composition，观察真实结果，正确继续或停止，最终交付可播放作品，并在并发、崩溃、费用和外部供应商失败时可靠恢复。**

最终架构：

```text
User
  ↕
Agent
  ↓
Native Tools
  ├── Immediate Editing
  │      ↓
  │   CompositionVersion
  │
  ├── Read / Preview
  │      ↓
  │   Renderer / Observed Facts
  │
  └── Async Media / Export
         ↓
      Job
         ↓
      Worker
         ↓
      SourceSnapshot / Output
  ↓
Observed Results
  ↺ Agent
```

其中：

- Agent 是剪辑师；
- Tool 是操作；
- Composition 是影片；
- CompositionVersion 是不可变编辑结果；
- Worker 是计算和外部执行能力；
- Job 是异步执行凭证；
- SourceSnapshot 是固定媒体；
- Output 是正式成片；
- Chat 是用户沟通与真实结果呈现。

**不再有一个位于 Agent 与真实操作之间的 WorkflowRun 创作控制中心。**

Iteration 6 关闭条件：

- 6A 首错及消费者审计完成；
- 6B ExportJob 真实替代旧导出 Workflow；
- 6C MediaJob 真实替代旧媒体 Workflow；
- 6D 删除已失效的 Run/Step/Graph 创作路径；
- 十用户并发正确性通过；
- 原三项 Worker 失败回归通过；
- 用户权限、版本、费用、Stop 和历史交付不回退；
- 新独立素材完整创作旅程有真实证据。

即便 Iteration 6 通过，也不能自动宣布跨素材普遍稳定或主观音频听感完成。

---

# 16. 下一批开工入口

**当前唯一授权主线：Iteration 6A → 6B → 6C → 6D。**

施工 Agent 首先阅读本合同全文，尤其是：

- §0 为什么彻底退役 Workflow；
- §3 Tool 与 Worker 边界；
- §4 Job 的最小持久执行契约；
- §5 十用户并发；
- §6 独立后台业务裁决；
- §7 Chat Activity 与可靠续行；
- §9 破坏性删除；
- §10 各切片真实出口；
- §12 五面验收；
- §14 停止条件。

然后核对当前代码。

不因旧函数名称存在就认为它必须保留。

也不因旧代码复杂就直接删除仍承担权限、计费或恢复职责的机制。

每一个反对意见必须给出：

```text
用户输入 / 初始状态
    ↓
实际代码路径
    ↓
错误动作或错误状态
    ↓
错误的用户结果
    ↓
最小修复
    ↓
真实验证
```

每一个新抽象必须证明为什么现有领域函数无法承担。

**施工总原则：尽可能删除旧架构，而不是在旧架构外再包一层新架构。**

**下一步先完成 6A 的实际消费者与故障审计，再以 6B 的单个 ExportJob 作为第一项真实破坏性替换；没有真实五面验收，不进入下一刀。**