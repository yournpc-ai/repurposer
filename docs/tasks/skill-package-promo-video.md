# Video Project 当前施工、真实验收与精确编辑

> Status: 直接 Op 与当前工作面合同已落码，真实视听、发布与完整精确编辑仍开放（2026-11-17）。优先级见 [PROGRESS](../PROGRESS.md)，长期作品契约见 [VIDEO_PROJECT](../VIDEO_PROJECT.md)，官网宣传片分批见 [官网证据链](website-promo-evidence-brief-workflow.md)。

## 0. 当前硬边界

- 不引入新作品根、第二意图面、第二内容写口、第二生产链、运行期镜头注册表或通用插件平台。作品内容只经 `apply_composition_edits` 形成 CompositionVersion。
- 首稿经 create_video 直接保存 CompositionVersion，局部修订经原生编辑工具调用 apply_composition_edits。
- 模型每轮只读取当前工作面：当前 base_ref、目标现值、相关来源、实际选区、当前错误和兼容工具。旧参数、旧媒体和已覆盖结果在完整送达一次后按现有生命周期退役，不叠加成第二份作品状态。
- Generator 允许 Agent 按创作需要现场编写完整 draw-2d 或 Remotion 工程，包括多文件、组件、共享 helper、视觉公式和内部时间线。限制的是权限、依赖、资源和隔离执行，不是工程内部的视觉创意。
- 直接 Op 不是自由代码通道；Generator 也不是业务调度、数据库、任意网络或任意文件通道。外部 Skill 脚本和 TSX 仍只是不可信参考，读取不等于执行授权。
- 原生文字、字幕、声音和需要独立精修的对象保留原生身份；Generator 只烘焙其负责的视觉范围。最终 video-spec 仍只消费固定媒体，不含 React/Remotion、生成任务或模型请求。
- Skill 只保存创作方法、模板、Preset、参考和声明资源，不进入 worker，也不在修订时重新执行。制作继续钉版本、来源、依赖和 digest，恢复不重新创作。
- 支付、通用 Chat 基础设施和其他非 Video Project 工作归各自合同，不借本计划扩大范围。

## 1. 统一 Skill 与 Generator 资源

随应用部署的内置包从 app/skills 加载。promo-video 从 MANAGED_SKILL_ROOT 下的配置版本加载，外部 SkillVersion 按 owner 和不可变版本读取。

`list_skill_shots / read_skill_reference / read_skill_demo / get_skill_preview` 继续提供有 owner、路径、文本和媒体边界的读取。模型可见工具按当前 Skill、草稿、版本、Output 与真实制作意图逐轮投影；完整工具结果按 call id 回传，权限、来源、取消、失败和制作授权不因投影改变。

Generator producer 继续为 `draw-2d / remotion-project / image-generation`。完整程序来源包含文件及 digest、入口、Composition id、props/schema、固定资源、依赖锁、输出约束与执行摘要；预览和制作复用同一来源 digest 的真实固定结果。只改原生文字不得使 Generator digest 或固定媒体失效，修改 Generator 不得重写未改原生层。

## 2. 当前协议与投影验收

- fake provider 捕获每次实际 `messages + tools`，覆盖首稿续写、当前版本编辑、局部修复、结果折叠与恢复；不得只验证函数返回值。
- 第二幕写入不得重带第一幕完整提交参数；当前版本编辑不得带无关作品、无关 Clip 或完整 Op union；当前目标只暴露兼容 Op。
- 直接 Op 批必须覆盖多个相关修改只落一个版本、整批校验、stale base、目标歧义、越权来源、重复请求和失败零部分写入。
- Output region 继续作为 `output` mention 的字段，保存帧时间、源像素、归一化区域和视口事实；本轮只投影当前候选目标，不把 region 当作已完成像素编辑。
- 真实模型的小样本工具调用可以验证直接 Op 的可用性，但不能据此推断通用成功率。不同目标、复合修改和真实旅程仍需分别验收。

### 2.1 当前工作面的字段合同

ContextSnapshot 刷新项目资源，RoundAssembly 投影当前工具、证据和已保存版本。

| 当前工作 | 默认保留字段 | 默认不投影 |
|---|---|---|
| 官网证据 | 当前 URL、采集状态、真实正文和页面视图、已有品牌依据 | 其他项目或页面的证据 |
| 新建作品 | 当前用户需求、显式 Skill、已准备的来源 | 历史样片内容 |
| 审片 | 当前 `next_review_target`、有效/失效范围、待判断 evidence、实际当前媒体和 open issues | `editable_targets` 全量对象、无关来源正文和历史媒体 |
| 局部修复 | 当前 finding、受影响 `clip_ids`、相关 editable targets、当前错误与可用直接 Op | 未受影响 Scene、其他目标、完整旧候选和无关 Op |
| 保存版修订 | `base_ref`、目标当前值、相关来源、兼容 Op、可选 `selected_region` 与 `region_target_candidates` | 完整 CreativeState、其他作品、无关 Clip 和不兼容 Op |
| 目标未定 | 仅 `target_candidates` 的作品身份与 base_ref，以及定位/提问工具 | 直接内容写入 |

