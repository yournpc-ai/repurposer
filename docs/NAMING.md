# NAMING — 命名宪法与判例库

> 现行工程命名规范。产品目标和编辑循环归 [Agent 总合同](tasks/new-agent.md)。
> 适用范围：模块 / 包 / 表 / 字段 / API / tool / skill / 事件——一切会被别人读到的名字。
> 用法：命名争议不复述本文论证，引用条目号（`NAMING §3`）或判例号（`N-29`）。判例只保留现行裁决——过时 / 被翻案的判例直接删除（历史在 git，不留痕）；新判例追加新编号。

## 1. 八条宪法

1. **一个概念一个名字，全栈统一**。同一个东西在表、字段、API、模块、前端词汇里必须同名。改概念 = 全库改名，不留旧词过桥层。
2. **包/模块用单词名词，函数用动词，枚举值用形容词/名词**。`chat/`、`pipeline/`、`apply_composition_edits()`、`behavior: "deterministic"`。
3. **禁用后缀黑名单**：`*_manager` / `*_engine` / `*_helper` / `*_utils` / `*_handler`。这类后缀意味着职责没想清楚——它该是现有包里的一个函数，或者职责值得一个真正的名词。例外：计算机科学既定名词（`compiler`、`scheduler`、`worker`）。
4. **布尔语义优先可空时间戳 / 可空枚举**。`pinned_at` 优于 `is_pinned`（白得审计信息）。
5. **枚举 = String 列 + 应用层注册表校验**（ADR-028 D6 先例）。新类型零表迁移；注册表是唯一守门人，DB 不重复约束。
6. **行话黑名单：编译器 / 框架黑话不进业务词汇**。团队通用词优先；一个词需要解释才能懂，就换一个不用解释的。
7. **分组准入测试**：新模块 / 新目录必须拥有**独立的表归属**或**独立的队列认领源**，否则它只是现有模块的职责扩充，不配开包。
8. **准入即登记**：新名词通过评审后必须进 §2 词汇表（中英映射唯一）；新判例进 §3。词汇表是冻结资产，改词 = 改文档 + 全库改名。

## 2. 领域词汇表（中英映射唯一，冻结）

