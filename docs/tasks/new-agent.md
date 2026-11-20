# Repurposer · Agent Editor v1
## 破坏性架构重构与五面一体施工总合同

**状态：新主线 / 待执行**

**基准日期：2026-11-20**

**目标：2027 年具有专业剪辑能力的无工作台 AI 剪辑师**

**性质：破坏性重构；不要求兼容旧 Agent 创作协议，但必须保护用户作品、权限、计费与执行正确性。**

---

# 0. 总裁决

## 0.1 产品目标

Repurposer 不再以 Pipeline、Run、Step、Canvas Graph 或 Storyboard 生产流程作为 Agent 创作心智。

Repurposer 是一个真实操作视频工程的 AI 剪辑师。

用户通过 Chat 提供要求，Agent 自主查看素材，使用剪辑工具，观察真实画面与声音，判断下一步操作，持续修改同一 Composition，最终交付作品。

唯一行为循环：

```text
用户表达创作目标
    ↓
Agent 读取素材和当前 Composition
    ↓
Agent 选择并调用 Tool
    ↓
Tool 执行真实操作
    ↓
返回新作品状态或媒体结果
    ↓
Agent 查看/播放实际结果
    ↓
判断继续、修改、完成或失败
    ↺
```

不要求用户操作时间线、工作台、关键帧、蒙版或节点画布。

## 0.2 五项不可妥协原则

**原则 A：Tool 就是操作。**

`split_clip(clip_id, time)` 就是分割片段。

`translate(id, x, y)` 就是改变支持空间位移的可视对象的位置。

`trim_clip`、`scale`、`rotate`、`add_keyframe` 等工具同理。

模型使用原生 Tool Calling，提交最少的类型化参数。

不要求模型构造通用 `ops[]`、完整 Clip JSON、Animation JSON 或整部 Composition。

**原则 B：不创建平行 Op 体系。**

现有 Op 类型可以作为内部实现类型，但不能再存在与 Tool 平行的模型可见操作语言。

禁止：

```text
LLM
 → SemanticTool
 → SemanticAction
 → OpCompiler
 → GenericOps
 → EditingService
```

目标：

```text
LLM
 → split_clip(...)
 → 既有分割算法
 → 统一版本事务
```

不得为了追求形式上的零 Op 而复制稳定的算法、类型检查或数据库事务。

**原则 C：先全量暴露，再根据证据优化。**

初期将全部已经实现、能够真实执行的 Agent Editor 工具暴露给模型。

不通过另一个 LLM、复杂意图分类器或固定媒体阶段决定剪辑工具是否可见。

这里的“全量”仅指新 Agent Editor 的有效能力目录，不包括数据库管理函数、内部 Run 操作和废弃工具。

**原则 D：上下文以作品为中心。**

Agent 默认获得当前作品、版本、用户目标、素材目录和最近的有效观察。

复杂对象、时间线细节、历史版本和媒体内容通过工具按需读取。

历史 Tool Exchange 是审计和恢复数据，不是当前作品状态。

**原则 E：五面一体。**

每一项施工必须同时修改或核查：

1. Tool Call
2. Prompt / Context Projection
3. Chat Message
4. Execution / State
5. Recovery / Replay

一项工具仅后端可用，不等于 Agent 已掌握它。

---

# 1. 施工现场接管

## 1.1 已知基准

上一 Agent 报告的现场状态：

- `main` HEAD：`1dc14e7a`
- 工作树：20 个已修改文件
- 另有一个未跟踪的配乐事务测试
- §9A 图片审阅约束减法已在本地施工
- §9B 已授权 BGM 直接执行已在本地施工
- 最近定向回归 112 项通过
- 旧第二轮真实 Chat 尚未验收
- 另有正在运行或尚未结束的验收工作

以上是交接报告，不代表新 Agent 已重新核验。

## 1.2 开工前必须完成

新 Agent 首先执行只读现场调查：

```text
git status
git diff
git log
当前工作树与实际 HEAD
当前 API/worker 进程与代码重载方式
未结束的 Run、生成任务和测试项目
未提交文件的完整归属
```

确认旧 Agent 已停止写入。

不得在仍会被热重载的运行中服务上直接开展破坏性修改。

必须先建立可恢复的 Git 检查点：

