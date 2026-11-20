# Repurposer · Agent Editor v1
## 破坏性架构重构与五面一体施工总合同

**状态：Iteration 1–4 已在隔离环境按各轮出口验收。下一项为 Iteration 5 的自主审片与正式 MP4 交付。**

**施工基准：2026-11-21，Iteration 4 从 main @ 32f04518 开工。**

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

## 1.1 已验收的起点

原生 Tool、作品 Context、唯一版本写口及其恢复语义沿用前三轮结论。下表限定已验证的范围。

| 批次 | 可复查的事实 |
|---|---|
| 现场审计 | 检查点 `09cf1873` 保存原合同。§9A 的图片审阅与来源约束、§9B 的授权、幂等及费用保护归入直接 Tool 路径。[消费者与事务审计](agent-editor-evidence/audit.md) |
| Iteration 1 | `inspect_timeline → split_clip → preview_range` 将指定 Clip 在自身第 5 秒分割，在 v2 播放成片第 7–9 秒。模型读到实际画面，刷新后仍播放同一窗口。[原生调用与验收](agent-editor-evidence/iteration-1.md) |
| Iteration 2 | 一个用户回合分割、裁剪、移动、缩放、平移，同一 Composition 从 v1 递增至 v6。两张预览卡可独立恢复，已验证 Stop、StaleBase 及版本提交后进程中断。[逐版差异与恢复](agent-editor-evidence/iteration-2.md) |
| Iteration 3 | 旁白、配乐各自生成并固定，再分别插入同一作品，主样本 v1 → v3。保留 Worker、来源快照、对齐和账本，退役普通媒体 Dock 与模拟 Start。已验证局部混音实播与故障续剪；模型听感和自主审阅正式 Output 待验。[媒体回执与验收](agent-editor-evidence/iteration-3.md) |

## 1.2 每批开工核对

核对实际分支、HEAD、工作树、相关服务与并行施工归属。沿上述审计复核本批涉及的现役消费者。在独立工作树或可恢复的 Git 检查点施工，保护未跟踪文件和运行中的用户工程。无法确认归属时保留现场，不使用 reset、clean 或强制 checkout 丢弃工作。

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

以下是候选能力目录，施工顺序见 §8。关键帧及复杂合成归 Iteration 6+。必须先核对已有实现，再按纵向切片接入。未实现或未验证的工具不得伪装成可用。

| 类型 | 候选 Tool | 最小语义 |
|---|---|---|
| 作品观察 | `inspect_project` | 当前作品和素材 |
| 时间线观察 | `inspect_timeline` | 目标时间窗及结构 |
| 对象观察 | `inspect_clip` | Clip 及其相关属性 |
| 媒体观察 | `inspect_media` | 视频、音频、图片、转写 |
| 分割 | `split_clip` | clip_id、time |
| 裁剪 | `trim_clip` | clip_id、时间边界 |
| 时间线移动 | `move_clip` | clip_id、目标时间 |
| 素材插入 | `insert_audio`（已验证） | 固定音频来源、作品时间、增益 |
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
- 已失败、已停止或未提交及其原因
- 确实需要用户确认

这只是模型和用户的执行结果语义，不要求新建持久状态机。

工具被接受不等于编辑已经完成。

版本生成不等于视频已经渲染。

视频渲染完成不等于 Agent 已审片。

## 6.3 消息恢复

TurnBlock 按用户回合组织正文、活动、问题、作品与媒体块。在线用 Chat SSE 更新同一消息，刷新用持久消息及其回执重建。重复、乱序和晚到事件按身份与顺序合并，保留正文与卡片的相对位置。Run SSE 只报告相应后台工作。

每个调用可从所属 opening 回溯原生 call ID、工具名、调用顺序、实际状态、自然语言摘要、实测耗时、真实结果引用及失败或停止原因。尚未提交的调用标明原因，缺少计时的历史行不补造耗时。版本卡固定 CompositionVersion、digest 与窗口，素材卡固定 Asset / SourceSnapshot，交付卡固定消息引用的 Output。引用失效时明确提示，不以当前 head 或最新 Output 补位。

分组由同一回合、同一次模型决策及其有序调用推导，在正文、确认或交付块处断开。默认显示“正在查看时间线”“正在调整片段”等折叠活动行，多个相关调用可展开逐项查看允许展示的参数摘要、耗时和诊断。长任务只保留一处真实进度；前端定时动画不得触发结算、写回消息或重复播报活动。

---

# 7. 破坏性删除范围