| 中文（文档） | 英文（代码） | 定义 | 不是什么 |
|---|---|---|---|
| 原生调用 | native tool call | 用 opening 与模型给出的 call ID 定位，按 call_index 排序 | 执行回执保留原身份 |
| 媒体任务 | MediaJob | 生成或复用授权素材，固定 SourceSnapshot | 状态由媒体 Worker 维护 |
| 正式导出 | ExportJob | 从已观察版本渲染并验证 MP4 | 成片身份为 Output |
| 对话 | `Conversation` | chat 的会话容器 | 不是 thread、不是 session（撞 auth session） |
| 素材理解 | `MaterialUnderstanding` / type `material_understanding` | 素材处理完成后产出：素材级理解（论点带位置/金句/主题/受众 + 节拍地图），内容寻址复用（`content_sha256`，同用户跨项目） | 不含任务信息 |
| 节拍地图 | beat map（`MaterialUnderstanding` 期 1 字段集） | 素材级语义节拍：`topic_boundaries` / `climax_spans` / `emphasis_words` / `quotable_lines` / `narrative_role_hints` / `visual_anchors`——LLM 只出文本锚（+ 可选秒数提示），`start`/`end`/`asset_id` 恒由代码吸附 ASR 词轴（locate_span 同纪律，词级时间戳零覆写） | 不是节拍方案（beat plan = 期 2 剪辑师产出）；声学半不住这里（`asset.meta["prosody"]`） |
| 韵律 | `prosody`（asset.meta 键） | 确定性声学特征工序（PROCESSORS 链，ASR/speaker_map 同族）：逐词 F0/能量 z 分、强调峰（f0/energy 声道分标不合流）、filler/死寂区 | 不是语义强调（`emphasis_words` 是语义半——两字段永不合并，预合并 = 自信地错且不可溯源） |
| 内容寻址 | `content_sha256`（asset.meta 键） | 素材字节哈希（处理链首工序/粘贴文本创建时盖章）：理解层复用的寻址键，同素材二次上传零 LLM | 不是 asset id / file_url（那是上传身份，仅作无哈希行的回退） |
| Agent | Agent | 根据用户要求、当前作品和观察自主决定下一次原生调用 | 共享模型调用与计量 |
| 工具 | native tool | 名称、参数 Schema、描述及服务端执行函数组成模型可调用的操作 | 实际工具目录由本轮 Context 决定 |
| 视频工具 | app/tools/video | 读取、生成、预览与审片复用的视频领域实现 | 权限和资金由服务端校验 |
| 指令包 | Skill | 由版本化的指令和参考资料向 Agent 提供创作方法 | 不持有执行权 |
| providers | `app/providers/` | 外部服务包装的一统家：**`llm/` 子层 = Model 缝**（含 PRICING 价目表；第二 provider 的家，ADR-025 薄接口落地处）+ asr / voice / vision / storage 等；**禁 import agents/、禁 import LLM 决策层**（N-29 铁律，grep 门禁） | 不是能力（能力归工具包） |
| 调用面 harness | harness | 模型调用面脚手架：Agent 漏斗（装配→渲染→调用→校验→修复一轮→计量→声明兜底）+ contexts 装配 + prompts 模板 | harness 单义 = 本行（N-48）；测试脚本不叫 harness（那叫剧本矩阵） |
| 视频检查 | review_video | 从确切 Output 读取并解码实际视频 | 后续交付验证已审文件的摘要 |
| 产物 | `Output` | 钉住来源版本的正式交付文件 | 历史行保留原身份 |
| 提及 | mention | 对话中的 @ 实体引用 | 不是 reference、不是 entity |
| 成片卡 | Output | 按消息的 output_refs 展示确切成片 | 可以播放和下载 |
| 提问 | ask_user | 模型发起的原生提问 | 持久化到 messages.question |
| 问题 | question | 持久化普通问题、分组问题或确切的费用确认 | 以消息 ID 作答 |
| 文字问 / 选项问 | question | options 或 items 给出可选择的答案，普通文字问题允许自由回答 | 分组使用同一问题 ID |
| 回答 | answer | messages.answer 记录 option、freeform、group 或 bail | 原问题行可在刷新后读取 |
| 派生来源 | `derived_from_output_id` | 派生行 `source_ref` 内的溯源指针（住 JSONB） | 不新建表列 |
| 字幕样式目录 | `CAPTION_PRESETS` | 字幕样式注册表（packages/clip）：preset id → 原语组合；TS 类型由它推导，Python 只校验成员 | 不是自由样式（preset 枚举纪律不变） |
| 布局 / 进场 / 词级高亮 | `layout` / `entrance` / `wordHighlight` | 字幕样式三原语：single\|stack × none\|fade-in\|pop-in\|slide-up × bool | — |
| 堆叠 | `stacking` | catalog 成员：新行淡入、旧行驻留、超 maxLines 滑动窗口 | — |
| 工作室 | `studio` | 登录后的应用区域 | 产品角色见 Agent |
| 助手 | `assistant` | Chat 消息中的助手角色 | 对外描述由产品要求决定 |
| 历史需求字段 | pending_brief | 仍由特定旧消费者及历史消息读取，按实际归属保护 | 通用编辑轮无必填 Brief |
| BrandProfile | `CreativeState.brand_profile` | 本项目、特定 SourceSnapshot 派生的品牌档案：positioning / claims / taglines / colors / typography / brand_assets / inferred creative_direction / unknowns / conflicts + source refs / extractor version / content digest；证据事实与视觉推断分列，原始 Snapshot 不被覆盖 | 不是 `persona.brand` 皮肤；不是全局品牌手册、作品根或独立主表 |
| 创作状态 | CreativeState | 创作中保存在 ProjectBrief，保存后随不可变内容固定 | 来源和约束保留各自身份 |
| 用户旅程矩阵 | `test/journeys/chat.py` / `JOURNEYS` | 预设多轮用户旅程对活 API 验证用户可见结果与服务端/数据库真值（真实模型不锁文案）；与 `test/core` 的核心 API/DB 确定性测试分属两类测试资产 | 不叫 harness（harness 单义 = 调用面，N-48）；未运行不得写成通过 |
| 风格 | `style` | 文风（写作风格），对外文案统一用词（hero/showcase/FAQ/identityEcho 已全扫）；voice 仅保留音频本义（声纹克隆/配音 dub） | 不是"口吻"；不是 voice |
| 声纹块 | `personas.voice`（JSONB） | 人设的声音绑定（音频本义，N-28 归还）：`{"kind":"cloned","voice_id","sample_asset_id"}` \| `{"kind":"stock","stock_id"}` \| NULL=Auto；旧 voice 文本（文风）已并入 `guidelines`，不再单列 | 不是文风（文风 = `style` + guidelines） |
| 皮肤块 | `personas.brand` | 仍由历史 Persona 深链读写的品牌配置 | 不作为普通 Chat 的启动条件 |
| 提及类型 | ChatMention.type | API 类型包括 asset、output、transcript_segment 和 recipe | 引用有效性由服务端检查 |
| 提及注册表 | `MENTION_REGISTRY` | 前端提及类型注册表（icon / i18n / 候选源）；picker 与 chip 只读注册表，新类型 = 一条注册项 | 不是 switch 分支、不是插件系统 |
| 活动行 | Activity | 按原 opening、原生 call ID 和持久消息展示执行回执 | UI 交接列出了当前消费类型 |
| 内容层 | content layer（`assets.transcript`/`extracted_text` + `assets.edited_transcript`） | ADR-113：transcript = 素材行的内容层，**全局唯一存储座**（读口 `pipeline/assets.py:asset_text_content`）；`edited_transcript` = 改稿覆盖层（C4 双层不变量：改稿只写覆盖层，源层 + `meta.words` 词级时间戳永不动；写口 `PUT /projects/{id}/assets/{id}/transcript`，零 run 零积分）；cues 永不持久化（读时 `group_cues`/`display_cues` 一法推导） | 不是节点（transcript document 节点已退役，存量迁移硬删）；不是第二存储座 |
| 时间条 | time strip | 素材卡转写区的条带：cue 块 ∝ 时长 + 停顿留白 + 1px 播放头针（骑 inline 播放器时钟）；点击 = 拨头（ambient-muted 律不动） | 不是进度条（无控制柄）；不是轨道栈（那是产物卡面） |
| cross-highlight | cross-highlight（`lineageHover` prop 对） | 血缘的唯一跨卡通道（ADR-113 §6，禁泛化）：成片卡视频轨块 hover 上报源区间，源素材卡时间条/cue 行重叠者点亮 `--lineage` 琥珀（灰阶画布唯一色相）；hover 撤即灭 | 不是边（血缘真边已退役——编排语义为零的关系不成边）；不是泛化高亮总线 |
| 人设 | `Persona` | 历史用户资料与素材的归属 | 素材中的说话人用 speaker |
| 记忆层 | `app/memory/` | 维护现有 Persona 资料及相关上下文 | 不承担创作编排 |
| 轨道 | Track | Composition 时间线中持有 Clip 的有序轨道 | 定义见 §2.1 |
| 片段 | Clip | 在作品时间窗内承载 Object，可绑定固定媒体源 | 源时间与作品时间分别记录 |
| 说话人时间轴 | `speaker_map` | 素材级内部分析产物（谁在何时说话、在画面哪侧 + 素材形态归类），asset-hash 复用；crop_track 的上游（reframe_clip 消费） | 不进 TOOL_REGISTRY；用户永不见 |
| 积分 | `credit`（复数 credits） | 用户面唯一计价单位（ADR-055）：估价 / 扣费 / 余额全部同一单位；序列化派生不落列（fold × `credits.per_cost_usd`）；zh 界面词 = 积分 | 不是 USD（内部成本层永不上 UI）；不是 token |
| 钱包 | `wallet`（`wallets` 表） | 用户积分余额 + 够不够花判定（ADR-055）：首登 lazy 开户 + grant；`balance` 是台账的物化缓存（允许为负），`version` 乐观锁 | 不往 `users` 加列；不是支付账户（支付订单 = `payment_orders`，PAYMENTS） |
| 台账行 | `credit_transactions`（表） | 积分余额变动唯一事实源（ADR-055）：append-only，kind ∈ grant / purchase / hold / capture / release / refund / adjust；`idempotency_key` UNIQUE 一等列；ledger 是子系统概念名不上表名 | 不叫 entry（双 entry 会计第三层用不到）；不叫裸 `transactions`（撞 DB 事务语境） |
| 消耗比例 | `credits.per_cost_usd`（configs key） | 每 $1 provider 成本的积分价（默认 1000）：报价 fold 与实扣同源单点，调参不发版、不动历史账 | 不是购买比例（钱→积分汇率 = 积分包定价决策，PAYMENTS，解耦） |
| 支付订单 | `payment_orders`（表） | 一次法币购买的内部订单：用户、套餐、金额/币种/积分快照、provider Session、状态与对应 purchase 台账行；Owner = 平台层，字段与状态机归 PAYMENTS | 不是 credit_transaction（积分事实）；不是 Stripe Session 本身；不是订阅 |
| 积分包 | credit package（`PACKAGE_REGISTRY` / `package_key`） | 服务端可售白名单：当前环境 Price、金额、币种与应授积分；客户端只选 key，永不能自报价格或积分 | 不是订阅 plan；不是前端价格常量；不是消耗比例 |
| 公共参数表 | `configs`（表）/ `get_config()` | 运营参数的统一家（ADR-055）：`CONFIG_REGISTRY`（key → default/类型/desc）是唯一事实源，表只存覆盖值，启动 reconcile 补插；读取一个漏斗，未知 key 报错 | 工程参数禁入（连接串/密钥/保险丝留 env `config.py`）；模块禁直查表 |
| 活动 | Activity | Agent 工作的用户安全观察流（可见性机制）：stable activity_id + sequence + started→completed/failed/cancelled，append-oriented | 不是 CoT / Tool Log / lifecycle authority / presentation 驱动器（永不控制 Canvas/Confirm/Run） |
| 活动投影 | ActivityFramePayload | 来自 messages.intent.frame，按 seq 回放，同组使用 call_index | 顺序与状态分别取自同一调用 |
| 系统状态 | System Status | `phase` 的保留义：系统宏观态（三概念分家——System Status / Agent Activity / Assistant Conversation） | 不再是 Activity container |
| 任务意图 | Task Intent | 自然语言请求的语义——含明确输出/语言/数量/范围；指导 Agent 检查与编辑 | 不是制作意图，也不是付费执行授权 |
| 制作意图 | production request | 用户要求生成某种媒体或导出指定版本 | 服务端逐操作检查费用授权 |
| 付费执行授权 | media_permission | 对确切参数和报价的同意，批准后才可按账户规则预占 | 实际结算使用原执行回执 |
| 言语提交协议 | speech commit protocol（DeferredFrames = 最小形态） | 凡依赖终态裁决的言语，裁决落地前永不 commit（ADR-099 §7）：缓冲 + 落地时刻再裁决（OPEN → BUFFERING → ACCEPT→FLUSH / REJECT→DROP→RETRY，RETRY 陈 buffer 必清），被拒言语从未对用户发生；与终态裁决无关的安全言语不缓冲照常即流；代码永不解析自然语言散文判定承诺（已告诉用户什么恒由结构化终态 payload 约束） | 不是悲观串行（先校验后流出 = 死寂首字延迟，已否决）；不是 token 级安全段识别（需模型自标 = 自报状态，永禁）；不是第二套 speech routing |
| 建议点选引用 | suggestion_ref | source_turn 与 suggestion_id 标记所选建议 | 费用仍需独立授权 |
| 建议源态 | source_state | 检查引用素材、后续素材理解和已提交的作品版本 | 过期事实进入下一轮上下文 |