- 保存所有属于已停止施工的本地成果。
- 保存未跟踪的必要测试文件。
- 不覆盖其他并行任务的改动。
- 不使用 reset、clean 或强制 checkout 丢弃工作。
- 若文件归属不能确认，先列出冲突，不擅自提交或删除。

建议检查点名称：

`checkpoint/pre-agent-editor-v1`

允许使用独立工作树或分支隔离施工。

检查点仅用于恢复工程成果，**不构成继续兼容旧架构的要求**。

## 1.3 对 §9A / §9B 的裁决

§9A 和 §9B 不继续作为旧第二轮专项任务推进。

新 Agent 应分别盘点其成果：

**§9A：**

保留用户要求、真实品牌事实、来源证据与模型自选拍摄手法之间的正确区分。

保留已经验证的图片审阅判断与快照复用。

删除不再需要的旧媒体阶段专用适配。

**§9B：**

保留已授权媒体请求直接提交、稳定调用身份、并发重放、费用与恢复保护。

取消旧 Dock / 模拟 Start 的入口和后续消费者。

如果成果只覆盖 BGM，允许作为新媒体 Tool 的第一条实现，不得误称图片和 TTS 已完成迁移。

---

# 2. 唯一作品模型与执行边界

## 2.1 保留的领域对象

继续使用：

- Project
- Composition
- CompositionVersion
- Track
- Clip
- Object
- Animation
- Keyframe
- Asset
- SourceSnapshot
- Output

Composition 是一部作品的持续身份。

CompositionVersion 是不可变的编辑版本。

Track / Clip / Object / Animation 是真实编辑对象。

Snapshot 固定素材来源和字节。

Output 是由确定版本制作的交付物。

不新增 WorkDocument、独立 Timeline Root、第二 Composition Store 或新的作品版本体系。

## 2.2 唯一写入口

继续使用现有 `apply_composition_edits` 及其事务保护。

所有写 Tool 都必须：

- 验证 owner 和当前作品。
- 定位真实对象。
- 验证操作参数。
- 保留无关内容。
- 原子提交新版本。
- 返回确定的实际变更。
- 保留请求幂等与版本竞争保护。

正常单一写 Tool 成功时，可直接生成一个新 CompositionVersion。

连续多动作暂不要求新建编辑 Session。

需要多动作原子执行时，复用现有编辑事务能力，不重新向模型暴露复杂批量 Op JSON。

## 2.3 内部 Run 的地位

Run、Step、worker 可以继续支持异步任务。

但 Agent 不需要：

- 创建 Workflow Run；
- 理解 Pipeline 节点；
- 模拟 Start；
- 根据 Run 阶段选择剪辑工具；
- 从 Run 恢复创作意图。

需要真实用户确认的动作继续使用授权机制。

已经授权的 Tool 调用不再经历重复的计划确认。

---

# 3. 工具体系：按真实操作组织

## 3.1 工具设计判断标准

每设计一个 Tool，只回答：

1. 它实际执行什么操作？
2. 修改哪些已有对象或产生什么结果？
3. 最少需要哪些参数？
4. 哪些对象类型支持该操作？
5. 哪些情况必须失败？
6. 执行后如何确认结果？

不得因为已有一套 Op 分类，就机械地产生第二套 Tool 分类。

一个内部算法只有一个实际实现。

一个模型可见操作只有一个权威入口。

## 3.2 目标工具目录

以下是目标能力目录。必须先核对已有实现，再按纵向切片接入。未实现或未验证的工具不得伪装成可用。

| 类型 | 候选 Tool | 最小语义 |
|---|---|---|
| 作品观察 | `inspect_project` | 当前作品和素材 |
| 时间线观察 | `inspect_timeline` | 目标时间窗及结构 |
| 对象观察 | `inspect_clip` | Clip 及其相关属性 |
| 媒体观察 | `inspect_media` | 视频、音频、图片、转写 |
| 分割 | `split_clip` | clip_id、time |
| 裁剪 | `trim_clip` | clip_id、时间边界 |
| 时间线移动 | `move_clip` | clip_id、目标时间 |
| 素材插入 | `insert_media` | source_id、目标位置 |
| 删除 | `remove_clip` | clip_id |
| 空间平移 | `translate` | id、x、y |
| 缩放 | `scale` | id、scale |
| 旋转 | `rotate` | id、angle |
| 透明度 | `set_opacity` | id、opacity |
| 关键帧 | `add_keyframe` | id、property、time、value |
| 删除关键帧 | `remove_keyframe` | 目标关键帧 |
| 文字 | `set_text` | id、text |
| 叠加 | `add_overlay` | source_id、目标范围 |
| 图片 | `generate_image` | 生成要求与必要证据 |
| 旁白 | `generate_voice` | text、voice 等必要参数 |
| 音乐 | `generate_music` | 时长、风格或必要乐谱信息 |
| 预览 | `preview_range` | 时间窗 |
| 导出 | `export_video` | 作品版本和交付规格 |