`clip_targets` 的当前事实包括 `clip_id / object_id / track_id / scene_id / range / object_kind / layout / transform / has_motion`，文字另带当前 text 和派生关系。region 只按帧时间与布局相交产生候选；有运动时标记 `motion_at_selection=not_evaluated`，不得把静态布局当成动态精确命中。

工具结果仍按 ToolObservation 生命周期处理：完整送达一次后才可折叠；当前权威资源接管旧结果；需要时用精确引用补读。`search_tools` 不是默认仪式，只有真实长尾发现需求出现后才评审；当前主路径直接投影已知工具。

### 2.2 实现座位与删减边界

- `tools/project_context.py` 负责从权威表读取资源、生成紧凑 Composition/Clip 投影和 region 候选；不负责保存另一份状态。
- `chat/prompts.py::assemble_video_round` 负责按阶段删选资源、字段、媒体和当前动作；不得把完整项目快照默认转发。
- `chat/turn_tools.py` 负责当前目标兼容的直接 Op 与工具 schema；不得把全部 Op 或完整作品定义无差别发给模型。
- `agents/tool_loop.py` 负责每轮刷新、真实结果配对和折叠；不得把历史结果累积成第二工作面。
- ConversationContext 保存有作用域的工具事实，版本由 CompositionVersion 保存。

## 3. 剩余真实能力与发布验收

### 3.1 Skill、素材与恢复

- 复验跨 Chat 授权指认、过期版本冲突、时间改动与不支持修改的诚实拒绝。
- 验收已有录音对齐、worker 恢复、READY 不可变、失效重建与多语言词锚。
- 验证同一 SkillVersion 在刷新和移动端一致绑定，Home 与选择器同载荷，旧作品独立于后续包版本；恶意包、越权素材、无权工具和绕过授权必须失败。
- CaptureRequest 的真实 Chat 采集/首稿与数据库 fixture 仍需复验；`page_script` 不属于当前开放协议。
- SFX、Preset、局部 Scrub 继续保留试听、刷新、偏移、响度、修订和 preview/render parity 验收。

### 3.2 P6+P7——集中测试、许可、真实视听与样片

- 按实际改动运行 core、当前 JOURNEYS、Web/render 检查；真实付费调用集中在明确授权的验收窗口，不在施工中无界分散执行。
- 收口 Remotion 许可或替代实现结论，覆盖最终 Renderer 与上游 runner；部署环境隔离、超时清理、资源限制和真实成本均是发布门。
- 为宣传视频制作少量不同 arc 的强组合样片，并以 Repurposer 自我介绍视频综合验证 Chat/Skill、外部 SkillVersion、原生对象和 Generator 的创作与修订。
- 网页/Generator 代表镜头继续验证真实来源、plate/cutout 对齐、主体独立运动、文字安全区、真实指标、主要动作节拍和稳定阅读段；不得以整页缩放冒充主体运动，不得用虚构数字或低清放大冒充质量。
- 动作审片只依据实际 Output 的目标 Scene 有序帧序列；音频信号检查不冒充试听。每个候选样片仍需独立连续看片、实际试听、音画同步和终审。
- 用户明确授权后才公开上架；内部预跑、空态、静态结构或单次技术交付不冒充公开发布通过。

### 3.3 P10——直接 Op、Output 选区与 Inspector

- 在稳定 CompositionVersion、Clip/Object id、PreviewAdapter 和唯一内容写口上，贯通明确版本、时间点、目标对象与真实属性。
- 用户可以说时间、框选 Output 区域或直接选择对象。服务端将 region 的帧时间和归一化空间事实映射到当前版本候选；模型不从正文猜 Clip，也不自行把源像素换算成内部坐标。
- 局部修订与 Inspector Apply 都提交当前目标上的直接 Op 批；相关改动一次原子落版。完整实体只用于首稿、开放重稿或确实需要整体替换的对象，不是局部编辑的默认负担。
- 连续拖动、试听、seek 和调值只更新本地草稿；mousemove/commit 不调 LLM、不建版本、不触发付费渲染。Apply 才携带 base_ref 和 Op 批形成新版本。
- region 是目标指认，不是万能 `edit_region` Op。文字、原生布局、Generator 和已烘焙像素分别按真实对象能力处理；无法编辑时诚实说明。
- 旧消息钉旧版本，只有当前版本可编辑；保留取消、409 冲突、失败回滚、键盘操作和刷新恢复。多对象和更多属性按真实消费者扩展，不建设完整 NLE。

**P10 出口**：至少一个视觉属性完成本地预览、直接 Op Apply、版本血缘、冲突和刷新验收；另用一个真实 Output region 验证目标解算与零误写。音频属性和完整 Inspector 可继续按实际消费者扩展，Chat 修订不被强制迁移到独立编辑器。

## 4. 参考边界

video-shotcraft 的 Motion Workbench 只提供稳定镜头/Clip 身份、typed props、逐镜修订和 Preview/Render 一致性的参考，不复制完整 NLE 或交付后强制工作台。外部专用脚本样例只证明单次内容生产行为；本项目必须继续提供来源身份、直接 Op、不可变版本、权限、恢复和真实质检。