### 2.1 Video Project 目标词汇（ADR-145）

以下名称是代码落地时的全栈同词标准。A 批 1 已落地：`Composition`/`CompositionVersion`/`SourceSnapshot` 表与 `app/editing`、`app/tools/video`、`packages/video-spec`、video-spec 家族（`family="video"`）；Skill/VideoTemplate/Preset、TextPart、Scene 完整职责仍 TARGET。

| 中文 | 英文（目标代码） | 定义 | 不是什么 |
|---|---|---|---|
| 影片 / 作品 | `Composition` | 一部视听作品持续修订的稳定身份，拥有 owner、origin_project_id 与 current_version；同一 Chat 可有多个 | 不是 Chat/Project、渲染器组件或 Output |
| 作品版本 | `CompositionVersion` | Composition 的不可变编辑版本，直接承载 settings/sources/scenes/timeline/provenance/content_digest | 不是整个 Project 的快照、Run、Output 或 pending_brief 内的可变信封 |
| 时间线 | `timeline` | CompositionVersion 内部的 Tracks/Clips/Transitions 与时间结构 | 不是独立作品根、独立表或 Composition/Sequence 的别名 |
| 场景 | `Scene` | 输出时间上的叙事范围，含 intent、可空 visual_description 与 speech_clip_ids，脚本引用 SpeechObject.text | 不是 Track，不等于单个 Clip/镜头 |
| 画面描述 | `Scene.visual_description` | LLM 对当前真实视觉元素与运动的用户可读摘要；视觉修改必须更新或清空 | 不是 renderer 输入、结构真相或可失实保留的旧文案 |
| 片段 | `Clip` | Track 上有输出时间窗的编辑项，内含 Object，可引用 SourceSnapshot/source_range | 不再专指旧 clip-spec；不是 `is_clip` 布尔变体 |
| 对象 | `Object` | Clip 内可渲染、可变换、可动画的内容 | 不自行决定 Track 和输出时间 |
| 生成对象 | `GeneratorObject`（`kind="generator"`） | 创作层保留程序或模型请求及参数，受控生产固定媒体后参与合成；目标以 `producer = draw-2d / remotion-project / image-generation` 区分生产方式 | 不是执行节点 `prototype="generator"`、Run 或每供应商子类，不向 video-spec 注入可执行代码或模型请求 |
| 2D 程序绘制 | `draw-2d` | Agent 编写受控 2D 绘制程序并生产固定媒体；替代旧名 `drawing-v1` | 不是自由 DOM、业务执行图或原生矢量对象的逐项可编辑承诺 |
| Remotion 工程 | `remotion-project` | Agent 编写完整、不可变的多文件 Remotion 工程，经隔离 runner 烘焙为固定媒体；替代旧名 `component-v1`，不再以单组件为创作上限 | 不是外部 Skill 脚本权限、动态 npm/网络/DB 权限或最终 spec 对象 |
| 图像生成 | `image-generation` | 保存模型图像生成请求，授权制作后固定实际图片；替代旧名 `image-v1` | 不是固定 ImageObject、任意供应商参数或免授权生成 |
| 镜头卡 | shot card | Skill 包内的镜头意图、参数、能量、已知坑与参考实现位置 | 不是新作品层、运行期镜头注册表或 renderer 组件身份 |
| 镜头静态索引 | `library.json` | 卡名、变体、分类与预览的发现/消歧索引 | 不是动态 import、执行注册表或第二作品模型 |