命名在施工中可按已有代码和对象语义调整。

`translate` 应明确表示空间位移；`move_clip` 表示时间线移动。二者不能混淆。

时间和空间坐标采用明确的单位及参照系。Tool 文档必须写清是 Clip 本地时间、作品时间、画布像素还是规范化坐标，不允许服务端猜测。

## 3.3 操作函数与内部 Op 的删除裁决

重点审查：

```text
apps/api/app/editing/edits.py
apps/api/app/editing/revisions.py
apps/api/app/editing/service.py
apps/api/app/editing/store.py
```

逐个判断：

- 哪些 Op 类是真实编辑算法需要的数据结构？
- 哪些只是从模型参数到同样参数的二次包装？
- 哪些展开函数重复完成目标定位？
- 哪些校验在 Tool 层和 Op 层重复？
- 哪些工具只是转发完整 JSON？
- 哪些可直接成为 Tool 执行函数？

删除重复入口和冗余转换。

保留真正必要的时间计算、来源映射、动画编辑、版本提交和原子性逻辑。

不得新建 Semantic Compiler 来替换旧 Op Compiler。

---

# 4. Tool 全量暴露策略

v1 不再根据 `draft_build`、`draft_review`、`draft_repair`、`version_edit` 等互斥阶段筛选基础剪辑工具。

默认向 Agent 提供全部可执行的 Agent Editor 工具。

无当前 Composition 时，读取、素材处理和创建作品的工具仍然可以使用；编辑已有 Clip 时由服务端检查目标是否存在。

唯一保留的门控：

- 用户权限
- 工具是否真正实现
- 资源是否存在
- 当前版本是否有效
- 媒体依赖是否就绪
- 费用和安全授权
- 当前执行是否允许并发
- Stop / Cancel

这些是执行约束，不是创作流程阶段。

不新增专门的意图识别 Router。

待建立真实使用数据后，再评估工具目录是否需要按任务裁剪。

---

# 5. Prompt 与 Context 重构

## 5.1 总规则

Tool 可以全量暴露，Context 不全量注入。

模型应该自己决定要观察什么，而不是让系统先替模型决定下一步操作类型。

上下文统一来自当前作品、素材、用户约束和工具观察。

## 5.2 常驻上下文

默认组装：

```text
当前用户要求
明确的用户约束
当前 Project
当前 Composition
当前 CompositionVersion
当前作品简要摘要
已有素材目录
最近有效执行结果
必要的权限和费用状态
```

不得默认注入：

- 完整 Composition JSON
- 全部 Clip 和 Animation
- 完整历史 Tool Exchange
- 全部旧失败候选
- 过期 Run 计划
- 已被当前版本覆盖的历史规格

## 5.3 按需观察上下文

Agent 使用工具获取：

| 当前任务 | 观察内容 |
|---|---|
| 分割 Clip | Clip 时间窗与源时间映射 |
| 裁剪 Clip | 当前边界及相邻片段 |
| 移动时间线 | 目标 Track、碰撞及空隙 |
| 平移与缩放 | 当前 Transform 和画布 |
| 动画 | 已有关键帧和时间轴 |
| 生成媒体 | 素材需求、品牌事实、作品状态 |
| 预览 | 精确版本、时间窗和真实视听证据 |
| 交付 | 当前版本、依赖、制作要求 |

观察结果必须标明版本、范围和来源。

不得把旧预览作为当前版本的证据。

## 5.4 历史上下文

继续持久化 Tool Exchange 以支持：

- 请求恢复
- 故障取证
- 历史比较
- 用户要求的回滚
- 当前未完成候选的精确恢复

但不再默认把旧工具调用完整模拟成当前对话的 assistant/tool 消息。

当历史信息确实影响任务时，通过读取工具按需获取。