## 7.1 优先移除

以下为历轮消费者盘点入口。Iteration 1–3 已删除的分支见 §1.1；后续只检查实际剩余调用方。

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

以下 Iteration 0–3 记录既有基线及各轮验收范围。下一项施工从 Slice 4A 开始。

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

## Iteration 4｜Studio UI 与多 Tool Calls（4A–4D 已实测）

统一 Studio 经真实 Home 首发、历史深链、编辑、音视频播放和硬刷新验收。同一模型响应的独立读取可并发，媒体和作品写入逐项受费用、Stop 与版本校验约束。外部抢写和提交后回执前强杀均已复现。付费供应商结果未知仅有受控故障注入覆盖。逐项结果、失败样本、调用身份、费用与浏览器证据见 [Iteration 4 验收](agent-editor-evidence/iteration-4/README.md)。

一个登录后 Studio 承载 Home、Projects 和项目 Agent Thread。用户能从素材和一句要求开始，在同一作品上连续对话、查看修改结果，并在刷新后接着工作。全站采用 affectUI Clean 的字体、颜色、圆角、间距与导航层级，共用现有主题偏好，覆盖浅色、深色、跟随系统及移动端。

**接入基线。** Web 声明 React `^19.2.0`。修订时本地工作树有 `@affectui` Registry 配置及未跟踪的 `thinking-loader.tsx`，两者均未进入基准 main；本机可读 affectUI 与 screens 等 Skills，MCP 可取下列源码。所列条目中，Tool Call Card / Group 为 Free，其余为 Pro。这些目标组件尚未落入项目 UI 目录。施工时按实际 import 核对依赖，尤其是 `@hugeicons/react`、`@hugeicons/core-free-icons` 和多个 Clean 子组件；整页示例有传递依赖。

| 已核源码（Registry slug / 导出） | 接入边界 |
|---|---|
| App Shell Inset · `app-shell` / `AppShell` | `children` 承载页面，`nav`、`active`、`onNavigate` 对接真实路由，账户来自 session。源码默认展开面板（`defaultPanelOpen=true`）并带示例项目。首批只取外壳，去掉示例入口。 |
| AI Chat / Start · `assistant-home` / `AssistantHomeScreen` | 内置 AppShell、示例会话与本地 `replyFor`。采用启动页布局，保留产品 Composer 和实际提交链。 |
| Folders / Overview · `files` / `FilesScreen` | 整页内置 AppShell，数据接口是 folders / templates。只取作品库布局与搜索排序交互，直接消费 Project。 |
| Agent / Thread · `agent-thread` / `AgentThreadScreen` | 内置 AppShell。源码支持 `messages`、`decisions`、`onSend`、`onStop`、`onDecide`、`upload`，`ThreadPart` 的 tools 分组接收 `ThreadTool[]`。采用线程结构与折叠行。示例 Stop 会先修改本地消息再触发回调，接入时以服务端 Stop 回执结算。消息槽保留产品的引用、Markdown、确认和播放器。模拟回复、上传、离线补发及文件名驱动的示例产物不得接管会话。 |
| Chat Composer · `chat-composer-clean` / `ChatComposer` | `onSend(message, {model})` 和菜单 `onAttach(item)` 不携带完整引用、Skill 或上传回执。通过现有编辑器及发送动作接线，费用同意仍走服务端问题。 |
| Tool Call Card / Group · `tool-call-card-clean` | 同文件导出 `ToolCallCard` 和 `ToolCallGroup`。Group 接收卡片 children；卡片仅有 running / success / error。普通调用优先 Thread 活动行；待授权、停止、未提交用真实语义显示，禁止映射成成功或错误。 |
| AI Answer · `ai-answer-clean` / `AIAnswer`；Thinking State · `thinking-state-clean` / `ThinkingState` | 前者接受 `answer`、`sources`、`streaming`，仅解析部分 Markdown；保留现有 Streamdown 的完整正文表现。后者用 `steps`、`stepMs` 定时展开，只有真实活动可支撑时才采用其呈现。 |

三个整页组件均以共享布局中的**内容区**接入，不能原样嵌套整页。视觉适配只消费既有 API、Chat SSE 与持久记录；不得新增 Workflow UI 表、第二套 Agent 状态或媒体投影。