`GeneratorObject` 的字段为 `producer`；旧 `runtime` 与旧值只在既有 CompositionVersion 读兼容、迁移合同和历史证据中保留，不作为活跃写口。
| 音效 | SFX | 固定音频来源，经 Audio Clip 参与作品 | 与配乐、旁白共用编辑和预览 |
| 波形播放器 | `WaveformPlayer` | SFX 候选与音频 Inspector 共用的真实播放/seek/进度组件；bars 是绑定稳定音频身份的确定性视觉表达 | 不是 VoiceRecorder、随机波形、真实音频分析、候选写口或第二作品编辑器 |
| 动画 | `Animation` | 所属 Clip 内针对 Object/TextPart 属性的关键帧序列与分段 easing | 不是 Clip 间 Transition，不是 Text 专属能力 |
| 文字部件 | `TextPart` | 由 TextObject 派生的 line/word/grapheme/span 可寻址对象 | 默认不是独立 Clip，不按数组下标静默重指 |
| 素材快照 | `SourceSnapshot` | 素材某次内容的不可变 digest、manifest/transcript/views 与存储引用 | 不是 refresh 会覆盖的“最新 Asset”或 page_readings 缓存别名 |
| 旁白对齐 | `NarrationAlignment` | 最终音频与讲稿的句/词源时间、文本范围、锚定/插值来源及 Agent 语义标注的不可变事实；准备完成后供 CompositionVersion 引用 | 不是 ASR 原文副本、可独立编辑的 timestamps 文件、置信度分数或第二作品根 |
| 旁白锚点 | `NarrationAnchor` | Animation 从特定 NarrationAlignment 的 sentence/word/text_range 解算输出帧时保留的来源引用 | 不是浮点秒、渲染器输入或跨文本版本静默重指 |
| 分镜采集计划 | `CapturePlan` | 由选定网页镜头产生的有界路由、状态、元素、动作与制品要求，经现有 WEB_PAGE Asset 队列生成新快照 | 不是任意浏览器脚本、登录/表单提交权限、全站爬虫或第二意图入口 |
| 视频模板 | `VideoTemplate` | 可确定性展开为 CompositionVersion 的结构、槽位、有界 repeat/variant | 不是 PromptTemplate、assistant 文案或执行脚本 |
| 预设 | `Preset` | Animation/Caption/TextStyle/Audio 等局部参数组合，实例化后展开 | 不是整部 VideoTemplate，不是 Renderer 运行时查询依赖 |
| 视频预设候选面 | `VideoPresetCandidateSurface` | Chat 内展示 2–4 个注册 Preset 的真实动态预览，经 `video_preset_set` 持久化并由普通语言选择 | 不是外部 Gallery、直接改作品按钮、mention、第二意图面或模板编辑器 |
| 提示词模板 | `PromptTemplate` | composer 可见预填；当前 Recipe 的目标语义 | 不携带隐藏执行参数，不叫 VideoTemplate，不要求 UI 出现“配方” |
| 视频渲染契约 | `video-spec` | CompositionVersion 编译出的 renderer-neutral 自足渲染输入 | 不含 React/Remotion/DOM/任意 CSS，不是 CompositionVersion 本身 |