当前作品事实始终优先于历史模型陈述。

## 5.5 创作约束

必须明确区分：

**用户硬要求**：明确指定的交付条件与真实来源。

**叙事目标**：观众需要理解的信息。

**创作选择**：模型自主选择的镜头、构图、机位和表现手法。

模型自选细节不能自动变成硬性验收条件。

审阅结果应推动 Agent 修改实际内容，而不是要求它无限满足自己以前写下的表现细节。

---

# 6. Chat Message 合同

## 6.1 用户可见内容

Chat 只呈现：

- 正在查看素材
- 正在分割片段
- 正在调整画面
- 正在生成旁白
- 正在检查局部预览
- 完成了哪些修改
- 真实可播放的结果
- 具体失败与合理下一步

用户无需理解 Clip ID、Op、Run ID、Step 或内部 digest。

## 6.2 活动与完成分离

每个 Tool 必须区分：

- 已接受
- 正在执行
- 已完成
- 已失败
- 确实需要用户确认

这只是模型和用户的执行结果语义，不要求新建持久状态机。

工具被接受不等于编辑已经完成。

版本生成不等于视频已经渲染。

视频渲染完成不等于 Agent 已审片。

## 6.3 消息恢复

刷新后通过持久结果重建消息和组件。

重复执行事件不得产生重复的交付消息。

后台恢复不得把旧的 Run 文案重新呈现为用户必须操作的工作流指令。

---

# 7. 破坏性删除范围

## 7.1 优先移除

重点盘点并删除旧创作消费者：

```text
chat/turn_tools.py
chat/plan_turn.py
chat/media_journey.py
chat/service.py
chat/conversation_context.py
chat/video_turn_seats.py
```

包括：

- 模型可见的普通 `present_plan / propose_tasks / start_run`
- 媒体 Tool 转待启动计划
- 自动 Dock 和模拟 Start
- 旧媒体阶段独占工具集
- 旧 draft 阶段专用创作路由
- 模型可见的 `revise_video(ops[])`
- 旧 Canvas Graph 工具投影
- 无消费者的旧 Prompt、状态映射和文案
- 重复的编辑操作展开及候选修复分支

以上为删除目标，不允许在没有调用方调查的情况下盲删函数。

旧实现一旦由新路径可靠替代，应直接删除，不开发兼容适配。

## 7.2 不删除的可靠性能力

- `apply_composition_edits` 的唯一版本写入
- CompositionVersion 不可变身份
- owner 和权限保护
- Request ID 幂等
- Stale Base / CAS
- SourceSnapshot 字节与 digest 保护
- Worker claim token
- 支付 hold / capture / release
- 供应商结果未知时的恢复
- Stop / Cancel
- 渲染产物完整性检查

这些可以重组调用位置，但不能静默取消。

## 7.3 数据处理

允许破坏旧 API 和旧模型协议。

不允许直接删除已有用户作品与账本。

历史 CompositionVersion、SourceSnapshot 和 Output 应能继续通过当前存储协议读取，除非另有经过数据盘点的明确迁移决定。

不做大范围历史数据迁移来维持旧 Agent 行为。

---

# 8. 五面纵向施工计划

每一轮必须同时交付：

1. Tool Call
2. Prompt/Context
3. Chat Message
4. Execution/State
5. Recovery/Replay

不得分拆为五个互不相关的任务。

## Iteration 0：现场保护与旧架构切除图

**目标：建立真正可施工的删除清单。**

Tool：
- 列出所有当前模型可见工具。
- 标记保留、替换、删除及未实现项。
- 找出重复入口。

Context：
- 列出阶段门控、上下文组装和历史恢复路径。
- 确认哪些旧事实仍被注入模型。

Chat：
- 标记旧 Plan / Run / Canvas 文案及触发位置。

Execution：
- 标记真正实现编辑、版本、计费和任务调度的函数。
- 识别不可替代消费者。

Recovery：
- 确认现有幂等、Stop、回放和数据库事务边界。

**出口：** Git 检查点、函数级删除清单、迁移次序及真实行为基线。

不得新建框架。

## Iteration 1：单一 Agent 工具面

**目标：取消旧创作 Tool 协议。**

Tool：
- 将已实现的基础剪辑工具作为模型可见能力。
- 去掉重复 `ops[]` 创作入口。
- 不再让模型使用 Plan / Start 操作普通剪辑。

