# Verification — 测试政策、核心覆盖与当前验收

> Status: 当前规范（2026-11-10）。本文是测试运行纪律、核心合同↔测试映射与跨模块验收的唯一母文档；排期仍归 PROGRESS。测试/文档退役不是产品验收通过，绿色历史标记不等于当前 HEAD 或真实旅程已通过。
>
> 视频验收见 [统一视频合同](tasks/skill-package-promo-video.md)。覆盖 Composition 版本、时间与 video-spec，以及共享权限、授权、计费、执行身份与消息回放。保留开放项及其验收条件。

关键帧编辑验收分别核对版本写入、完整受影响运动和真实模型判断。恢复验收从导出成功的持久边界中断进程，核对同 opening 的实际调用、版本、Job、账本与交付卡。[I7 已验证范围](tasks/agent-editor-evidence/iteration-7/README.md)

## 1. 测试运行政策

### 1.1 当前资产边界

只保留两类测试资产：

1. **用户主流程旅程矩阵**：`apps/api/test/journeys/chat.py` 的当前 `JOURNEYS` 注册表。各种用户经普通 HTTP Chat 多轮完成创作、修订与交付；文档不复制固定数量或编号。
2. **核心 API/DB 确定性测试**：`apps/api/test/core/`，覆盖支付、上传、工具协议、权限、计费、作品数据、执行与交付等用户直接依赖的合同。

内部 helper、提示词文案、实现形态、重复 ToolLoop 机制和事故编号不另立永久测试。同一用户行为已有真实旅程证明时，不复制内部锁；重构使测试失去合同依据时逐案删除，不留注释尸体。

### 1.2 当前验证层

- 核心测试：`cd apps/api && uv run --extra dev python -m pytest test/core -q`。不调用真实模型、不执行付费制作；事务测试使用独立临时 PostgreSQL 数据库。
- 真实旅程：`cd apps/api && uv run python test/journeys/chat.py`，或用 `--only <name>[,<name>]` 选择当前注册表子集。需要活 API、当前 migration、fresh dev worker 和模型配额；制作媒体的旅程须单独明确授权。
- Web 按改动面运行 vitest 与 TypeScript 检查。旅程只锁用户可见结果及服务端/数据库真值，不锁 LLM 文案；打字机、remount、布局与最终视听仍归 Web 检查和真实 UI 验收。
- 诊断脚本不是部署门禁，读数不能替代核心测试、真实旅程或人工验收，也不能为放行调整断言。

### 1.3 Fixture 与 flake 处置

- 剧本素材先复制到 `scenario/` 前缀；项目删除会 unlink 外部共享 key，禁止直接引用营销或用户资产。
- fixture 必须显式建立被测状态；常驻 worker 的时序不得定义剧本语义。手工 run 前后清理数据；worker 代码新鲜度预检见 §1.4。
- 断言只锁形态；红先归因机制。可用 pre-批面复跑、固定输入重复采样和失败签名频率区分回归、既有弱点与发射方差，禁止调断言放行。
- 连续出现同类方差时登记 PROGRESS，保留原始输出、工具调用和应用处理证据，不静默重试到绿。

#### 已知方差与覆盖边界

- 真实旅程的模型输出方差是开放观察项，不自动放大为新的 release regression；每次仍需在当前 HEAD 按当前旅程名称归因。
- 以下风险目前没有完整活旅程自动化看护：计费失败、孤儿 hold 回收、Job 执行权仲裁、turn durability、SSE 断流复连、repair 静默/泄漏。相关纯函数覆盖不能冒充全链覆盖；是否补入矩阵须按用户旅程归属评估。

### 1.4 运行纪律