**产物范围。** 保留用户点击既有产物后的 Inbox、详情弹窗、图片查看与音视频播放。当前可定位的入口是 Chat 消息、项目的 `chat/outputs` 投影、`ChatOutputViewer → MediaLightbox`、`StoryboardCard → CompositionPreview` 及 `AudioPlaybackSurface → WaveformPlayer`；“Inbox”沿用这些真实引用和入口，不要求创建同名路由。允许为共享 Shell 适配尺寸、主题与焦点。可拖拽分隔线、复杂审看模式、多标签素材区、自动聚焦时间码、完整 Inspector、多窗口布局及大型右栏管理系统均留待后续按需安排。

### Slice 4A｜共享 Shell、Home 与 Projects

| 面 | 同片交付 |
|---|---|
| Tool Call | Home 一次提交把原请求交给项目 Chat，再由原入口进入 ToolLoop。保留 staging 上传、附件、mentions、Skill 及 persona 选择。 |
| Prompt / Context | 原文与结构化引用随 `firstMessage` 交接，保留选区与来源归属。精选示例仅预填，登录返回继续原草稿。 |
| Chat Message | 一个开场用户消息。Home 保留输入、添加素材、发送；移除重复分类、空货架与吸底变形。Projects 从项目 API 展示名称、实际封面或可靠占位、更新时间，按名称搜索、基本排序并打开原项目。 |
| Execution / State | `_app.tsx` 现持 Sidebar 与 MobileHeader，Home、Projects 列表在其下；`_app.projects.$id.tsx` 只有 Outlet，实际 `projects.$id.index.tsx` 在生成树里直属 root，独挂 ProjectHeader、ChatDock。调整文件路由父子关系，由共享布局持唯一导航和 Outlet，保留项目 URL、鉴权、账户、设置、积分和通知。按路由源重新生成 `routeTree.gen.ts`。 |
| Recovery / Replay | 沿 `HomeComposer → useProjectLaunch → assets/from-staging → location.state.firstMessage → AgentThread` 核对交接：Home 建项目并关联已上传素材，只有项目 Chat 发首条 POST。保留历史加载屏障、results 与持久用户行核对。施工前只有挂载 ref，历史读取异常曾放行发送。现由持久 opening 和历史加载屏障共同保护首发。提交结果未知先回读，禁止因重挂、慢历史或读失败自动重复发送。 |

**出口。** 用桌面和移动端实走登录 → 上传并带引用发送 → 项目 Chat，核对请求数、开场行、附件与 ToolLoop 回合各自身份；双击、刷新、返回再进均只留下同一次提交。深链、Projects 搜索排序及历史项目打开正确，导航和账户可用。首页不建设运营系统，作品库不增加团队、文件夹管理或工作台。

### Slice 4B｜Agent Thread 接通项目对话

| 面 | 同片交付 |
|---|---|
| Tool Call | 现役编辑与生成工具从项目 Chat 原入口发起，Stop 绑定 opening，问题和费用确认绑定原消息。 |
| Prompt / Context | 续聊仍携当前作品、版本、用户约束及有效观察；从产物引用继续编辑时校验引用对象与归属。 |
| Chat Message | 复用 `ChatConversation`、TurnBlock 与 timeline 的逐消息位置。用户引用、中外文流式 Markdown、活动、问题、批准/拒绝、错误、作品卡及播放入口各有真实来源。 |
| Execution / State | `chat-stream.ts` 的 `streamChat` / `streamAnswer` 仍接 Chat SSE；`use-run-events.ts` 仅供关联的后台 Run。接通现有 Stop、QuestionDock、费用授权和失败反馈，调用接受、版本保存与产物可播放分别取对应事实。 |
| Recovery / Replay | 从会话 messages 和对应回执恢复，合并未结束活动及后续 SSE。同一工具、问题、正文或交付卡只显示一次。旧消息固定原版本与窗口，已归档 Output 按原 ID 打开。 |

**出口。** 在真实项目发送编辑要求，看到流式正文和工具活动；分别实测 Stop、同意、拒绝、失败、刷新和继续编辑。点击已有素材、音频、预览及正式产物，验证弹窗或播放器实际加载；推进 head 后刷新并重开旧卡仍命中原媒体。

### Slice 4C｜一次模型决策中的多调用、分组与恢复

施工前的两个前台 Chat 入口已启用 `service_per_call`。当时 `tool_loop.py` 的批次预检会检查 terminal / `batchable`，同名组才可能使用 `finish_batch`；前台缺少该收尾时会在执行前拒绝整批，允许的批次仍按循环逐项执行。Iteration 3 的 mix 样本中，合法的旁白和配乐被整批拒绝后再逐个调用。目标是在既有 ToolLoop 内按下表处理同一原生响应的多个调用，不能仅因数量大于一而拒绝。[实际调用](agent-editor-evidence/iteration-3/native-calls.json) · [每轮输入及观察](agent-editor-evidence/iteration-3/provider-wire.json.gz)