Context：
- 当前用户目标与当前作品直接投影。
- 移除旧阶段作为工具可见性的前提。

Chat：
- 使用真实动作活动与结果。
- 删除不必要的计划确认文案。

Execution：
- 直接复用当前 Editing Service 与唯一版本写入。
- 旧协议对应消费者迁移后删除。

Recovery：
- 版本重放、目标失效、Stop 与刷新继续成立。

**真实出口：** Agent 在真实 Chat 中能读取一个现有 Composition，并调用有效的基础剪辑 Tool。

不得以单元测试直接调用后端代替原生 Tool Calling。

## Iteration 2：真实基础剪辑循环

**目标：Agent 能连续操作同一 Composition。**

Tool：
- `inspect_clip`
- `split_clip`
- `trim_clip`
- `move_clip`
- `translate`
- `scale`
- `preview_range`

具体范围按现有算法可用性裁决，不为测试虚构能力。

Context：
- 当前 Clip、时间映射、空间变换、相邻对象和必要素材。
- 每次修改后更新版本及变更摘要，不重注入全量历史。

Chat：
- 展示实际动作、预览和完成结果。

Execution：
- 正确分割、裁剪、移动与视觉变换。
- 单动作原子保存。
- 不改变无关内容。

Recovery：
- 断线重放不重复分割。
- 刷新获取相同版本。
- Stale Base 不覆盖新状态。

**真实出口：**

用户要求：

「把这个片段从中间切开，缩短前半段，后半段移到后面，再检查播放效果。」

Agent 自主选择并执行工具，实际产生新版本，并观察局部视频。

## Iteration 3：媒体生成直接 Tool 化

**2026-11-20 验收登记。** 原生 MiniMax 回合在已有 18 秒访谈中生成英文旁白和轻电子配乐，经两次独立插入将同一作品从 v1 写到 v3。局部混音 MP4 已解码，Chrome 刷新后实播。图片生成、原音与配乐复用、Alignment READY、真实费用同意后续剪、API 与 Worker 在交付前强杀并重启后的续剪均有独立记录。模型听感、生产部署与主观成片质量未验收。具体失败样本、费用、版本与证据见 [Iteration 3 施工与验收记录](agent-editor-evidence/iteration-3.md)。

**目标：图片、TTS、BGM 成为普通可调用创作工具。**

Tool：
- 复用现有真实图片、旁白和配乐能力。
- 去掉已授权工具的 Plan / Dock / 模拟 Start。
- 保留真实费用确认。

Context：
- 只注入生成当前素材需要的信息。
- 允许在编辑途中生成新媒体，再回到 Composition。

Chat：
- 显示真实生成进度和可用产物。
- 不显示 Run 启动仪式。

Execution：
- 保留 worker、缓存、快照、实际计费和媒体分析。
- 不复制执行引擎。

Recovery：
- 同一调用重放取回原执行。
- 不重复扣费。
- 作品变化后不误用过期结果。
- 后台恢复能把工具结果交回 Agent。

**真实出口：**

在已有 Composition 中按需生成一段英文旁白或 BGM，并继续进行剪辑，最终得到真实可播放结果。

不得要求用户再输入 Start。

## Iteration 4：动画与专业视觉操作

**目标：扩展真正的专业剪辑能力。**

Tool：
- 关键帧
- 叠加
- 画中画
- 蒙版
- 必要的抠像与运动跟踪

实际能力按底座与执行证据分批接入，不得用占位 Tool 冒充实现。

Context：
- 当前 Object、图层、关键帧、画布和局部时间范围。

Chat：
- 显示当前制作效果及实际预览。

Execution：
- 使用现有 Composition / video-spec / Renderer。
- 只修改目标对象。
- 不创建第二套合成引擎。

Recovery：
- 版本隔离、局部失效、失败恢复和复用已通过内容。

**真实出口：**

用户要求：

「把演讲者放在右边，左边展示 PPT。第三秒人物缩小，PPT 放大，然后淡出。」

Agent 自主执行并预览实际动画。

## Iteration 5：审片、连续修订与交付

**目标：完成真正的剪辑师行为。**

Tool：
- 检查真实视听内容
- 按需局部修改
- 导出当前作品

Context：
- 当前版本、用户目标、受影响范围、实际媒体证据。