- **进程卫生**：`uv run` 包装器被 kill 可能留下孤儿 worker；手工 harness 使用 `start_new_session` + `killpg`，结束时核对实际进程。
- **dev 退出自动重启**：`scripts/dev.sh` 为 API、worker、render、Web 各持一个 supervisor，服务退出后间隔 2 秒重启；再次启动先经 `$TMPDIR/repurposer-dev-supervisors/` 清理旧 supervisor，再清理服务家族，避免旧进程复活成双实例。日志只在整栈启动时截断，单次自动重启继续追加。supervisor 只处理进程退出，**不是代码热加载**；修改 worker 消费的代码后仍须按上条在无活跃任务时重启 worker。
- **live / 付费预检**：同时核对服务健康、进程加载的代码新鲜度和当前 schema/migration；修改 worker 消费的代码后必须重启 worker。进程“在运行”不证明它已加载当前代码，未取得根因前不得重复付费重试。
- **证据分级**：函数调用、state updater 已调度、React 已 commit、内容用户可见、ACK/状态已持久化、MediaJob / ExportJob 终态、delivery 可见与媒体可播放是不同事实。DTO/HTTP 200 只证明其响应层级；每个验收结论必须对应实际取得的证据，旧自动门结果不得写成当前 HEAD 证据。
- **归因先行**：一条假设只配一个能证伪它的实验。两个独立实验仍未推进归因，就停止新建业务版本、浏览器探针或付费执行，回到真实 payload 与代码状态链；不得为探针机械创建新版本，也不得在未证明机制相关时调整实现顺序。
- **配额**：全量真实旅程可能产生显著模型费用；合并改动后一次跑，所有真实模型 HTTP 计入预算，warmup 默认关闭。付费运行需明确授权。
- **探针采样**：需要比较 provider/prompt 时采用 round-robin，避免顺序批把 provider 漂移误判为改动效果；保留原始读数。
- **scratch 边界**：根 `/scratch/` 是本机工作区，已整体加入 `.gitignore`，不纳入版本库。一次性探针、HTML 原型、原始响应、帧图、音视频和验收证据可以留在这里；文档中的此类路径只表示取证位置，不是新克隆必有的运行输入。现行规则、开放事项和验收步骤必须在正式文档中自足，不能只剩 scratch 链接。
- **升编**：可复用工具一旦被现行验收步骤或部署仪式引用，就应迁入受维护的 `test/` 或 `scripts/` 位置；历史决策中的原型与证据指针不等于正式工具。不要长期让关键验收依赖一次性目录。
- **文档**：当前注册表、命令和已知限制就地更新；不保存历史测试输出、调用量日志或旧矩阵副本。
### 1.5 合同迁移原则

1. **Tests protect contracts, not historical implementations.** 测试锁的是
   合同，不是某个历史实现形态；实现替换时测试按合同重审，不按代码怀旧。
2. **Contract migration requires intentional product/architecture change.**
   测试迁移的唯一合法理由是合同被有意变更（有 ADR / 用户拍板）；**永不**
   为了让当前实现变绿而削弱断言。「base 同样失败」不自动等于「测试该留
   失败」，也不自动等于「测试该删」——先裁决合同，再动测试。
3. **Scenario fixtures must explicitly establish the state under test.**
   剧本前置条件由 fixture 显式声明，background worker 的 timing / race
   永不定义剧本语义（fixture 纪律见 `docs/VERIFICATION.md`
   §1.3/§1.4 与 `test/journeys/chat.py` 头部）。

### 1.6 按身份核对实际模型请求

MiniMax 与 DeepSeek 共用 `app/providers/llm/trace.py`；`LLM_TRACE_PATH` 指向受控本地 JSONL 文件，旧 `MINIMAX_JOURNEY_TRACE` 环境名继续作为配置别名，未配置时不保存正文。请求在 transport 前记录实际发送的完整 payload，包括 messages、tools 与参数；响应在 schema/工具 JSON 参数解析前记录完整内容，流式工具调用保存未截断、未解析的原始 `arguments` 字符串。每次模型请求/响应/异常以 `model_call_id` 关联，普通 Chat、回答续聊与 trigger 携带 `project_id`、`conversation_id`、`turn_id`。标准日志的 `model_request_started/finished` 给出身份、trace 路径、输入清单、usage 与终态；详细提示词、工具 schema、逐条上下文、实际请求和原始响应归 JSONL，不在普通日志重复打印正文。凭据脱敏、签名 URL query 脱敏，inline 媒体以 digest 与本地 binary_ref 保留，不声明 trace 是未脱敏 HTTP 抓包。

从 `apps/api` 执行：

```sh
uv run python scripts/inspect_model_trace.py --id <project/conversation/turn/model-call UUID> --out ../../artifacts/model-traces/<id>
```

可用 `--trace <jsonl路径>` 指定记录。导出只读，不调用模型、不重新发送 Chat、不修改作品。旧记录缺少 project_id 时，仅通过既有 conversations 表解析 project → conversation；每个调用导出 request/response/error、完整 message 文本、各 tool schema、inventory 与总索引。没有响应记录写 pending，不将其等同于进程仍在执行；项目终态仍须读 opening 与 Job。

