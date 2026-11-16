# 按播放顺序审片的创作循环与 Skill 资源

> Status: 当前阶段装配、用户明确约束与保存事实已实施；两幕顺序审片、分镜 ACK 和同会话定向编辑已注册通过。原始 URL 最新复验已从空项目完成同版本制作、自动交付、重复确认幂等、完整解码及新旧 Output 刷新前后连续播放；实际用量、脚本修复和开放项见 §6.3.1、§7.3–7.5。最终用户主观视听与完整 P6+P7 不随技术验收关闭。P1 历史放行见 [Composition 创作循环与上下文收敛](composition-authoring-context-convergence.md)；优先级见 [PROGRESS](../PROGRESS.md#0-当前里程碑与施工序列)。

## 1. 首次创作默认出分镜，动态预览按需开启

先形成可讨论的全片分镜提案，明确讲什么、镜头顺序和每一幕的用途。模型决定叙事、画面和素材。提案可以先呈现，标明尚未编译或保存；已有可编辑版本仍由现有 Storyboard 读面呈现。

首稿默认完整校验、保存并呈现 Storyboard。模型发现某个动态效果存在影响交付的具体不确定性，且真实画面有助于确认时，才对目标幕或接缝开启有界预览。用户明确要求查看某个效果时也可提供对应预览。若必须由用户选定意图且画面不能帮助确认，走 `ask_user`。绑定 Skill 或存在 Generator Clip 本身不触发预览。正式制作沿用现有授权和版本规则。

开启审片后，按播放顺序检查选中的幕和受影响接缝，复用仍有效的证据。用户明确要求按幕审片时，可以从第 1 幕逐段推进到约定范围。发现问题时只改相关 Clip、同步轨或接缝，再局部复查。保存前的审片守卫覆盖已开启的审查范围，结构校验仍覆盖完整 Composition。

保存后，用户在同一个 `POST /chat` 提出反馈，默认基于当前版本执行针对性编辑。模型理解反馈并提交高层动作，服务端使用当前 `base_ref`、目标和现有编辑服务确定性校验、执行和保存。能唯一定位就直接编辑；存在实质歧义就发出真实问题。文字等可由版本差异直接核验的修改走结构校验；需要确认画面、运动或声音时，只预览受影响的范围。明确要求整片复查或重做时按用户要求处理。首次保存前收到的反馈仍作用于同一工作草稿，从受影响处继续。

## 2. 上下文组装与循环

| 路径 | 每轮默认注入 | 按需读取 |
| --- | --- | --- |
| 首次创作 | 简报和约束、分镜简表、草稿引用、当前相关 Clip/Track 及可执行动作 | 所选 Skill 资源、已开启审片的结论与证据、当前需确认的幕或接缝 |
| 保存后编辑 | 用户最新反馈、当前 `base_ref`、目标候选或唯一目标、相关当前值和时间窗、适用约束、当前待答问题与适用编辑工具 | 定位所需的历史事实、确需的素材引用、受影响范围的预览 |

首稿每次推进只投影一次最新状态。已开启按幕审片并进入第 3 幕时，带第 1–2 幕的已审结论和证据引用，按当前窗口加入第 2 幕尾部与第 3 幕的实际证据；旧 MP4 从模型输入尾部折叠，原始证据可以按引用回读。保存后编辑默认省略首稿 Skill/arc、整片分镜、审片游标和历史媒体。改第二幕标题时，只给第二幕标题的目标、现值、用户要求和写入所需的版本事实。

复用现有 ToolLoop 的每轮刷新与工具投影、ConversationContext、局部 Scrub、review 与同一作品写口。审查证据需要绑定草稿或版本及实际受审内容；修改后的证据只复用未受影响的部分。草稿、来源或依赖发生变化时，由代码计算最早失效位置。模型的文字描述只能记录判断，不能自行盖章说已看过画面。

逻辑上每轮验收的是累计片段。模型输入默认复用已审片段的结论和可回读证据，把真实的新画面、声音与接缝作为本轮新增输入；仅在跨幕依赖或全片判断需要时回看更早的媒体。单帧与静态摘要可以支持构图核对，运动、剪切、字幕和音画同步必须有连续播放证据。首个验证先用现有局部预览能力，完整动态预览的产品范围另行评估。

在现有 ToolLoop 刷新点由一份结构化事实驱动提示、可见工具、执行守卫与 Activity。以当前操作和草稿或版本状态选择投影，避免从历史正文猜测路径。通用行为约束在系统提示写一次，工具 schema 描述参数与返回，动态事实走轮次投影。服务端已确定的审片目标和窗口由工具直接使用；结果返回实际影响范围、精简回执和当前可执行动作。证据覆盖、模型对画面的判断和版本保存结果分别表达，覆盖齐全只能满足保存所需的证据条件。回答已有问题时，允许当前合法候选重校验，后台问题不能替换正在等待的编辑问题。已有稳定的引用、权限、版本、校验及制作约束继续适用。

### 2.1 状态来源与取值

| 现有座位 | 初版用途 |
| --- | --- |
| `Conversation.context`、消息问题记录 | 恢复本会话对应的草稿候选及审片回执，读取归属于当前操作的待答问题。草稿的 `review_started`、有效/失效区间、`next_review_target` 和 `save_ready` 已由 `working_draft_review_facts()` 投影。 |
| `Composition.current_version_id`、`CompositionVersion` | 先解析本轮指向的作品，再从作品当前版本生成 `base_ref`。版本提供目标和内容事实。一个项目里有已保存作品只代表存在可选对象。 |
| `Project.status`、`Project.pending_brief` | 保留现有项目生命周期与计划确认用途。 |
| `chat/prompts.py::ChatMode` | 保留 `plan / conversation / event / delivery` 作为现有 Chat 执行模式。 |

初版增加服务端回合内的类型字段 `video_stage`，由用户操作、目标引用、草稿和版本事实推导。会话继续保存可恢复事实，`video_stage` 每轮重算，无需数据库迁移。SSE 与非流式共用同一推导函数。

| `video_stage` | 进入条件 | 提示词增量与工具范围 |
| --- | --- | --- |
| `none` | 非本批创作/编辑操作，或已有独立的成片审查和制作流程 | 沿用当前流程。 |
| `resolve_target` | 已识别为视频创作或编辑，但本轮操作或作品目标未确定 | 只给必要的候选引用、定位读取和提问能力。确认后再开放写入。 |
| `draft_build` | 已确认新建，或继续指定草稿且需要组装内容 | 简报、分镜简表、相关素材及当前装配对象。开放适用的素材和草稿写入工具。 |
| `draft_review` | 已开启按需审片，下一步是查看选中的幕、接缝或修正后的窗口 | 已审结论和证据引用、服务端校验的窗口、当前相关 Clip；证据到达后加入该窗口的媒体，由模型记录实际观察。 |
| `draft_repair` | 当前草稿有已定位的首个问题，或存在与当前候选绑定的校验错误 | 具体问题、目标现值、相关证据和高层修正参数。修改成功后重新计算失效范围，回到 `draft_review`。 |
| `draft_finalize` | 草稿可进入完整结构校验与首次保存；如已开启审片，所需窗口的判断已完成 | 通过现有写口保存。证据判断仅约束已开启的审片范围；内容变更时重新计算证据有效性。 |
| `draft_present` | 本回合顺序审片草稿已成功保存 | 使用保存结果呈现分镜，仅开放 `answer`。用户下一条反馈才进入保存版编辑。 |
| `version_edit` | 已确认反馈指向某个已保存作品的当前版本 | 最新反馈、`base_ref`、相关目标与现值、适用的高层编辑工具。歧义时限于定位和提问；只有确需视觉验证才加入局部预览。 |

有归属明确的待答问题时，沿用原操作和目标，将问题作为独立条件块。草稿和保存版同时存在时，以本轮明确的目标或续接的问题决定路线。首次保存的结果结束当轮草稿流程。下一条用户反馈再解析目标；指定已保存作品时走 `version_edit`。明确要求重做时可以开启草稿流程。初版按现有独立路径处理显式成片审查和制作。

明确引用新文案的单点标题替换，且本轮无待答问题或素材准备时，使用现有 `revise_video` 的精简参数。装配只给用户本轮要求、目标版本和当前原生文字候选，候选唯一才开放写入；候选有歧义时走真实 `ask_user`。工具绑定当前 `base_ref`、目标 Clip 和原文，服务端复用现有文字更新和版本写口。旧消息仍可回读，其他编辑继续使用原有装配。

提交审片判断的轮次带当前窗口的连续 MP4、同一 MP4 中目标幕末段的一张代表帧和用户要求，省略网页来源原文。代表帧用于核对可见细节，运动和接缝以连续证据为准。新证据要求在 `observed` 记录画面事实，再提交 `pass`、`issue` 或 `uncertain`。无法确认时服务端只允许同窗换一处取样复查一次；两次均无法确认则保留未保存草稿。后续取景修复仍提供相关冻结来源和元素选项。

### 2.2 通用提示词装配

在 `chat/prompts.py` 增加共享的 `assemble_video_round(facts)`，由现有 ToolLoop 每轮刷新调用，`plan_turn.py` 和 `propose_turn.py` 提供同形事实。返回本轮的阶段、系统提示文本、动态消息片段、媒体引用与工具列表。使用现有 Jinja 渲染，按下列顺序组装。

1. `resolve_video_stage(facts)` 先确认本轮操作及目标。编辑已保存作品进入 `version_edit`；草稿按校验错误、装配、已开启的待审窗口和保存事实选择阶段。已有 Scene 只说明可以确定检查对象。确认不了意图时沿用同一回合的定位/询问工具，从结果和当前事实推进阶段。
2. 按阶段选择工具，再应用权限、目标、待答问题、素材就绪和候选修复等限制。将最终工具列表与阶段交给渲染器，保证提示里要求的动作确实可调用。
3. 条件拼接系统提示为「共用 Chat 规则 + 当前阶段的行为片段 + 适用的待答/纠错规则」。动态消息再拼接「用户要求 + 当前阶段投影 + 最新相关结果」，媒体独立挂在对应证据消息上。项目事实、候选诊断与草稿状态按身份投影一次；从历史回读时只取相关片段。
4. 从执行结果更新草稿、回执或当前版本，再回到第 1 步。执行守卫仍用当前权威事实重新校验；Activity 由真实执行事件生成。测试从最终 provider 请求验证片段、媒体和工具同时切换。

首稿验收时增加草稿与保存版共存的覆盖。明确改保存版第二幕标题时，预期为 `version_edit`，请求里只含该目标的编辑片段；同一会话继续尚未保存的草稿时，则依据该草稿的回执进入对应的草稿阶段。已完成的审片判断或全片检查回执需要跨回合恢复时，沿用草稿现有回执座位。

### 2.3 本批移除冲突装配

接入统一装配时同步替换以下旧分支。每条行为规则由一个阶段片段或共用规则提供；执行限制由服务端事实和守卫落实。

| 当前冲突来源 | 本批处理 |
| --- | --- |
| `_video_project.j2`、`review_working_draft` 工具说明和 `video_round_context_projection()` 都写了审片顺序与复查要求 | 将顺序、修复和保存行为交给对应阶段片段；工具说明保留调用契约，动态投影只提供草稿、窗口和证据事实。 |
| 草稿按 `drafts[-1]` 投影，工具又按草稿存在与否、快照中的版本键和 Promo 文本判断 | 先解析本轮操作和具体目标，按目标投影。去掉从快照正文识别协议的分支；确需区分旧工具参数时使用目标版本的结构化 provenance，独立于阶段判断。 |
| 工具先投影，候选修复随后限制工具，动态上下文仍可能列出限制前的 `available_actions` | 阶段、最终工具列表和行为指令一起装配；只开放修复工具的调用中，提示只要求处理当前候选错误。 |
| 通用、direct 模板和草稿状态都可以注入 pending 规则或问题 | 共用一处行为规则，本轮只投影归属明确且仍开放的问题。回答并保存成功后，下一次模型请求去掉旧问题及提醒。 |

用同一份输入事实核对两条 Chat runner 的最终 provider 请求。至少覆盖首稿审片、草稿与保存版共存时的保存版编辑、只能纠错的回合、目标歧义与回答保存、成功后下一轮无旧提醒。断言系统提示、动态上下文和最终工具集合同时成立，并验证目标版本和实际写入结果。此项与首稿及保存后编辑一同验收。

### 2.4 工具调用前的用户说明

`video_stage` 表示后端当前工作阶段。界面继续复用已有 Activity，不新增独立进度 UI。工具步骤、用户开场计划和从证据得到的新发现分别有各自的来源。

`assemble_video_round()` 按阶段装配执行指令、工具和发言条件。ToolLoop 的 `on_interim_prose` 结合当前草稿、本轮实际证据、开场轮次和已有 interim 计数路由文字；历史回执、被拒绝的调用或重复读取不能单独触发新说明。

1. 两条 runner 继续共用 `chat/prompts.py::assemble_video_round()`，用局部条件值选择规则，无需持久化字段、第二套状态机、额外模型调用或新工具。
2. `_read_tools.j2` 与 `_video_project.j2` 的共用阶段规则只保留当前行为；终态回复及其他流程保持原有行为，不恢复 Promo 专用模板。

| 本轮条件 | 模型发言与工具调用 |
| --- | --- |
| 首稿多步任务开场，当前用户回合还没发过中途说明 | 可以在首个实际工作的非终态调用前说一句计划。只说准备做什么。 |
| 本轮收到当前草稿的新预览，或有与本轮操作相关的新结果 | 只有发现用户关心的变化才说一句发现。可以和记录 `evidence_id` 判断的调用同轮发出。只描述看到了什么，不重述计划、不预告修完；一般通过、常规读取或机械复查可静默。 |
| 后续例行调用、内部纠错，或保存后直接修改已定位的目标 | 静默调用。执行中由既有 Activity 显示真实动作。实质歧义仍走 `ask_user`。 |
| 已有实际保存结果或具体阻塞 | 沿用现有终态回复，以保存结果、版本差异或阻塞为依据。 |

现有 `interim_prose` 继续处理非终态调用旁的用户说明。审片问题由已接受的 `judgment.summary` 经现有通道显示一次；同次判断的自由正文不再显示。ToolLoop 按装配的静默条件关闭本轮中途正文输出，Activity 照常显示实际操作，终态回复走现有 settled envelope。判定依据是结构化轮次状态和已接受的工具结果。

在 §6.5 的同一注册旅程中抓最终 provider 请求和 SSE 顺序。首稿开场计划至多一次；第二幕发现须晚于对应预览；修复过程不重复计划；保存后的单点标题修改直接执行，终态依据实际版本差异。检查语义和事件顺序，不锁具体措辞。

## 3. Skill 包与可执行资源

### 3.1 Clip、资源和 Generator 的职责

Clip 是时间线上的共同编辑单位，持有轨道位置和输出时间范围。Clip 内的 Object 类型决定画面或声音如何取得、哪些属性可独立编辑。放置、移动、裁剪、叠放、对齐和转场共用时间线编辑能力。

- **现有素材**：图片、视频、网页截图、声音经素材工具获取或准备，形成项目可回读的冻结资源身份。编辑时引用该身份并落到目标轨道和时间段。
- **生成素材**：按现有能力和授权准备。待生成请求要明确标为待准备；实际生成后才能把固定媒体作为已就绪资源投影给模型，后续编辑可复用。
- **程序化生成**：Generator Clip 保存可重跑的程序、参数、依赖及固定素材身份。其实际预览和固定媒体经现有 runner 产生。重要标题、字幕及声音按可编辑需求保留为独立原生对象。

### 3.2 包资源与装配器

Skill 可以保存方法，也可以携带一个或多个可复用的作品资源。按使用方式声明资源：

- **方法**指导取证、分镜、实现与检查。只含 `SKILL.md` 的兼容包仍可导入并作为方法使用。
- **参考**包括 arc、镜头卡、演示和参考成片。模型可以读，当前没有对应实现的参考要明确显示为参考。
- **可实例化资源**可以是参数化整片模板，也可以是带画面、文字或声音的多轨片段。复用现有 VideoTemplate、Preset、原生对象与受控 Generator 的能力。调用时解析槽位、来源权限和所需能力，将内容展开到当前 Composition 的草稿。已保存版本固定自己的内容与资源身份。

装配器提供跨 Skill 的宿主能力。它按版本读取模型选中的资源，解析实际依赖、输入槽与可用能力，绑定用户素材和当前时间窗，再把参数化模板展开成原生 Clip 或把受控程序放进 Generator Clip。结果返回实际改动的轨道、Clip、可编辑参数和可预览范围。复用包可以只提供方法；有不同工程结构的包也使用同一装配入口。

同一能力定义负责判断资源可执行性、生成模型看到的选项和校验工具调用。资源从参考变成可执行，需要解析源码、资源和依赖闭包并通过宿主校验。内置 Promo 的现有 arc 和镜头可作为可用素材或回归样本。首稿专用封闭枚举是否退役，要等通用路径证明能够表达并实现相同创作。外部脚本和原始程序仍按现有不可信参考与受控执行约束处理；读取 Skill 不自动获得运行权限。

后续用户保存 Skill 时，可以从选中的编辑版本截取片段或选整片，声明可替换的文案、品牌和素材槽位，生成新的版本化资源。先验证一个资源能在不同位置可靠实例化与独立编辑，再规划导入、另存与跨项目体验。

## 4. 第一轮验证

1. **验证循环。** 用已有冻结的 OxValue 网页做两幕，第一幕让观众看清 Frame / Enrich，第二幕接到 Value / Defend。展示提案后，先审第 1 幕，再审 1→2。故意让第二幕使用与第一幕相同的焦点，确认问题在接上第二幕时被实际证据发现。只修第二幕，再重审受影响范围。验收实际焦点、关键帧和连续画面，检查第一幕未受影响部分及其他轨道的内容。
2. **验证 Skill 资源。** 两幕重复使用同一个可执行资源，并绑定各自的素材或目标；验证只改其中一幕。用一个只作为参考的镜头卡验证它不会混进可执行选项。先复用已有资源，若素材本身缺少能区分两段的可定位区域，记录为采集或资源缺口。
3. **验证成本和产品结果。** 记录每轮默认注入范围、增量媒体、provider 调用数和累计 tokens、首次看到提案的时间、到可编辑版本的时间。另用采购者简报检查用户要求能改变镜头内容和取证。提案能展示、局部画面符合意图、最终版本保存分别验收。

旧合同中的官网首稿、overlay 问题归属、跨 SSE／非流式第三轮续接和真实视听仍开放。完成上述验证后，更新 [视频作品母文档](../VIDEO_PROJECT.md) §7、§8.1.2，并逐条迁移仍有效的 Skill 与创作验收。被替代的施工条款就地删除；已有测试与可复现证据保留。

## 5. 已验证的边界

- **镜头复用与局部编辑通过。** 项目 `312e5266-096e-4d96-9e84-cf1b740d4e7f` 的两幕复用同一官网快照、同一网页视图和同一 `evidence-push` 资源。版本 `946f96f9-ef35-4c0c-87b2-d6115738ad77` 的两幕误用同一焦点，实际预览帧都显示 Frame / Enrich。经现有完整 Clip 修订服务只改第二幕，版本 `a647c614-a3be-4797-bd25-b9bbae88e74e` 的实际预览转向 Value / Defend。版本差异仅一个网页 Clip 的动画，第一幕、文案轨、来源、设置和时间线未变。零 Run、零 Output。
- **视觉验收仍有缺口。** 实际画面里的 Defend 正文右侧截断，浅背景上的白色标题对比不足。现有 `element_id` 能选单个已定位元素；本例两卡组合还需要调整取景。已核对各幕实际预览帧，未验收连续播放、转场或声音。
- **循环仍待验证。** 本轮由脚本先后读取已保存版本的两个独立 Scrub，再调用通用修订服务。现有公开 Scrub 只接受一个已保存 Scene/Clip 或独立 Object，无法在同一工作草稿中检查跨幕连续片段。还未验证普通 Chat 自动推进、上下文投影、从首个问题恢复或累计 provider 用量。
- **外部 Skill 解析与执行分开验证。** 完整本地 Shotcraft 包通过现有解析器，得到 1,015 项参考和 54 项预览媒体。原模板依赖 JSON 布局与 Remotion `Audio`。现有 Generator 支持声明的本地 JSON 数据模块和固定图片；完整模板和包脚本的执行兼容性仍待验证。
- **一个原始上游镜头已在现有隔离中运行。** Shotcraft 的 `DollyZoomReal` 及其布局 JSON 原文件按 digest 固定，验证脚本只添加标准 Remotion 注册入口，声明 10 张上游图片。API、工具说明和 renderer 允许本地 JSON 数据，renderer 的固定资源数量与 API 的 64 项上限对齐，单项及合计字节预算保留。项目 `157f7fc3-69f9-42c6-8e9c-60248bca49f4` 的版本 `14c6a7a7-748e-4d7a-88a3-dad9339795ad` 保存 Generator Clip 和独立原生标题；隔离预览返回 135 帧。版本 `f48349ce-d4f9-4b5c-8d3d-e54360f99f44` 只更新标题文字，Generator 的精确对象 Scrub 仍可读，零 Run、零 Output。该验证由脚本选取和声明上游资源，普通 Chat 的自动装载与按幕审片尚未验证。

## 6. P2 代码修改方针

### 6.1 关键环节、工具和 Chat 状态

首次创作在同一个 Chat 回合逐步推进同一工作草稿。检查、修正与复查只在确有动态确认需求时发生。状态行由实际事件推进。

| 环节 | 工具或系统动作 | Chat 状态行示例 | 推进条件 |
| --- | --- | --- | --- |
| 分镜提案 | 根据简报和证据提出镜头顺序、各幕意图和素材计划 | 正在整理分镜 | 提案可展示，标记尚未落版 |
| 素材准备 | 回读已有资源，按需调用 `prepare_video_materials`、`capture_web` 或已有生成能力 | 正在准备第 1 幕的网页素材 | 得到真实资源引用，或明确记录缺口 |
| 装配当前幕 | 将选中的 Skill 资源、原生对象或固定素材绑定到目标 Clip、轨道和时间窗 | 正在组装第 1 幕「证据从哪里来」 | 本次编辑通过局部校验 |
| 检查第一幕 | 用真实草稿内容编译并读取第一幕预览证据 | 正在检查第 1 幕画面 | 本幕实际证据已查看并记录判断 |
| 检查新增幕和接缝 | 按播放顺序检查当前幕、上一幕尾部和跨界音画，按需回读更早证据 | 正在检查第 2 幕与上一幕的衔接（2/5） | 当前累计范围成立，或发现首个具体问题 |
| 修正与复查 | 修改目标 Clip 或同步轨，计算最早受影响位置并复查 | 正在修正第 2 幕取景；正在复查第 1–2 幕 | 新证据覆盖受影响范围，判断问题是否解决 |
| 保存 | 完整结构校验并经现有写口保存；已开启审片时检查对应证据 | 正在保存可编辑版本 | 取得成功保存的版本 |

素材未就绪、用户需要回答、预览失败、取消和达到预算时，用对应的实际终态收口。暂停时保留有效草稿及可复用素材。预览与审查本身不触发正式制作或交付。

### 6.2 关键代码模块

下表的 API 路径相对于 `apps/api/app/`，Web 路径相对于 `apps/web/src/`。

| 模块 | 修改方针 |
| --- | --- |
| `editing/schemas.py`、`editing/edits.py`、`editing/templates.py`、`editing/store.py` | 保持 Clip、Track、时间窗和唯一版本写口。装配与编辑共用已有实体、时间编辑和校验；按资源类型补来源绑定与可编辑属性。片段展开后由当前草稿持有。 |
| `tools/video/design.py`、`tools/video/preparation.py`、`tools/project_context.py` | 素材准备返回 owner 校验后的稳定资源引用及就绪事实。统一投影当前素材、草稿或版本、可编辑目标、当前幕、接缝和 pending；已准备媒体可按引用回读。项目事实只注入一次，截图、转述依据与逐字屏上引用分别表达。 |
| `skills/package_reader.py`、`skills/package_session.py`、`chat/video_turn_seats.py` | 复用版本化包读取、预算和文本回执。接入通用资源装配，解析选中资源的入口、源码、布局、素材和锁定依赖，绑定到当前草稿。工具选项和执行校验共用解析结果。用普通 Chat 自动选中并装配一个真实上游镜头验收，首个镜头无需逐卡实现。 |
| `tools/video/preview.py`、`tools/video/review.py`、`agents/working_drafts.py` | 复用局部切片与预览编译，增加对精确草稿及有界跨幕时间窗的检查能力。证据钉草稿或版本、时间窗和受影响内容；编辑只使依赖该内容的审查结果失效。整片连续观看与局部检查按实际证据分别标记。 |
| `chat/conversation_context.py`、`agents/tool_loop.py`、`chat/turn_tools.py`、`chat/prompts.py` | 每轮从同一结构化状态计算可见工具、提示词、当前审查范围和候选。已确认范围默认投影摘要与回读引用；当前幕、接缝和变更影响的媒体按需加入。去掉从 `snapshot.text` 查找 Skill 名来切协议的做法。局部修正共用回合预算，复查不重置计数。 |
| `chat/plan_turn.py`、`chat/propose_turn.py`、`chat/trigger_turn.py` | 对当前版本、用户目标、待答问题和合法操作使用同一判断。已有问题仍归原编辑任务，后台触发可以提供信息；对应修改成功后才结算。复查与保存经过真实执行守卫。 |
| `chat/activity.py`、`chat/routes.py`、Web `lib/chatStreamFrames.ts`、`components/chat/ActivityStream.tsx` | 复用现有 Activity 和 SSE 状态行。由服务端真实开始、成功、失败和取消事件提供当前幕及范围，界面按事件显示。工作草稿与证据的事实继续走服务端上下文，Activity 负责呈现。 |
| `tools/video/components.py`、`tools/video/programs.py`、`apps/render/src/component-runtime/` | 复用现有隔离 runner、固定资源和 digest 缓存。仅按真实上游样本补宿主能力缺口。固定媒体回到既有时间线和预览；制作授权及最终 `video-spec` 合同保留。 |
| `editing/promo.py`、`skills/video_shotcraft.py`、`chat/turn_tools.py`、`tools/video/design.py` | 将固定 Shotcraft 适配与仍被生产调用的 Promo 分支分开核对。无生产消费者的固定适配先核对现有回归后退出生产包；现有三个原生镜头可作为资源复用。通用路径承接原有首稿和修订行为后，撤掉按包名切换工具 schema 的专用分派。 |

### 6.3 施工顺序与退出条件

1. **先收口同一 Chat 入口的首稿和保存后编辑。** 用 OxValue 两幕验证 `1 → 1–2 → 修第二幕 → 复查 → 保存`，再在同一会话改第二幕标题，验证走当前版本的局部写入、无从头审片、第一幕及其他轨道保持稳定。检查首稿模型请求只带当前所需媒体与已审摘要，后续反馈请求只带当前编辑上下文和适用工具。用 provider usage 分别记录两次用户回合的各调用输入、峰值和累计 tokens，核对模型请求中实际附带的媒体，并验证提示、工具、守卫和 UI 使用同一事实。
2. **再让通用装配进入同一个循环。** 首稿默认保存分镜和按需预览的分派已有真实验收，见 §7.4。从同一 Chat 入口分别绑定 Shotcraft 和 Talkcraft，验证不同上游资源能直接保存分镜并按需局部隔离预览。检查独立原生文字修订、参考资源未被当作可执行选项，以及下一回合能复用已准备的资源。用户作品另存 Skill 在该资源模型验证后再接入口。
3. **最后撤掉已被覆盖的 Promo 专用路径。** 用同一官网的两份不同简报验证创作仍有差异，再复验原首稿、五类局部修订、overlay 原问题结算、第三轮跨 SSE／非流式 Skill 续接。只通过脚本、结构校验或静帧的项目分别记录，P1 的开放项按各自证据关闭。

### 6.3.1 动态 Skill 切换与删除

先分别用 Shotcraft 和 Talkcraft 两个独立外置包验证通用装配，再用现有 Promo 旅程验证通用路径覆盖原有能力。通用接管与旧路由删除在同一切换提交完成。切换后，包名、历史 provenance、资源缺失和装配失败均不得恢复旧协议。缺少可执行资源时返回具体缺口，保留可恢复草稿及用户意图。

单镜头接线先做两项可独立验证的宿主能力。Skill 方法只随需要它的创作阶段投影，项目快照保留结构化资源。按需草稿预览只为目标切片准备已有本地 Generator，沿用隔离门与媒体预算。首稿明确时直接保存分镜；局部预览单独验收。包在 `template/generators/` 显式声明入口、源文件、固定图像和输出规格。统一 Chat 工具从当前绑定的不可变包版本发现并选用声明，经宿主校验和依赖锁定装配为轨道上的 Generator Clip。只有用户要求或确有动态疑问才走局部预览，预览使用现有隔离 runner。普通源码阅读仍只提供参考。两份样本分别覆盖 Shotcraft 的多文件和固定图像，以及 Talkcraft 的数据动画卡；分别绑定并验证通用写入、保存和按需预览。

声明文件以 `<resource_id>.json` 命名，字段为 `entry`、`composition_id`、`files`、可选 `resources`（程序内资源路径到 `gallery/media/` 路径的映射）及 `output`。模型用 `list_skill_shots` 发现资源，再用 `design_video.skill_resource` 指定资源、Scene、视觉 Track 和 Clip。首批采用声明的完整时长，布局可选。包代码、依赖与 SourceSnapshot 由宿主固定。版本 provenance 保留绑定包、资源 ID 与声明 digest。每个作品至多绑定一个 Skill 版本。双包验收使用独立作品，走同一 Chat 入口。

两条外置包旅程在当前共用链上独立通过。`dynamic_skill_shotcraft` 项目 `cc72885e-cee2-442b-8471-cfccaa1930aa` 保存版本 `dcafff80-9e36-4ded-90f7-e8f96a12a88e`；`dynamic_skill_talkcraft` 项目 `9e4589d8-063a-46a9-bc9f-6c5076f6c285` 保存版本 `a4f3a9af-46ea-43f1-86e2-1c7acd2033df`。两者均由真实 Chat 完成绑定、保存、分镜 ACK 和按需局部 Scrub，未创建 Run 或视频 Output。

**Promo 已完成切换。** 内置 Promo 与带旧 provenance 的保存版共用高层 Scene 创作和 `ReviseVideoActionArgs` 定向修订；服务端绑定当前 `base_ref`、真实用户答案、来源和时间窗。包名、历史 provenance、资源缺失及装配失败都不会恢复旧 prompt、schema 或执行分派。最终 provider 请求只声明当前阶段允许的工具，保存版不接收 raw Track/Clip/Op，也不要求模型手抄 `base_ref`。

| 真实注册 | 当前证据 | provider 输入 tokens（每次调用；峰值；累计） |
| --- | --- | --- |
| `promo_p1_first_draft` | 项目 `a5f435ab-7b38-49bd-a55d-56a7911387ea`；版本 `32a22466-e528-4f9a-9624-150116f0cd87`；分镜 `2c864e32-84ea-4daa-a203-045e2bcf1628`；Snapshot `0d3bcf62-2251-5fed-8235-51e74a987903`。Clip 输出 `0..360000`，来源 `0..360000`，各自 timebase 下均为 4 秒，零 Run/Output | 30,524 / 31,446 / 38,041 / 36,824 / 21,464 / 21,900 / 21,174 / 7,981；38,041；209,354。另有 1 次辅助调用缺 usage |
| `promo_p1_continuation` | 项目 `47e4c90f-4dd5-4746-a053-fcad622d2ff8`；草稿 `cnd_387847ef366b4ccba2bb65c9fd4529cf`；版本 `1b718647-3a7f-4aae-b639-35c140b41f6c`；分镜 `ad29ff4b-8b29-41e8-8a13-9ae5f681f874`。三轮 Turn `2f34b984-e753-40ba-8044-ad3fd4e7ab94` / `f3c8b2b0-5976-47d3-a24b-1363b4c695b6` / `25e8349a-640c-46a1-bcb4-77176fc5bc61`，同一 draft/digest/receipt，零重读、零历史媒体、零 Run/Output | 首轮 32,103 / 33,741 / 38,502 / 40,823 / 43,158 / 22,794 / 23,851（43,158；234,972）；澄清 21,806；保存 23,855 / 9,416（23,855；33,271） |
| `promo_p1_revision` | 项目 `0e2d9d44-2b0a-48a1-96a9-238daf1df341` 连续保存 V2–V4；标题歧义形成真实问题 `70a186d5-91fa-419b-ac7b-530fa436bfa6`，零 Run/Output | 时长 102,857（3 次，峰值 34,862）；文字 69,153（2 次，峰值 34,639）；Preset 107,922（3 次，峰值 36,907）；歧义 109,547（3 次，峰值 37,748） |
| `promo_p1_overlay` | 项目 `6d4cf817-4f28-4198-8e8f-c95476394e0d`；原问题 `febc90bc-f7e4-43e5-8185-671552b8aadb`；Snapshot `3f6efc6d-ea4d-573b-abfd-6d6868372d79`；overlay `clp_overlay_1ecf6946f768`；V2 `2a0ee16f-4222-414b-9586-42c9770bf780`；删除版 `1d6e0fb7-c0b6-460e-86c1-bba25c99aa6d`。原问题在保存后以原话 freeform 结算，删除只移除目标 Clip，旧提醒未复活 | 询问 33,598 / 35,982 / 34,840（35,982；104,420）；回答保存 35,451 / 35,253（35,451；70,704）；删除 35,706 / 35,450（35,706；71,156）。回答轮另有 1 次辅助调用缺 usage |

装配失败和旧活跃草稿恢复均有确定性回归：资源装配失败零版本写入并返回原工作草稿；只有一条成功且活跃的旧 Promo 草稿 `cnd_33fb215078b34c21b014d3ca4d3f26a8`，其完整展开内容可经 save-only 协议恢复，无不可恢复案例。未知 Snapshot 与错误 owner、越界/反向窗口、stale base、错误目标均失败闭。切换后完整 core **390 passed / 1 个既有 SFX 文案断言失败**，定向共用链 **104 passed**，`git diff --check` 通过。

实际删除：`editing/promo.py`、`_direct_promo_turn.j2`、`_promo_composition_authoring.j2`、`skills/video_shotcraft.py`、`skills/promo-video/template/first-draft.json`，以及 Promo 参数模型、专用展开器、包名/provenance 判路、工具白名单、首包索引自动注入和 `hasattr(args, "shots")` 特判。包内 arc、卡片、demos、素材、方法与版本化绑定保留。历史 CompositionVersion、SourceSnapshot 和 provenance 不改写，旧保存版继续使用同一读取、修订、预览和制作入口。

`promo_short_confirmation_delivery` 的切换后付费复验与浏览器连续播放已通过技术验收，证据见下文。最终用户视听仍按 P6+P7 验收。

**首要用户验收。** 从空项目用产品内的 Skill 选择入口发一条自然请求，例如 `/promo-video 帮我给这个网站制作一个宣传片：https://agent.oxvalue.ai/`。首轮用用户提供的真实来源保存并呈现可编辑分镜，等待呈现回执，零 Run。后续用户消息只允许 `OK` 或 `Yes`。系统给出明确的确认对象，确认与当前分镜或制作报价绑定。若现有设置还需报价确认，第二次仍用同样的简短肯定。验证只产生一个 Run、一个可播放的 Output，两者绑定用户确认时的同一 CompositionVersion，版本数保持不变，交付回到原 Chat。另验收确认指向不明、版本过期和重复确认的边界。真实旅程使用实际通用工具和制作链。截图分镜、直接调用生产函数及带有额外制作指令的确认消息均不足以通过这项验收。旧入口删除仍受本节其余回归门槛约束。

**主链接线计划。**

1. **首稿。** 在内置 Promo 切换改动中，`skills/resolution.py::resolve_named_skill()` 和现有 Skill 选择入口仍绑定同一包版本。`chat/video_turn_seats.py::prepare_bound_skill_context()` 提供方法，`chat/prompts.py::assemble_video_round()` 与 `chat/turn_tools.py::video_round_tools()` 使用通用草稿工具。模型用 `prepare_video_materials` 获取真实 URL 的冻结来源，再经同一个 `design_video` 和工作草稿每次写一幕。模型决定叙事、幕数与顺序、素材及取景、屏上文案和动效意图；首稿可见 Schema 不提供 raw Track/Clip、布局、关键帧、来源 digest 或输出时间写法。保存版修订继续按当前 `base_ref` 定向执行。

   **模型高层输入。** 初始 `scene_plan[]` 只含 `scene_id / intent / visual_description`，以数组顺序决定幕数和顺序；`source_ids[]` 选择已冻结来源，`music_snapshot_id` 选择已准备音乐。随后每次一个 `scene`：`scene_id`；可选同级 `snapshot_id / view_id / element_id` 决定网页或图片素材及取景；`headline / supporting_text / items[]` 决定原生屏上文案；`text_preset` 只复用现有 `title-lockup / list-reveal`；`source_motion` 只表达 `hold / push`。`scene_count / target_seconds / aspect / background` 仍只接受用户明确固定的约束，普通简报不由模型自设。

   **服务端派生。** 服务端按当前幕读取工作草稿，校验来源 owner 和冻结 view/element，补齐 SourceBinding digest；按文案阅读时长和既有 30fps 时间格计算连续 Scene range，并仅为用户明确的 `target_seconds` 延长末幕阅读保持。服务端创建或复用 `trk_main / trk_music` 及现有 Preset 展开出的 Track，派生 Clip/Object/Animation 身份、全画布或文本布局、网页取景关键帧和全局音乐床。原生文字、网页/图片和音乐仍是可编辑 Composition 内容；不新增 Promo 专用镜头枚举、固定叙事模板、第二写口或通用 IR。

   **局部与最终校验返回。** 参数错误返回高层路径（如 `scene_plan[i].scene_id`、`scene.view_id`、`scene.text_preset`），未知/未冻结来源、当前幕不符、取景或 Preset 不兼容、时长不足均保留原草稿并给出具体错误，不把 raw 实体错误推给模型。每次单幕派生后做现有局部结构与来源校验；`save=true` 只接受既有 `draft_ref`，再经完整 Composition 校验和唯一写口保存，零部分内容版本。最终完整校验和 20 次上限不变。
2. **分镜确认。** 创作轮保存成功且用户原始请求含制作意图时，在分镜结尾给一个明确的“按这版制作吗”。在 `video_turn_seats.py::stamp_video_presentation()` 及既有 `PendingPlan.video_presentation` 中记录确认邀请，绑定分镜消息与完整版本引用。`routes.py::complete_video_presentation()` 继续核验真实呈现。仅看分镜的请求、ACK 本身以及无待确认对象的简短肯定均不触发制作。
3. **简短肯定。** 在 `chat/service.py::prepare_chat_turn()` 与两个 runner 共用的轮次装配处，先确认当前对话中唯一有效的待确认对象。已有制作报价时沿用报价确认和 `start_run`；否则对已 ACK、已邀请制作且仍是当前版本的分镜，将独立的 `OK` 或 `Yes` 映射为当前版本的制作意图。复用 `present_plan` / `propose_tasks`、`resolve_confirmation_need()` 和现有报价策略。用户无需复述片名或版本 ID。
4. **版本和重复请求。** `tools/video/production/__init__.py::pin_video_production()` 复核真实授权消息、同一 Chat、已完成呈现、目标版本及 digest。在现有锁和授权事实下验证简短肯定对应的版本仍是当前版本，且同一次确认未启动过 Run。过期或有歧义时重新呈现或提问，重复请求返回已有状态。沿用 worker、计费和交付链。
5. **放行。** 在 `test/journeys/chat.py` 登记真实 URL 首稿到交付的旅程，复用分镜 ACK、Run/Output 与交付检查。先验证默认设置下 `OK`，再验证需额外确认的设置下 `Yes`，并覆盖 SSE 和非流式。核心测试覆盖无邀请、未 ACK、过期版本和重复确认。通过用户主链后，继续现有 Promo 修订和续接回归，按同一切换条件删除旧入口。

**短确认实现与当前验收。** `prepare_chat_turn()` 把简短肯定解析为真实分镜或报价事实，存进当前用户消息。分镜呈现回执记录制作邀请。两个 runner 读取同一确认事实，服务端填充唯一制作任务，复用报价和 Start。锁内校验版本、呈现消息及重复提交。交付触发器恢复返回确定性审核事实和实际 Output 引用。

- **旧 502 来源已查明。** 项目 `568fa1ef-6592-445c-abf9-6e2d818348bc` 与 `a017396e-ec2c-47b6-a8e6-287f2c6af8eb` 的持久化 trace 均为 MiniMax HTTP 429 `rate_limit_error`（Token Plan 用量上限 2056），经 `chat/routes.py` 的 LLMError 边界映射为 502；不是素材、worker 或 renderer 故障。两个项目均零版本、零 Run。
- **修复前业务对照。** 项目 `fd01ced0-5460-45fc-b30d-bab9dab72966` 在真实首稿的 `save=true` 遇到 `verbatim_copy_mismatch`，下一轮改写已填首幕又被 `scene_order` 拒绝，最终零版本、零 Run。校验器已有 expected/actual，但草稿诊断将其丢弃。现按每次高层单幕写入提前校验逐字文案：中间幕校验当前前缀，最后一幕校验完整序列；失败恢复当前未填幕，诊断保留 expected/actual，最终完整校验不变。相关创作、保存、预览与交付定向 **126 passed**。
- **历史真实注册交付 PASS，P1 已关闭（只作对照）。** 从空项目 `11b96089-3e1b-41fd-b843-e601c3dff6bc`、Chat `1082cff8-1b83-47a6-98d8-0ac98803ab9b` 和原始 URL 话术启动。首稿 Turn `85b3ecce-79bf-4026-b8fb-e2fb3e67d273` 实际使用 `scene_plan` 和逐幕 `scene`，保存 Composition `cdd484f7-fe91-487d-a353-ccf09fb6a4b8` 的唯一版本 `84b08377-b967-463a-9e82-5ae842f64223`（digest `8f6a081d0c8a81bc068b3e4afcc4d32710c5f3b1e7e84a3e8e572f731ffd7a9b`），分镜消息 `f60d10fc-1e74-44c5-b1cb-e995c4c59a76` ACK 成功且确认前零 Run。OK 用户消息 `ec0949dd-b6e9-40d8-8e3f-bce4efbcb0b3`、制作回复 `c3624020-8a67-4834-8898-0faa00381a4b`；当前 auto 设置无需另一次报价 Yes。Run `c93d618e-8ca1-4e21-9c0d-f838c80149f7` completed，视频 Output `ace76862-df70-4a11-8742-33febe00cf03` completed，二者与分镜钉住同一 version/digest；交付消息 `392035d0-851a-49ed-8133-bc6475415b3b` 自动回到原 Chat 且只引用该 Output。重复 Yes 用户消息 `d81b1290-660c-4c65-a2d7-f3e69a2a2782`、回复 `95a28601-0ad1-4b80-81aa-87fa0c008e44` 后仍为 1 Run、1 视频 Output、1 版本、1 交付消息。
- **完整解码（本轮只读复验）。** 历史 Output MP4 为 19,655,378 字节，SHA-256 `292d061ac1a0823e96a2e5b3e38aaa4d5e97d9937fffa67ed770c1e630cde982`；1920×1080、30fps、视频流 42.2 秒，完整解码 **1266/1266** 帧。容器时长 42.261333 秒；1981 个音频帧、4,057,088 个样本的 RMS/peak 均为 0，实际为无声成片。该历史保存版、Run 与 render spec 都没有音乐轨；旧分镜/OK 的 Tech House 表述来自未落轨计划，不是保存事实。
- **历史真实 provider 用量。** 首稿 16 次 Chat 调用依次 **30,446 / 35,078 / 37,673 / 59,180 / 66,682 / 54,666 / 58,253 / 62,528 / 65,298 / 68,200 / 71,145 / 74,237 / 74,661 / 58,254 / 61,312 / 75,430**，峰值 **75,430**、Chat 累计 **953,043**；2 次辅助准备调用分别缺 usage、1,716，已知合计 **954,759**。OK 为 **16,051 / 16,275**（峰值/累计 **16,275 / 32,326**）；重复 Yes 为 **15,058**；自动交付另有 **17,508 / 17,905**（累计 **35,413**）。报价 Yes 未发生。结构统计中首稿当前媒体共 5 parts、历史媒体 0；OK 与重复 Yes 均为 0。
- **旧 Turn 已诚实收口，provider 已恢复。** 项目 `0c0a50f2-b5a6-40b8-b6a5-2a501d9fd9d7` / Turn `faebb418-0e83-40e3-9468-c9a6f67f13ab` 没有活跃 API/worker 执行者，已通过现有 `stamp_turn_failed` 入口落为 `failed`，保留原用户消息和 6 条 ConversationContext 事实；没有 assistant 终态，零 Composition、零版本、零 Run、零视频 Output，只有素材理解 Output `0954b0bd-45c6-4e64-9d06-61f23847af22`。原故障依次为 ReadTimeout（`50a39e2c-e0ad-4279-abd8-b12d9e2c43bb`）、RemoteProtocolError（`31bfdf18-052d-49a6-a9c3-361584bdb3b2`）、ReadTimeout（`fd066e0b-98d6-4262-ad23-c5fef105659f`），均缺 usage，与旧 429/2056 不同。新最小真实 MiniMax M3 探活 `acf1a205-b39b-49f6-8553-9c6210c78612` 成功，记录 185 prompt tokens。
- **当前真实 URL 主链 PASS。** 从空项目 `bf405d24-ca25-416e-9929-c9c4fe3a815a`、Chat `3953009d-566a-4c8a-b470-17563f4e2786` 和原始 `/promo-video` URL 话术启动。首稿 Turn `451e99dd-cd08-4bf0-9d0c-71ed4fc3a759` 实际使用一次六幕 `scene_plan`、逐幕 `scene` 和最终 `draft_ref + save=true`，未提交 raw Track/Clip/Op，逐幕请求无历史媒体重复注入。保存 Composition `f0db375f-e762-4766-939a-7c33257f119b` 的唯一版本 `44a9bf4b-1a73-4535-8ce6-b8a0cc8fcee5`（digest `3e4dbc8e81ce83f2506f30c82a0d94a5a98c79f44184645ebb30680722388310`），分镜消息 `7a936c45-be73-4282-98d1-3a4eaa7296cd` 由 API ACK 且确认前零 Run。OK 用户消息 `826650ba-cb80-4706-9c47-24181aac230f`、制作回复 `74fcb76a-4bec-4625-abdb-ef139b093684`；auto 设置未发生报价 Yes。Run `259ac347-17ba-4dc4-bcb1-748e31fac2b3`、视频 Output `95315d77-67fd-4e3b-a712-931776d4b71d` 和交付消息 `2a0df282-163b-468a-a9a4-052fc014f812` 钉住同一 version/digest，交付只引用该 Output。浏览器复验后再由 API 发重复 Yes（Turn/用户消息 `dd98b790-ff3d-406e-b8ff-02adb03a17ff`、回复 `150dc54a-d158-4d14-a33d-8346d5d8165e`），最终仍为 1 版本、1 Run、1 视频 Output、1 交付消息；素材理解 Output `c80d0945-ae7b-4c84-83e7-510c7856c875` 单独计数。
- **当前成功首稿减量。** 16 次 Chat 输入依次 **12,347 / 17,031 / 19,604 / 40,874 / 33,185 / 33,468 / 51,959 / 23,121 / 26,190 / 25,842 / 25,942 / 25,928 / 27,695 / 25,915 / 16,705 / 8,148**，峰值 **51,959**、Chat 累计 **413,954**；辅助准备 1 次 **1,717**，无缺失 usage，已知合计 **415,671**。相对历史成功基线，Chat 累计下降 **56.57%**、已知总量下降 **56.46%**、峰值下降 **31.12%**。OK 为 **1,941 / 2,177**（累计 **4,118**）；报价 Yes 未发生；自动交付为 **17,503 / 17,920**（累计 **35,423**）；浏览器后的重复 Yes 为 **780**。首稿当前媒体共 5 parts，逐幕和后续请求不重复携带，历史媒体为 0。峰值首个 `scene_plan` 请求的剩余主要上下文是历史工具观察 **76,815** 字符、项目/来源文本 **46,880** 字符、system **8,712**、工具 schema **31,754** 和当前媒体 4 parts；字符与 parts 仅作结构证据。
- **当前媒体与浏览器 PASS。** 新 Output 为 15,595,481 字节，SHA-256 `846d97aa9e133139a62a5c0123e61c5a5d7d45d95f8fe01e19ada383780fb495`；1920×1080、30fps、视频流 39.5 秒，完整解码 **1185/1185** 帧，容器 39.552 秒。保存版与 render spec 均有一条音乐 Clip；实际音频全流可解码，872,122 个样本，RMS **−17.802 dBFS**、peak **−4.313 dBFS**、零削波、零音频问题。真实浏览器打开原分镜和交付卡，新 Output 刷新前后均从 0 连续到 `currentTime=duration=39.552`、`ended=true`、`readyState=4`、`video.error=null`；硬刷新后仍是同一交付消息和 Output。历史 Output 同样在刷新前后到达 **42.261333 / ended**。两者媒体响应均为 206 Range；浏览器取消旧 Range 的 `ERR_ABORTED` 没有造成播放器错误或中途停止。此前未达 ended 的原因是脚本只等 1.8 秒便暂停，不是产品播放缺陷。
- **脚本、用户回复与本轮检查。** 注册初次已真实交付后在媒体汇总处失败：`AudioInspection` / `OutputCheckIssue` 是 Pydantic，旅程误用 `asdict()`；现改为 `model_dump()`，没有为重跑脚本另造付费 Run。OK 制作回复曾暴露参数纠错话术，现 `_loop_echo()` 只携带工具修复事实，发言职责归还当前阶段；核心测试覆盖第二次 provider 请求不再包含额外的用户发言指令。重复 Yes 曾在 Run 已完成时说仍在渲染，现 `short_video_confirmation()` 返回真实 `run_id / run_status / output_refs / delivery_message_id`，短确认提示按当前事实作答；原项目复验 Turn `bdb77bd0-7485-4647-955c-a16e5705c7f1`、回复 `dd81d4c9-e8b9-433e-a3e3-013a9930bc2d` 已明确告知完成并指向现有视频卡，数量仍不变。完整 core 当前为 **397 passed / 1 个既有 SFX 文案失败**；`sequential_oxvalue_draft_review` 在项目 `fc7c1a05-37f8-48af-a406-79448af5b499` 真实通过，顺序首稿版本 `ad3497e6-31e8-468f-b6d4-c5c24cc6851e`、标题版 `dbdb5e1e-8c61-4deb-a762-205d2df2d710`，两轮零 Run/Output。`git diff --check` 通过。

### 6.4 当前接线顺序与代码验收

本批只实施 §6.3 第 1 项。§2 是行为合同，§7 是已有基线。以能通过 §6.5 的最小改动为准，优先复用现有函数、工具、回执和测试。保留现有权限、版本、来源和保存校验；新增检查只覆盖合同明确要求或本批可复现的失败。避免预防性兜底、兼容分支、通用框架和顺手重构。

发现当前代码、现行文档或验收条件存在实质冲突时，立即停在冲突点，报出文件行号、实际行为和需要拍板的一项选择，等答复再改该处。保留已完成改动，可继续不依赖该决定的验证。文档未指定的局部实现细节按现有惯例做最小选择，无需逐项请示。以下按实际调用顺序施工。

1. **目标与结构化事实。** 从 `chat/plan_turn.py`、`chat/propose_turn.py` 的 `call_loop()` 接线入手。复用 `video_turn_seats.py::video_context_lines()` 对输出引用的权限查询、`editing/store.py::get_video_version()` 对作品当前 head 的读取，以及 `ConversationContext.restore()` 对草稿候选的恢复。把现有 `tools/project_context.py::load_project_context()` 已生成的资源身份、当前版本和 provenance 在渲染前结构化交给投影，保留 `ContextSnapshot.keys` 的「该资源正文已经投影」语义。明确 @/选择、归属于当前操作的待答目标、明确续接的草稿引用作为目标信号。首条自由文本若无足够事实，沿用现有模型回合和读取/询问，不加分类请求。具体接法为在现有 `get_video_version` 提供编辑用途的窄读法，输入目标及必要的 Scene/Clip 提示，服务端确认 owner 并读取 head，只返回 `base_ref` 和相关目标现值，成功后更新回合事实。普通读版、ACK 和 @Output 仍保留精确历史版本语义。明确的新建请求沿用 `design_video(save=false)` 创建首个草稿，随后凭实际候选进入草稿阶段；未解决的目标歧义保留真实 `ask_user`。同一 Chat 可以同时有多部作品和未保存草稿，存在性和排列顺序不能用来授权写入。
2. **统一轮次装配。** 两个 runner 传同一个装配器，替换视频分支的 `project_round_tools / project_round_context / project_round_system` 三处独立判断。 `agents/tool_loop.py::call_loop()` 在 refresh/restore 和 `active_repair` 确定后调用它，把最终声明、系统文本、当前动态事实和可见媒体送进原 provider 请求；通用循环只传事实及通用修复限制，不导入视频领域。给非视频调用保留现有入口。 `chat/prompts.py` 与现有 Jinja 承担规则条件拼接，`chat/turn_tools.py` 承担按阶段的声明和参数投影，执行侧继续校验当前目标和 digest。已删除审片散文投影、`drafts[-1]` 盲选、按 `snapshot.text` 或历史 provenance 的 Promo 分派；所有 Skill 与保存版使用同一通用 schema。按实际 provider 请求核对基础 user/context 模板、project snapshot、ConversationContext restore 和 observation tail，避免阶段变短却仍附完整工程、旧 pending 或旧视频。
3. **草稿审片与证据。** `working_drafts.py::working_draft_review_facts()` 只给当前相关对象及服务器算出的窗口。收窄现有 `review_working_draft` 的模型声明，服务器从已认证草稿和当前审片阶段绑定窗口，模型不用重填起止秒或复述用户要求。沿用同一工具增加按 `evidence_id` 记录简短判断的分支（通过或具体问题及相关目标），写入现有草稿 review 回执；检查 draft/content digest 和窗口归属。拿到 MP4、模型看后的判断和保存分开。按需预览沿用 `tools/video/preview.py` 及现有 `/preview` 的大小、时长、owner 和解码边界。通过 `design.py` 中现有 `assert_working_draft_review_ready()` 校验已开启的审查范围和未解决问题；默认首稿经完整结构校验即可保存。 `video_turn_seats.py::review_working_draft_seat()` 的媒体沿用 ToolObservation 生命周期，证据第一次作为完整 tool call/result 送达，此后只保留精简回执，使用现有媒体回读能力；Activity 继续取自真实执行与回执。
4. **修复与失效。** 针对 OxValue 反复调 raw position/scale 的实测问题，在现有高层草稿写口支持最小的取景修正（目标 Clip 和真实网页元素引用），复用 `editing/grounding.py::resolve_focus()` 与 `camera_keyframes()`，照常走完整内容校验；测试夹具不得直接写入修好的 Clip。修 `working_drafts.py::review_state_after_edit()` 两处边界：新增重叠 Clip 即使没有出现在旧 receipt 的 `clip_ids` 也要让受影响时间窗失效；明确的 `valid_segments=[]` 保持空，仅历史字段缺失才回退原 scope。 `next_review_target` 从最早有效缺口和相邻接缝算有界复查，避免一有失效就无条件从片头开始。失败保留草稿，禁止将重复预览或覆盖齐全视为问题解决。
5. **保存后定向编辑。** `video_turn_seats.py::revise_video_seat()` 继续走现有高层校验与唯一写口，校验 current `base_ref`、scope 和来源；旧版本或错误目标不能写入。以实际保存的 delta 作为返回，并在已有对应问题且保存成功后结算问题。用新的 provider 请求证明没有首稿片段、旧问题、草稿审片工具和历史媒体。用户只改标题时通过版本差异核验；现有用户明确需要的局部视觉复核保持有界。

### 6.5 本轮收口交付与放行

| 必交 | 可复核的验收 |
| --- | --- |
| 核心确定性回归 | 在现有测试座抓最终 provider 请求，证明计划前后、逐幕、纠错、保存、呈现和标题编辑的阶段隔离；保留简报、明确约束、幕纲、当前来源和实际工具。约束测试覆盖默认值、明确 9:16、绕开 wire、续接与错误后的草稿恢复；音乐读面覆盖有/无保存 Clip。 |
| 真实注册旅程 | 复跑 `sequential_oxvalue_draft_review`，核对 1 → 1–2 → 局部修复复查 → 保存/ACK，以及下一条标题反馈只改目标文字且零 Run/Output。再从空项目复跑 `promo_short_confirmation_delivery`，只使用原始 URL、OK 和必要的报价 Yes，核对同版本 Run/Output/digest、唯一交付及重复确认幂等。 |
| 实际用量与媒体 | 分列首稿、OK、报价、重复确认、自动交付的逐次 prompt_tokens、峰值、累计、辅助和缺失 usage；与历史 953,043 Chat 累计及 75,430 峰值比较。读取实际 Output，完整解码所有帧并用共享音频检查验证保存版所期待的声音。 |
| 浏览器 | 复用同一 Run/Output，区分 API 代发的消息/ACK 与浏览器实际操作；核对分镜、制作邀请、原 Chat 进度/交付卡、播放和硬刷新。技术播放、主观画面与实际试听分别报告，用户终审和完整 P6+P7 不自动关闭。 |

在 `apps/api` 运行 `uv run --extra dev python -m pytest test/core -q` 和受影响注册旅程，另跑 `git diff --check`。保持 20 次循环及现有三次失败收口，不增加上限；已知 SFX 断言单列。更新本页与 PROGRESS §0，未实际完成的验收保持开放。

## 7. P2 实施与当前证据

### 7.1 已落码的链

1. **当前草稿的有界连续证据与独立判断。** `tools/video/preview.py` 复用 `slice_clip`、`compile_video_scrub` 和同一 video-spec 编译；单次不超过 24 秒，窗口由服务端按当前状态绑定。`apps/render/src/server.ts` 的 `/preview` 不上传、不创建 Run/Output/版本；API 解码验证 MP4 后记录证据，模型再以 `evidence_id` 单独记录 pass/issue。未判断证据和开放问题均阻止本批顺序审片保存；修复只失效重叠范围，新增重叠 Clip 也计入，显式空有效区间不会复活。
2. **同一事实驱动目标、提示、工具和保存。** 两个 Chat runner 在 ToolLoop 每轮恢复及纠错状态确定后调用同一个 `assemble_video_round()`。目标来自显式引用、当前操作 pending、唯一草稿/作品等结构化事实；保存版与草稿共存时按本轮目标选择 `version_edit` 或草稿阶段。项目资源带结构化身份和 provenance，不再从 `snapshot.text` 分派 Promo，也不取 `drafts[-1]`。保存版只投影目标当前 head 和适用编辑工具，草稿审片只投影当前草稿及必要来源。唯一写口、base_ref、owner、来源和保存校验不变。
3. **真实 Activity/SSE 与条件发言。** `review_working_draft` 只有真实预览执行才显示检查，有效回执带 `evidence_id`、范围及 digest；判断写入和失败预览不伪装成完成预览。装配器使用开场轮次、既有 interim 计数和本轮新增有效结果选择 opening/finding/silent：首稿计划至多一次，新发现晚于证据，修复/复查/纠错及保存版单点编辑静默。现有 interim_prose 和 Activity 承载显示，无新增 UI、工具、模型调用或持久化状态。

### 7.2 改动文件

- API 草稿与预览：`apps/api/app/agents/working_drafts.py`、`agents/tool_loop.py`、`tools/video/preview.py`、`tools/video/design.py`。
- Chat 工具、执行与提示：`apps/api/app/chat/turn_tools.py`、`chat/video_turn_seats.py`、`chat/plan_turn.py`、`chat/propose_turn.py`、`chat/context.py`、`chat/prompts.py`、`prompts/chat/_video_project.j2`、`prompts/chat/_read_tools.j2`。
- 编辑读取与结构化项目事实：`chat/perception/executes.py`、`models/schemas.py`、`tools/project_context.py`。
- Activity：`apps/api/app/chat/activity.py`、`chat/activity_receipts.py`；本批没有 Web 改动。
- 回归与旅程：`apps/api/test/core/test_previews.py`、`test_provider_tools.py`、`test_delivery.py`、`test_promo_authoring.py`、`apps/api/test/journeys/chat.py`。

### 7.3 测试证据

- 当前完整 core 为 **397 passed / 1 个既有 SFX 文案断言失败**；参数修复观察与重复确认事实的最小定向为 **2 passed**，音频检查另为 **8 passed**。
- `sequential_oxvalue_draft_review` 当前真实通过；原 URL 项目的重复 Yes 已再次经真实 Chat 验证完成状态，未新增版本、Run、视频 Output 或交付消息。`git diff --check` 通过。
- 当前真实 URL 主链、同项目续验和新旧 Output 浏览器刷新前后连续播放均通过；注册脚本自身的 Pydantic 序列化错误已最小修复。技术播放与最终用户主观视听分开报告。

### 7.4 当前真实用量与结果

- **内部安装 Shotcraft 的真实主链 PASS。** `promo_short_confirmation_delivery` 从空项目 `41316eb7-9bc7-4f5b-9f2c-8c018822d44f` 和原始 URL 请求开始，首稿 Turn `e9adb675-c89c-45e4-9331-a7ce2c4e9bd3` 实际读取安装包的 Gallery、创作方法与镜头卡。唯一版本 `265c8af7-18a6-4f04-b2a6-4613f7b67556` 的 provenance 固定 `bdd94be16d60fa8f`，分镜消息 `94bf873b-364e-4956-a398-5268b6134486` ACK 之前零 Run。`OK` 创建 Run `8c0e3a92-d299-41d9-a95d-38956cbd4d6f`，自动交付消息 `de18e3ec-dd5f-4f3c-83d1-a359dceb6d2a` 只引用同版本 Output `a222538d-37f1-4190-9ce0-40f480a042c4`，重复 `Yes` 后仍各一条。实片完整解码 968 帧，1920×1080、30 fps、容器 32.32 秒，保存版无音乐 Clip，实际音轨为静音。共享库五首 BGM 对象与安装包逐字节一致。首稿 Chat 20 次共 695,534 输入 tokens，峰值 68,228，辅助 1,717，另一次辅助缺 usage。旧 Promo 包成功首稿的 413,954 独立保留为对照。 同一 Output 浏览器硬刷新前后均连续播放到 32.32 秒并收到 `ended`，`video.error=null`。独立真实 Chat 项目 `77ff9f0a-c039-4ed8-ae52-b0dbf8034615` 通过共用选曲与准备入口把 Cat Walk 存为一条 music Clip（版本 `26140c25-cb08-4998-bd2c-18629ff8c76e`），零 Run。

- **当前最终 URL 证据。** 项目、Chat、Turn、版本、Run、Output、交付、重复 Yes、逐次 tokens、解码、音频及浏览器事实统一见 §6.3.1，避免以旧顺序审片用量或历史交付替代本次成功首稿。

- **本轮顺序审片注册。** 项目 `c7a15dd8-4253-42fd-b5b6-00e54329d47a`，会话 `9723ed30-1aaa-4955-8bce-533724a029ce`，作品 `69da7ab4-f406-48b8-ac55-4ecdf33e0c4a`。首稿 Turn `8076c6fe-b330-4a2a-a59c-b5e1fea45222` 保存版本 `4698ddac-2147-461e-a747-be4b0d0b2cfa`，只改 `clp_review_web`；实际窗口 0–4 / 2.5–8 / 4–8 秒，证据 `a3c06080aec06315f6f78f52` / `71be839eca043e06d7c4a795` / `7f7e47e9f78fdd389fa0aa01`。10 次输入 **11,422 / 12,752 / 14,452 / 14,306 / 17,943 / 15,422 / 15,521 / 18,190 / 16,185 / 3,933**，峰值 **18,190**、累计 **140,126**；当前媒体只在三次判断各一段 MP4 + 一张代表帧，历史媒体为零。标题 Turn `025af309-aee0-4a11-b986-dacaaed2b4bd` 保存 `bece8d82-2487-44a9-b5d6-764ed8dd9204`，只改 `clp_review_headline`，输入 **2,217 / 2,422**，累计 **4,639**；两轮零 Run/Output。相对此前 `bd451034-004e-4681-80db-2bea74578eb2` 的 238,672 / 7,154，分别下降 **41.3% / 35.2%**。

- **默认首稿与按需预览。** 使用已有 OxValue 工作草稿分别走真实 Chat。明确保存的 Turn `a2220437-7a8b-49cf-b154-5e99fa92fb3d` 直接保存 `ee150958-4100-4831-85e4-bb441628e476` 并 ACK，零预览；只看第二幕的 Turn `68b7f9f0-2c51-4041-b8d8-5144cbc2d775` 只取得 4–8 秒证据 `ae541526dacbfaded37a361c`，保存 `9613e096-b4d7-4d67-8366-aaad6cbb0530` 并 ACK。两项零 Run/Output。明确要求顺序审片的原注册完整通过，首稿版本 `cfb7404b-3ce1-4718-a9cd-3894b4e47383`，同会话标题版本 `34a858ed-49a8-4ef0-8a32-d4eb3d2953e4`；输入分别累计 **241,107 / 7,194**。完整 core **389 passed / 1 个既有 SFX 文案失败**，定向 **60 passed**。

- **真实两轮注册通过。** `sequential_oxvalue_draft_review` 返回 `All 1 journey(s) passed`。项目 `53eb3cac-2fb3-43c5-b915-0be6cd63c469`，会话 `9ab393c1-1cb3-4315-a7e5-755d22967502`，作品 `ecea515d-1ed1-48c9-bdf5-59da27f7d67a`。两轮合计零 Run、零 Output。
- **首稿审片及保存。** Turn `a44afc99-7345-4c3f-8ed0-127ba7e6c7b7`，版本 `e28faa92-4ad6-4eca-b531-a2d627deee99`，只改 `clp_review_web`，发现时序及分镜 ACK 通过。真实预览窗口 0–4 / 2.5–8 / 4–8 秒，证据分别为 `a3c06080aec06315f6f78f52`、`71be839eca043e06d7c4a795`、`19e8dc630196c977bc9793ba`。11 次调用输入 **27,065 / 31,129 / 29,501 / 32,369 / 28,574 / 29,290 / 32,864 / 30,337 / 35,191 / 31,989 / 47,537**，累计 **355,846**；媒体仅在三次判断请求各出现一段，历史媒体为零。两次可选判断字段格式错误后回合自行恢复，20 次上限保持。
- **同会话保存版编辑。** Turn `be0424c4-11a3-48cf-88e6-21a7bf37595f`，版本 `d87ab3fc-907d-4f61-bad8-3583a91aa4f9`，只改 `clp_review_headline`。三个请求均为 `version_edit`，无中途说明、首稿工具或当前/历史媒体。输入 **46,520 / 47,263 / 47,123**，累计 **140,906**。
- **明确标题替换的上下文减量。** 原注册在项目 `48f5fc06-1f93-4881-a9aa-28cdccacd526` 完整通过。首稿版本 `4609fb95-9937-4333-94d2-e4fefd698741`，同会话标题 Turn `2fa90278-4e26-4d22-be47-bb27c0e7cf51` 保存版本 `09fe02a9-3270-48ed-98b5-abcad2818bf0`，输入 **2,282 / 2,338 / 2,917**，累计 **7,537**。第三次调用由空正文的 `answer` 引起；最终版保留已保存状态并明确终态正文要求。
- **最终代码的真实标题回合。** 同一项目 Turn `220ab9e8-3698-4386-9190-7118596e92d8`，版本 `c0c12b8d-d845-4111-8d78-a0a053700a83`，只改 `clp_review_headline`，零 Run/Output、零 delta、零中途说明。provider 输入 **2,206 / 2,339**，累计 **4,545**。两次分别只声明修订加回答、仅回答，无额外读版。字符量仅作请求结构参考：系统提示 **348 / 229**，工具 JSON **5,629 / 4,367**，当前项目事实 **462 / 461**，历史消息和当前/历史媒体均为零。
- **首稿误判对照。** 原失败与成功请求都收到同一段 2.5–8 秒 MP4（SHA-256 前缀 `fd7d2f8bc077`）和同一验收要求。实际抽帧显示错误画面末段停在 Frame / Enrich，修复后稳定显示 Value / Defend。用同一 MiniMax M3 对修复前后各做一次原装配与精简装配对照，均给出 issue / pass；精简请求输入分别从 **32,345 → 24,961**、**35,191 → 27,807**。对照支持证据分座，尚无法证明误判率下降。
- **首稿保存后的阶段隔离。** 去掉来源正文后的真实 Turn `06267606-9643-4bd3-93b0-8975ea6f3f66` 正确发现、修复和复查，但首稿成功保存后转入 `version_edit` 又写一版。现按同回合保存事实切入 `draft_present`，仅开放分镜回复；新用户反馈才进入保存版编辑。
- **最终注册复验通过。** 项目 `3e6745b5-e35e-48c8-aba2-18900a4d426a`，首稿 Turn `ba02d568-c297-480a-ac0c-c3bf3c6be2e3` 保存版本 `9d503a33-7d29-40be-aeca-3f1575addb63`，只改第二幕网页 Clip，复查证据 `26031c6b7e5b147e870ee7be`，分镜 ACK 通过。首稿 15 次调用，累计 **430,474** 输入 tokens，峰值 **35,303**；同会话标题 Turn `b88cdc30-c88f-4d79-aa45-01d8e966d430` 保存版本 `ad226ff1-9358-447c-9ae2-adc58d432895`，输入 **2,282 / 2,412**，仅改目标文字。两轮零 Run/Output。
- **同窗正反样本及最新注册通过。** 用同一 MiniMax M3、同一要求和 4–8 秒窗口各测两次，错误取景两次 `issue`，正确取景两次 `pass`，代表帧均为输出 7.733 秒。最新注册项目 `bd451034-004e-4681-80db-2bea74578eb2`，首稿 Turn `d35d13a0-640b-4a40-851f-26aa5626b7f8` 只改第二幕网页 Clip，保存 `a83bf3e5-8793-416a-8a63-844dcc99f4f6` 并 ACK，9 次输入 **27,140 / 25,282 / 30,023 / 26,780 / 32,196 / 29,582 / 28,834 / 32,040 / 6,795**，累计 **238,672**；三次判断各带一段 MP4 和一张同源代表帧，其他请求无历史媒体。标题 Turn `8b888ae5-c023-4754-b6c1-dd93dd846ba9` 只改目标文字，保存 `fdeec706-8407-4fdc-990d-e0d655e40c2b`，输入 **2,217 / 2,412 / 2,525**，累计 **7,154**。两轮零 Run/Output。
- **取景与发言约束。** 真实网页快照以 `snapshot:` 资源键识别，`kind` 保留真实类型 `web`。有取景候选时模型只能提交目标 Clip 和元素，服务端拒绝同时带其他内容写入。旅程把 `focus_clip_id` 纳入编辑目标统计，仍按实际版本差异核对范围。已接受的发现只显示一次，静默阶段由 ToolLoop 执行。

### 7.5 剩余验收

- **内部 Skill 边界。** `/promo-video` 由部署方安装并绑定固定 Shotcraft 版本，安装目录和配置见 VIDEO_PROJECT §8.1.2。用户从现有选择器使用。Shotcraft / Talkcraft 的已注册 Generator 样本作为独立宿主回归。
- **首稿判断与开销。** 多素材、多模型的误判率仍待复验；标题减量主要覆盖明确引用新文案的单点替换，开放式及复合编辑成本未全局优化。本轮只按真实请求减少重复装配，不声称已优化所有创作形态。
- **完整 core 复验。** 当前工作区运行 `uv run --extra dev python -m pytest test/core -q`，结果为 **396 passed / 1 failed**。唯一失败仍是 `test_media_import.py:215` 的旧 `Persisted SFX candidate sets` 文案断言，当前实际标题为 `Persisted audio candidate sets (internal references for a later selection turn):`。
- **视听与后续边界。** 历史确认版没有音乐轨且实际无声；当前新确认版有一条已保存音乐 Clip，实际非静音音轨已验证。新旧 Output 的技术连续播放和刷新恢复均已通过，但最终用户主观视听、实际试听与音画同步、完整 P6+P7、runner 环境、Remotion 许可、部署与公开发布仍开放。旧 Promo 协议已退役，技术验收不自动代替用户终审。