Chat：
- 正确区分制作、审片和交付。
- 用户可直接查看最终作品。

Execution：
- 渲染真实 MP4。
- 技术检查与模型视听观察分别记录。
- 不以 Run 完成冒充作品完成。

Recovery：
- 渲染缓存、幂等交付、失败重试和刷新回读。

**真实出口：**

用户只用自然语言完成一条多素材视频剪辑任务，Agent 能观察、修改、继续观察并交付可播放 MP4。

---

# 9. 每轮必须提供的验收证据

每次汇报固定包含：

```text
一、现场与代码
- HEAD / 工作树 / 本轮提交
- 实际删除的文件、函数、分支
- 保留的底层算法和事务

二、Tool Call
- 模型实际看到的工具列表
- 每个工具实际 Schema
- 原生调用轨迹
- 参数错误及拒绝原因

三、Prompt / Context
- 本轮实际注入的信息
- 当前作品和目标引用
- 上下文 Token
- 被排除的无关历史
- 是否出现过期事实

四、Chat
- 用户实际看到的活动、正文和结果
- Live 与刷新后的状态
- 是否泄漏内部 Run/Op/Plan 语言

五、Execution
- 实际版本变更
- 正确对象、正确时间和空间
- 真实预览与媒体结果
- 无关对象是否保持

六、Recovery
- 重放和并发结果
- Stop/Cancel
- Stale Base
- 供应商未知结果
- 幂等与费用事实

七、结论
- 已通过
- 未通过
- 未验证
- 下一项真实阻塞
```

禁止把「测试全部通过」等同于真实 Agent 任务通过。

## 9.1 核心指标

记录：

- 首次 Tool 参数合法率
- Tool 执行成功率
- Agent 目标选择正确率
- 真实观察驱动修订成功率
- 无关内容保持率
- 单个任务模型调用次数
- 上下文和输出 Token
- 重复执行与重复扣费次数
- 用户任务真实完成率

测试失败时，先区分模型选择、工具参数、执行逻辑、上下文、消息和恢复故障，不允许无限增加重试。

---

# 10. 施工权限与停止条件

允许破坏性删除旧 Agent 创作逻辑。

允许不兼容旧工具 API、Prompt 和内部阶段定义。

不要求旧官网宣传片四轮流程继续通过。

但以下情况必须停止相关修改并报告：

- 需要删除无法恢复的用户作品数据；
- 需要绕过权限和费用授权；
- 会破坏原子版本提交或幂等保护；
- 无法确认某段代码仍被哪个真实消费者使用；
- 新路径无法证明正确，却准备删除唯一可执行路径；
- 需要引入第二套执行、编辑或上下文真相。

工程缺陷必须如实报告，不允许通过静默 fallback 或伪造预览宣布完成。

---

# 11. 完成定义

Agent Editor v1 完成时，必须达到：

**用户不操作剪辑界面，Agent 能够直接调用真实剪辑工具，在同一个 Composition 上持续工作，并根据实际画面和声音修订作品。**

最终产品心智：

```text
User
  ↕
Agent
  ↓
Tools
  ↓
Composition / Media / Renderer
  ↓
Observed Results
  ↺ Agent
```

Run/Step 退到内部执行层。

Canvas 不再承担创作规划或执行身份。

不再要求 LLM 生成底层 Op JSON。

不再维护新旧两套模型可见剪辑协议。

不再用固定 Pipeline 阶段决定 Agent 的下一步行动。

**最终验收以真实剪辑效果、连续操作能力、上下文可靠性和用户任务完成率为准。**

---

# 12. 给施工 Agent 的第一条指令

请先接管当前工作树，建立可恢复 Git 检查点，确认上一轮验收进程不会与新施工混用代码。

随后执行 Iteration 0 的函数级消费者盘点，给出明确的删除清单。

进入 Iteration 1 时，不再提出新的 Agent 架构。

直接使用现有 ToolLoop、Editing Service、Composition Store 和 Preview，建立单一模型可见剪辑工具面。

每个施工切片必须同时闭合 Tool Call、Prompt/Context、Chat、Execution、Recovery 五个方面。

在同一批真实验收通过之后，立即删除已经失去消费者的旧创作路径，而不是长期保留双轨兼容。

**这次要减少系统，而不是在系统上继续增加新的层。**