首次模型请求前的静态 Skill 文件装配记录 `initial_chat_dependency_started/completed/interrupted`，带 project/conversation/turn 身份、读取名、状态和耗时；不执行长耗时采集、不冒充模型工具活动。素材准备归普通 ToolLoop：首轮模型先发言并调用工具，等待明确结果后才请求下一轮；取消不继续。首轮上下文保留根方法/索引/模板原文，实际图片随准备工具结果交付。基础层回归比较完整共享来源及哈希，不设提示词长度目标。

请求的 `assembly` 记录 Agent、ToolLoop 迭代序号、实际执行到的 Jinja root/include 路径、完整源码及 SHA256，系统提示在声明时渲染的源码随其最终字符串保留，不在发送时用磁盘新文件覆盖。条件分支未执行的 include 不列入来源，缓存命中也记录。普通 Chat 另记本轮 message 分区、拒绝候选的完整参数/结构化错误、候选是否真的出现在发送消息中、已成功读取与本轮折叠/保留的 call id。诊断信息不注入模型输入，不改变提示词正文或工具执行。

导出同时生成每个调用的 `assembly.json`、来源模板文件与相邻请求的 `messages-diff.patch`。这些差异基于实际存下来的 messages，包括最新反馈、公共资源和工具协议对，不凭日志摘要推断。旧 trace 没有来源清单时明确标为 unavailable，只提供原始渲染文本，不追认当前源码为历史输入。Skill 按需读取的路径/digest/正文仍在相应工具结果中，非文件系统数据不伪造为 Jinja 来源。

跨回合 context 验收：检查请求 assembly.conversation_context 的 retained_ids、omitted 原因、媒体未附带记录及预算；对照 Conversation.context 中原始调用、规范化执行参数、完整结果与源 Turn。目录本身有界，omitted_catalog_truncated=true 表示还有未列出的历史条目。当前 Turn 的结果只出现在 tail，不能又从历史恢复一次。两回合连续性、实例重建、取消/失败、锁与并发、媒体和权限须由当前核心测试或真实多轮旅程取得证据，不引用已删除的内部上下文套件。


数值兼容的 `arguments_normalized` 记录与原始 request/response 使用同一 model_call_id，并记录 tool_call_id、实际字段路径、原始字符串和转换数值；inspect_model_trace 索引展示转换表，不覆盖原始响应。转换发生在历史包装解包后及参数模型校验中；原始 wire 始终留在原始 response，业务校验仍决定可否执行。

输入清单逐消息、逐工具记录 compact JSON 字符数、UTF-8 字节数与 SHA256，正文另列文本字符数和媒体 part 类型。新记录清单在媒体替换/脱敏前计算，旧记录只能按存下来的内容重算；索引明确区分。provider 的 `prompt_tokens` 是实际总读数，各区段只有字符/字节精确值，未获得 provider 分项 tokenizer 时不得按比例宣称精确 tokens。二进制、工具 schema 与消息封装开销不能冒充普通文本。请求详情可能含业务内容，沿用本地诊断产物管理，不上传为公开页面。

## 2. 核心合同 ↔ 当前测试映射

旅程名称只以 `test/journeys/chat.py` 的 `JOURNEYS` 注册表为准；下表不声明未运行项已通过。核心文件可以按领域拆分或合并，但不另建第二注册表。