| 调用关系 | 执行与失败语义 |
|---|---|
| 独立读取 | 对同一明确版本或独立来源的只读观察可安全并发。记录各自版本、范围和耗时；完成先后不改原调用次序。 |
| 独立媒体生成 | 在权限、逐项费用上限、余额及资源允许时可并发提交或执行。生成固定素材，插入另算一次作品写入。待确认项按原回执暂停，不得借同批其他调用的授权。 |
| 同一 Composition 写入 | 对本次决策时已知且可独立定位的目标，按原生顺序逐项走唯一写口。首写校验观察时的 base，后写校验本批上一笔提交的确切版本与目标前置条件；外部抢写返回 StaleBase，回模型重读。不得把未知的新 head 自动当作自己的 base。 |
| 结果依赖与终结 | 需要刚生成的 SourceSnapshot、分割所得 Clip ID 或前一项的观察判断时，先把真实结果交回模型，下一次决策再调用。猜测 ID、前置失败或引用失效的写入标为未执行。终结回答或交付须等相关结果落定，不短路尚未记录结果的同批调用。 |
| 部分失败与 Stop | 各项分别标明已提交/完成、待授权、失败、停止、未执行或供应商结果未知。独立成功保留；后续有依赖或安全性无法确定时停止该项并写明原因。Stop 与每次提交按既有锁排序，保留先落库的版本、快照与费用，停止新提交，按原执行身份处理在途工作。 |

| 面 | 同片交付 |
|---|---|
| Tool Call | 保留一条 assistant 原生调用列表及各自的 call ID、参数、序号和 Schema 校验。合法组按上述语义执行，无需通用 DAG、变量引用语言或新 Scheduler。 |
| Prompt / Context | 在下一次模型决策前按 call ID 对齐每一项 tool 响应，包含已生效、失败及未执行项。投影提交后的作品版本、固定结果与仍有效的观察；涉及新 ID 或外部改版时由模型重新选择。 |
| Chat Message | 修正 ActivityProjector 的单一开放调用槽，以及媒体提交按活动 key 选最近活动行的关联方式。按 opening、原生调用、ToolExchange 的 iteration / call_index 关联实际 Activity 与持久消息，确保同名调用和乱序完成仍归到各自活动行；依 §6 展开分组，不跨正文或问题合并。只暴露用户可读且获准展示的事实。 |
| Execution / State | 并发工作隔离数据库会话与调用上下文。逐项保存实际提交/完成次序、请求指纹、版本或媒体回执。沿用唯一版本事务、Worker claim、报价及 hold/capture/release；同身份同参重放取原结果，异参拒绝。 |
| Recovery / Replay | 崩溃后按原 opening 与各 call ID 核对版本、执行、快照及账本；供应商结果未知时先对账。已提交的调用不可重跑；待授权、未开始、中断和已完成的调用按事实恢复。多个 Worker 完成不得各自重复续剪；历史与 live 复建同一组和每个结果。 |

**出口。** 用真实模型在**一次响应**发出多个调用，逐项对照 wire、下一轮 Context、持久消息、版本及账本。至少覆盖独立读取、旁白与配乐同批、同一作品两个顺序写入与外部竞争、生成后下一次决策使用真实来源 ID 插入、部分失败。另测同名调用、乱序完成、费用拒绝、批中 Stop、提交后回执前强杀、重启重放与浏览器硬刷新。已成功的项仍可查可播，未执行的项无写入，恢复无重复扣费、版本或交付消息。

### Slice 4D｜退役重复界面与消息路径

4D 不是集中删除阶段，而是最终清算阶段。每完成 4A、4B、4C 中的一个纵向切片，必须在同一个提交范围内删除已被替代、无真实消费者的旧实现，并提供消费者搜索与删除证据。禁止以“留待 4D 统一清理”为由保留双轨代码。

| 面 | 同片交付 |
|---|---|
| Tool Call | 沿路由及调用方盘点旧启动按钮、模拟操作和重复发送入口；仅删除已由 4A–4C 实证替代且无消费者的路径。 |
| Prompt / Context | 清除旧 UI 阶段对工具与当前作品的重复投影；同一续聊只消费现役作品事实。 |
| Chat Message | 移除失去消费者的旧 Chat Shell、重复 Sidebar、Run 展示、活动卡、阶段文案与视觉组件，保留历史消息和产物的读取能力。 |
| Execution / State | 删除废弃的状态同步、订阅和路由入口；权限、计费、Worker、播放器、Inbox 及媒体访问仍走已核验的执行路径。 |
| Recovery / Replay | 通过新 Thread 打开旧项目、历史问题、已停止和部分完成的回合，刷新、播放并续聊。无旧 UI fallback。 |