**命名裁决**：Project 是 Chat/执行上下文，Composition 是影片身份，CompositionVersion 是内容版本，Timeline 是内部时间结构。选 Composition 表达 MG/网页/文字/媒体的时空组合，不同时引入 Sequence、Work / WorkDocument。用户面沿用影片名称、画面、字幕、版本；首稿使用 create_video，后续按实际编辑操作选择原生 Tool，正式导出使用 export_video。

当前内置 Skill id：产品宣传沿用 `launch-film`，口播动效 = `talking-head-video`，文字动画 = `text-animation`，知识讲解 = `knowledge-explainer`。新增核心宣传 Skill = `promo-video`，用户面 zh = `/宣传视频制作`、en = `/Promo video`；其实现与 Home 新入口绑定归 `tasks/skill-package-promo-video.md` P4，旧 launch-film 的既有绑定和 provenance 不改名。这些是内部引用与包名；picker/chip 的 zh 用户面名称依次为 `/产品宣传视频制作`、`/口播动效视频制作`、`/文字动画视频制作`、`/知识讲解视频制作`，en 依次为 `/Product promo video`、`/Talking-head motion video`、`/Text animation video`、`/Knowledge explainer video`，永不把内部 id 当作用户面 Slash 名称。十六个原生 Preset id 固定为 `caption-phrases` / `text-reveal` / `text-impact` / `typewriter` / `keyword-fill` / `word-cycle` / `claim-layout` / `highlight-sweep` / `path-underline` / `callout` / `flow-steps` / `comparison-columns` / `card-stack` / `list-reveal` / `notification-stack` / `title-lockup`；它们是展开注册表条目，不是 Object kind、renderer component 或 mention。