| 用户依赖的合同 | 核心测试座 | 真实旅程 / 额外证据 |
|:---|:---|:---|
| 应用组合根可启动 | `test/core/test_app_boot.py` | 活 API 健康检查与真实请求 |
| 支付、积分、计量与报价 | `test_payments.py` / `test_metering.py` / `test_pricing.py` | `credits_boundary`；真实 webhook、费用确认与钱包台账 |
| 执行身份、交付、渲染归属与产物检查 | `test_export_stop_races.py` / `test_project_job_deletion.py` / `test_delivery.py` / `test_render_probe.py` / `test_output_checks.py` / `test_staging.py` | 明确授权的制作旅程；worker 恢复、上传重试与真实媒体 |
| 上传、媒体准备与导入 | `test_media_preparation.py` / `test_media_import.py` / `test_web_capture.py` | `material_to_clips` / `remix`；真实上传进度、失败与删除 |
| 内置与外部 Skill、包权限和读取边界 | `test_skill_store.py` / `test_skill_packages.py` / `test_skill_catalog.py` | `builtin_promo_skill` / `external_skill`；恶意包与真实 Skill 多轮对话 |
| Composition、版本、预览与 video-spec | `test_compositions.py` / `test_previews.py` / `test_video_spec.py` / `test_generator.py` | `temporal_revision` / `builtin_promo_skill`；浏览器预览、Scrub 与最终视听 |
| Provider 工具协议与原始 trace | `test_provider_tools.py` | 各真实旅程的完整工具调用与 `inspect_model_trace.py` 取证 |
| 官网证据、Brief、BrandProfile、集中问题组与 CreativeState | `test_website_promo_readiness.py` / `test_website_promo_wire.py` / `test_question_groups.py` / `test_compositions.py` | fake provider golden wire 与临时 PostgreSQL；真实模型、真实 LegitEvi 网页及连续视听另行授权 |

真实旅程注册表还覆盖迷失用户、探索、无素材写作、研究、咨询、修订、访谈、时间编辑与能力拒绝等主流程。新增旅程必须来自真实用户需求；新增核心测试必须能指出其保护的用户合同，不能仅为内部实现形态提高覆盖率。

## 3. Job 与费用

检查原授权、所有者、实际 Job、钱包预占与最终 capture/release。Stop 与外部副作用按先提交的事务裁定。API/Worker 强杀、双 Worker、待核对和项目删除必须在真实隔离 PostgreSQL 中验证。

## 4. 未闭环验收与实现差异

本节只维护剩余检查、实现差异与证据要求；产品规则分别归 CHAT_ARCHITECTURE、BILLING 与现行 ADR。下面各项仍待运行/核对，不继承 §2 的绿色符号作为 live 通过证明。按改动运行 `test/core`、当前 `JOURNEYS` 与 Web 测试/tsc/build；付费检查遵循既有预算授权。

### 4.1 选项唯一座位

按实际 Chat 检查原问题身份、组内答案、批准与拒绝、报价、持久回执和硬刷新。来源准备、Brief、媒体和成片的验收分别记录到对应项目。6D 对真实进程和用户请求的检查见 [6D 验收](tasks/agent-editor-evidence/iteration-6/6d-acceptance.md)。

### 4.2 授权、会话计量与配置

Canonical：CHAT_ARCHITECTURE §3.1，BILLING §6.5/§7，ADR-117/139；Video 首稿按 VIDEO_PROJECT 的呈现与授权合同。

- 设置读写覆盖缺席/非法值/部分键/同会话生效，确认控件只在 Settings「助手」，composer/dock 不出现偏好开关。
- auto/ask × quote=0/正价 × 守卫线 × NULL × 有无制作意图：服务端矩阵与真实 Chat 各覆盖代表路径；在原生调用与回答费用问题两条入口验证确切操作、报价和授权范围。
- 真实回合检查 conversation_usage：每回合一行，tokens/cache/cost/model/project 归属正确，多迭代聚合、无调用空回合零行、记录失败不打断回复；永不上用户账单/UI，不替代 agent_calls。
- context 窗口边界与世界状态幸存需要核心覆盖；预算是否调整由真实 usage 分布决定，保持 prefix-cache 稳定顺序，滚动摘要不能代替溢出证据。
- 费用四面同源、NULL/守卫线文案诚实，积分余额/冻结/台账一致；工作段、Dock 两形态、打字机与信封权威不回退。
- 查询目标环境的 configs 旧 key billing.confirm_large_threshold，按已授权范围清理真实残留并记录执行状态；旧 confirm_strategy 不新增兼容语义。本次未查/改目标 DB，也未运行以上仪式链或 live 检查。

### 4.3 素材理解与对话回放

Canonical：CHAT_ARCHITECTURE §3.5/§8，ADR-102/113。

- 当前素材/咨询旅程、相关核心测试与 Web 检查仍待完成；不恢复 material-wait 事故套件。
- live：① 寒暄/能力问答零 worker 事件与素材处理；② 视频提问出现真实 read-active，等待实际 ASR 后同回合 grounded answer/诚实失败；③ 同素材追问 digest 命中、零等待。
- ④ 硬刷新每条 opening/user message 恰好出现一次，不丢不重；⑤ 无素材读取问题的上传不产生处理活动或虚假叙事；⑥ 素材读取回合只有一个 read Activity 生命周期，回答有依据，不逐资产重复叙事。
- worker 停摆导致无限等待仍是登记风险；超时/取消/降级不在本整理批擅改。ASR GPU/云加速为独立运营评估，不作为本验收完成项。