**出口。** 提交调用方与删除清单，沿唯一项目入口复跑 4A–4C 的真实旅程；确认无双 Shell、双发送、双订阅或重复活动。通过后进入 Iteration 5。

## Iteration 5｜自主审片与正式视频交付（必做，待验收）

用户要求完成作品后，Agent 在当前 Composition 上检查、观察、修订、再观察，固定通过审片的版本，导出正式 MP4，审阅该 Output 的实际字节，再在 Chat 交付。基础闭环使用已有编辑能力。

| 面 | 同片交付及证据 |
|---|---|
| Tool Call | 原生轨迹包含检查 Composition、取得实际视听证据、因已识别的问题选择具体编辑 Tool、再看同一受影响窗口、固定版本并导出、读取和审阅真实 Output。保留模型据以选择下一步的观察。 |
| Prompt / Context | 每次观察绑定版本、媒体来源、时间窗与用户要求。代码校验来源、版本、解码、时长和音视频轨等技术事实。Agent 根据实际画面与声音判断内容、节奏和混音。要声称听见问题，必须有可感知音频的模型实际收到相应声音并据此判断的独立记录；波形、响度、ASR 和轨道存在只能支持各自的技术结论。缺少听感证据时该项待验。 |
| Chat Message | 分别报告局部修改、审片意见、正式导出和最终交付。成功消息引用实际 Output，Inbox/播放器从同一引用播放原片；看不到、听不到或导出失败时说明具体缺口。 |
| Execution / State | 经现有钉版制作、快照、Renderer 与 Output 路径导出可解码 MP4。核对 Output 与不可变版本、来源、交付规格一致。Agent 打开正式产物审阅；发现问题则继续修订并重新钉版、导出、审阅，不能沿用旧 Output 的结论。 |
| Recovery / Replay | 重试或重启取回原导出身份、固定版本和 Output；未完成或失败的审阅不得生成成功消息。重复回读或推进 head 后，已交付消息仍只指向原片，不重复渲染、扣费或交付。 |

**真实出口。** 同一用户任务从多素材作品到可播放 MP4，提交一次“实际观察发现问题 → 局部修改 → 再观察”的前后对照、正式 Output 的技术检查与模型审阅，以及 Chat / Inbox 刷新后实播证据。仅有局部预览、Run completed 或渲染任务完成均不能关闭本轮。

## Iteration 6+｜按需扩展专业剪辑（可选独立批次）

可按作品需求接入图片插入、overlay、画中画、复杂图层、关键帧、蒙版、色键抠像、前景分割（segmentation）、运动跟踪及高级动画特效。它们均不阻塞 Iteration 4、5 或 v1 验收。

每批用一个明确的 Tool 接入现有 ToolLoop。Context 提供目标图层、属性、时间与版本；Chat 呈现实际局部预览；Execution 在现有 Composition / video-spec / Renderer 中实现领域算法；Recovery 核对版本隔离、未改对象及故障重放。例如新增关键帧能力时，应从用户要求走到指定时刻的真实动画预览。缺少算法先实现并验证，再暴露 Tool，避免为扩展重写主循环或预建通用视觉平台。

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

Iteration 4 的证据按 4A–4D 分别登记。4C 报告模型响应数、同批原生调用数、合法数、实际提交数及逐项结果，区分同一回合连续决策与一次响应多调用。Iteration 5 的最终凭据须能从 Chat 消息追到经审阅的固定版本及可播放 Output。

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

**v1 关闭条件。** Iteration 4 的统一 Studio 和多调用回放通过真实对话验收，Iteration 5 完成对正式 Output 的自主审阅与交付。以实际视听证据、连续修订、版本及消息一致性和用户任务完成率核验。

---

# 12. 下一批施工入口

核对最新 main 和 §8 验收记录后，从 Iteration 5 开工。沿同一 Agent Thread 观察并修订当前 Composition，固定审阅通过的版本，渲染正式 MP4，再审阅该 Output 的实际字节并交付。沿用 §9 的五面凭据与 §10 的停止条件。Iteration 6+ 依独立需求立项。