内容修订产生 CompositionVersion。历史交付和跨 Chat 引用钉住具体 Output 与版本。

## 3. 判例库（只保留现行裁决）

| # | 判例 | 裁决 | 依据 |
|---|---|---|---|
| N-01 | Output | 交付使用真实 Output 和版本身份。 | §2.1 |
| N-05 | 否决 `ai/` 顶层目录 | 不拥有表、不认领队列、不对应部署单元——按技术风味分组 = `services/` 错误的高配版 | §1 规则7 |
| N-06 | 六模块包 + routes 入住模块 | `routers/` 平顶解散，模块自包含（routes + service + 逻辑）；skills/tools 永无 routes | §1 规则7 |
| N-07 | `services/` 目录废除 | 18 文件混四个架构层；按层分家（pipeline/chat/skills/tools/memory/platform） | §1 规则7 |
| N-22 | 应用区 | Studio 是应用空间名。 | §2 |
| N-26 | chat 流式词族：delta = 散文预览增量，envelope = 终帧信封 | 流式三层各一词：LLM 原始片 = fragment（`on_delta(fragment)` 入提取器）；解码后散文增量 = **delta**（SSE 帧 `assistant.delta`，纯预览，非事实源）；终帧 = **envelope**（`turn.completed`/`turn.failed`，完整 ChatResponse，永远权威）。机制名：`ProseDeltaExtractor`（唯一散文提取入口）、`MiniMaxClient.generate_stream`、service 拆分 `prepare_chat_turn`/`execute_chat_turn`、前端 `streamChat`。禁 chunk/token 混用（chunk 是 HTTP/LLM 传输单位，token 是计费单位，delta 才是渲染单位）（ADR-034） | §1、§5 |
| N-27 | Persona 与 speaker | 前者为用户资料，后者是素材中的说话人。 | §2 |
| N-28 | Persona 配置 | `persona.brand` 保存皮肤，`persona.voice` 保存音色绑定，历史资料沿用这些名称。 | §2 |
| N-29 | "班组/班底"式自造词禁令 + agent 正名 | 需要解释才能懂的自造词违反 §1 规则6；LLM 决策单元直接叫 agent（Mastra/Agno/Anthropic 行业标准词）；决策体共享层归 `app/agents/`（ADR-039 四分）；`SkillEntry.kind`（skill/tool 值）字段不存在。能力层定词与 LLM 禁 import 铁律的现行形态见 N-42 | §1 |
| N-30 | Agent 归一：一个 Agent 类 + 声明实例 | 10 个 `xxx_agent` 类的真实差异只有 prompt 模板 / 输出 schema / 调用配置——**多样性是数据不是代码**。`agents/base.py` 一个 Agent 类（harness 漏斗：装配→渲染→调用→校验→修复一轮→计量→声明兜底）；工具私有声明住工具包，共享 crew（director/persona/translator）住 `agents/registry.py`；特殊子类仅流式。领域逻辑归 schema 校验 / 工具包工序（ClipPlans 时长钳制本已在 schema） | §1 |
| N-36 | asset scope 会话退役：ChatModal / AssetChatModal 删除，产物对话归 dock + 焦点注入 | 会话只剩 project scope——`ChatRequest.asset_id/asset_type` 删除（extra=forbid，旧调用 422），`Conversation.asset_id` 列留给历史行、新行恒 NULL；产物指认两通道 = @output mention（注册表参考族，确定性 id）+ 旧 `focus_output` 已写退役，仅由 FocusRow 读回历史消息，不再每轮携带或新增写入；LLM 失败的 revise_script 猜测兜底不存在——ask 反问是唯一失败形态（禁令 #7） | §1、ADR-041 D8 |
| N-45 | pending_brief | 保留数据库字段名及其既有数据。当前任务由用户请求、作品和选择确定。 | §2 |
| N-48 | harness 单义 = 调用面 Agent 漏斗；测试入口 = 核心测试 / 用户旅程矩阵 | harness 只指调用面漏斗（`agents/base.py` + contexts 装配 + prompts）；真实用户测试叫**用户旅程矩阵**（`test/journeys/chat.py` / `JOURNEYS`），确定性合同测试叫**核心测试**（`test/core`）。harness 只保留调用面含义，不为测试脚本另立产品概念。pytest/vitest 的 test suite 仍是正常工程词，不在此禁令内 | §1 |
| N-50 | 文字问 / 选项问 | 文字问在对话中回答，带选项的问题可在 QuestionDock 点选。答案与原问题 ID 对应。 | §2 |
| N-51 | 积分词汇批：credit / wallet / credit_transactions / hold→capture→release / grant / purchase / payment；settle / claim / pay / ledger 表名 / entry 永禁 | 积分系统命名（ADR-055，行业坐标 = Stripe authorize→capture→release / Modern Treasury ledger transactions）：**credit**（积分 = 用户面唯一计价单位）；**wallet**（余额 + 判定）；**credit_transactions**（台账行——ledger 保留为子系统概念名不上表名，行 = transaction，entry 是双 entry 会计第三层用不到）；扣费时序 **hold → capture → release**（预扣 → 实扣 → 释放剩余——settle 是银行间清算语境、claim 是用户发起的收款动作方向相反，均禁）；**grant**（授予：开户 / 订阅周期 / 补偿）/ **purchase**（购买，支付订单入账）/ **payment**（名词位；pay 是动词只留函数名）；比例参数 `credits.per_cost_usd`（消耗比例 ≠ 购买比例） | §1 |
| N-59 | 精确编辑与授权 | 原生编辑按 base_ref 形成不可变版本，成片按原 Output 和摘要审阅。媒体和导出各有独立费用准入。 | §2.1 |

## 4. API 命名

- REST，复数资源，动作用子路径：`POST /outputs/{id}/poster`。
- 不为单个动作造 RPC 式端点（`/api/sendChat` 此类永不出现）。
- 内部类型（如 `material_understanding` / `storyboard`）不得从任何公开响应漏出——统一经 `visible_outputs_stmt()` 过滤（ADR-030 D1）。

## 5. 命名审计触发点

以下情况必须做命名审计并在当前任务合同中列出结论：

- 新模块 / 新表 / 新工具 / 新指令包准入（§1 规则7/8）；
- 大规模重构（命名审计结论随当前合同维护，不另建重构简报）；
- 发现同名不同物（如 `routers/intent.py` vs `agents/intent.py`）或同物不同名（如 `music.py` / `music_generation.py` 的职责切分）。