## 5. 共享机制与 UI 的当前验收

这些检查尚未闭环，不继承旧批次完成状态。旧 task 的过程、固定事故项目与旧数据救援工单不再是新架构施工前置；仍需的行为合同在各母文档/ADR，下面只登记当下验收和未定事项。

### 5.1 导出与交付

核对确切预览、ExportJob 所钉版本、Renderer 生成的 MP4、Output 字节摘要、Agent 审阅及交付消息。实际播放与下载在 Chrome 硬刷新后分别检查。多版本、多用户与恢复使用原 Job 和消息身份。

### 5.4 素材卡、Transcript 与精确编辑边界

Canonical：ADR-113/115、UI_GUIDELINES、VIDEO_EDITOR。源 transcript/extracted_text 与 edited_transcript overlay 分开，words/timestamps 不可变；cues 只读派生；资产 GET/PUT transcript 零 run/积分，无 graph JSON 双写，不冒充 ASR 时间戳。

待验：StageSkin/视频轴/cue seek/cross-highlight 与真实源区间一致，overlay 时隐藏不可靠时间皮，恢复原文后回归；NLE_AXIS_PX=116 与镜像常数、26px modifier lane、port/handles 同步；不同旧尺寸与现有布局不溢出，深浅主题、medialess/粘贴资产诚实，L0 常驻/L1 HoverChip/L2 inspector 不藏结构。刷新后 overlay 与时间轴/锚一致。初始 fixture 的 48 cues/5:40 badge、2:59–3:45 clip 与六字幕块只是可替换的具体检视样例，不要求保留某个事故项目。

未实施：edited-transcript 驱动 re-cut、overlay 进入 Operation Model、粘贴估算词轴、drag-select、modifier-lane 内容面/port、竖屏折叠；无新批准不扩首批范围。

### 5.5 消息数组、Checkpoint 与 Candidate Surface

Canonical：CHAT_ARCHITECTURE §8、ADR-108/109/110。seq 可有间隙；首回合与 conversation 同事务分配，后续用独立计数器短事务。append 定位/update 原位，禁止时间戳重排；cancelled 留审计但不显示，failed 诚实告警，零 delta 走 settled/typewriter。

待裁决：candidates_log 聚合行是正式例外还是改细粒度行；不得默许豁免或为数组化破坏单卡 repaint。不增查询端点。覆盖 set/同集重发/selection/revise/失败/answer-turn 六类载荷的 live/replay 顺序、幂等/替换、selection 无空行、失败回滚与持久化一致、跨轮重选。event/sync 无 Activity 只作 parity 观察，不自动扩需求。

Checkpoint 五路承重覆盖：非终态非空散文合法参数且有 channel 时 post-validation/pre-execute 发射且 execute 不重复；终态仅 settled；参数拒收不发/不执行/不留残片；无 channel 最终 envelope 不丢不重；cap=4 后记 capped 且不把截散文回灌 ledger。保留 tool_loop_checkpoint/tool_loop_checkpoint_capped 读数，结构性单读零 checkpoint 合法，不追数量。

fresh 首/后续 conversation 分别检查 FK/seq、刷新切 tab、WorkSegment 与 failed/cancelled；保留历史的环境才要求活动旧行迁移及回放证明。无用户 reset 路径不需要迁移事故项目。

### 5.6 活动和恢复

刷新读取原 opening 的消息与各工具独立回执。API 中断或双 Worker 的测试须核对唯一续行、版本、固定媒体、费用和交付次数。

### 5.7 现有 UI 自足与锚卡


真实 MediaLightbox 播放、跨 Home/Lightbox 声音互斥、离屏暂停所有权、copy/免责声明、双主题/无横溢、MentionEditor 不 remount、背景相机不动、WorkSegment 正确收口都未自动通过。交付正文始终只讲实际结果，不给界面引导或内部 ID。Home 真片状态只读 home-creation-entry-refresh；空货架/假 Queue/mic/反馈按钮不复活。
