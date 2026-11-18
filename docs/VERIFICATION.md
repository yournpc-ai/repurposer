# Verification — 测试政策、核心覆盖与当前验收

> Status: 当前规范（2026-11-10）。本文是测试运行纪律、核心合同↔测试映射与跨模块验收的唯一母文档；排期仍归 PROGRESS。测试/文档退役不是产品验收通过，绿色历史标记不等于当前 HEAD 或真实旅程已通过。
>
> 视频验收见 [统一视频合同](tasks/skill-package-promo-video.md)。覆盖 Composition 版本、时间与 video-spec，以及共享权限、授权、计费、执行身份与消息回放。保留开放项及其验收条件。

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
- 以下风险目前没有完整活旅程自动化看护：计费失败、孤儿 hold 回收、run 执行权仲裁、turn durability、SSE 断流复连、repair 静默/泄漏。相关纯函数覆盖不能冒充全链覆盖；是否补入矩阵须按用户旅程归属评估。
- 保留历史消息的环境，migrate_activity_log_rows.py 退役前仍须迁移与回放证明；本轮已授权 reset 的无用户环境可重建空数据，不承担旧行兼容回填。reset 未执行不等于旧行已清零。
- trigger `/event/sync` 无 Activity 行是 parity 观察，不自动等同于缺陷或新需求。

### 1.4 运行纪律

- **进程卫生**：`uv run` 包装器被 kill 可能留下孤儿 worker；手工 harness 使用 `start_new_session` + `killpg`，结束时核对实际进程。
- **dev 退出自动重启**：`scripts/dev.sh` 为 API、worker、render、Web 各持一个 supervisor，服务退出后间隔 2 秒重启；再次启动先经 `$TMPDIR/repurposer-dev-supervisors/` 清理旧 supervisor，再清理服务家族，避免旧进程复活成双实例。日志只在整栈启动时截断，单次自动重启继续追加。supervisor 只处理进程退出，**不是代码热加载**；修改 worker 消费的代码后仍须按上条在无活跃任务时重启 worker。
- **live / 付费预检**：同时核对服务健康、进程加载的代码新鲜度和当前 schema/migration；修改 worker 消费的代码后必须重启 worker。进程“在运行”不证明它已加载当前代码，未取得根因前不得重复付费重试。
- **证据分级**：函数调用、state updater 已调度、React 已 commit、内容用户可见、ACK/状态已持久化、Run terminal、delivery 可见与媒体可播放是不同事实。DTO/HTTP 200 只证明其响应层级；每个验收结论必须对应实际取得的证据，旧自动门结果不得写成当前 HEAD 证据。
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

可用 `--trace <jsonl路径>` 指定记录。导出只读，不调用模型、不重新发送 Chat、不修改作品。旧记录缺少 project_id 时，仅通过既有 conversations 表解析 project → conversation；每个调用导出 request/response/error、完整 message 文本、各 tool schema、inventory 与总索引。没有响应记录写 pending，不将其等同于进程仍在执行；项目终态仍须读 Turn/Run。

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
| 执行身份、交付、渲染归属与产物检查 | `test_execution_fencing.py` / `test_run_authority.py` / `test_delivery.py` / `test_render_ownership.py` / `test_render_probe.py` / `test_output_checks.py` / `test_staging.py` | 明确授权的制作旅程；worker 恢复、上传重试与真实媒体 |
| 上传、媒体准备与导入 | `test_media_preparation.py` / `test_media_import.py` / `test_web_capture.py` | `material_to_clips` / `remix`；真实上传进度、失败与删除 |
| 内置与外部 Skill、包权限和读取边界 | `test_skill_store.py` / `test_skill_packages.py` / `test_skill_catalog.py` | `builtin_promo_skill` / `external_skill`；恶意包与真实 Skill 多轮对话 |
| Composition、版本、预览与 video-spec | `test_compositions.py` / `test_previews.py` / `test_video_spec.py` / `test_generator.py` | `temporal_revision` / `builtin_promo_skill`；浏览器预览、Scrub 与最终视听 |
| Provider 工具协议与原始 trace | `test_provider_tools.py` | 各真实旅程的完整工具调用与 `inspect_model_trace.py` 取证 |
| 官网证据、Brief、BrandProfile、集中问题组与 CreativeState | `test_website_promo_readiness.py` / `test_website_promo_wire.py` / `test_question_groups.py` / `test_compositions.py` | fake provider golden wire 与临时 PostgreSQL；真实模型、真实 LegitEvi 网页及连续视听另行授权 |

真实旅程注册表还覆盖迷失用户、探索、无素材写作、研究、咨询、修订、访谈、时间编辑与能力拒绝等主流程。新增旅程必须来自真实用户需求；新增核心测试必须能指出其保护的用户合同，不能仅为内部实现形态提高覆盖率。

## 3. Charge Semantics 等价登记（ADR-063 终读）

**当前实现下 `charge_semantics_ready ≡ has_pending_plan`——这是当前合同
空间中的故意等价，不是测试缺失。**

- ADR-063：estimate 可 deferred（NULL estimate = 诚实 Deferred 披露面），收费语义随 pending plan 的 dock 即已完整披露，**estimate 完整性不阻塞 PLAN_READY**；`always_confirm_above` 触发独立费用确认；NULL 不可报价族仅在 execution=ask 或 credits=ask 时确认，auto/auto 不另设确认。
- 推论：`PLAN_READY=true ∧ charge_semantics_ready=false` 在当前产品实现中
  是**不可达状态**；四合取的 charge conjunct 不提供独立运行时分叉，其
  独立性由合同层保留（未来引入独立收费语义准备态时它才有牙）。
- 若未来要支持「Plan Ready + 费用语义未完整 + Canvas 可审阅 + Confirm
  disabled」：那是 **ADR-063 / ADR-087 的产品合同翻案**，不是普通 bug
  fix——先拍板再动代码，届时本条目与等价钉同批改写。
- 该等价是当前产品合同；若实现引入独立收费语义准备态，必须先修订上述 ADR，再调整核心测试与真实旅程。

## 4. 未闭环验收与实现差异

本节只维护剩余检查、实现差异与证据要求；产品规则分别归 CHAT_ARCHITECTURE、BILLING 与现行 ADR。下面各项仍待运行/核对，不继承 §2 的绿色符号作为 live 通过证明。按改动运行 `test/core`、当前 `JOURNEYS` 与 Web 测试/tsc/build；付费检查遵循既有预算授权。

### 4.1 选项唯一座位

Canonical：CHAT_ARCHITECTURE §8.5/§8.8，ADR-081/099/100/116。

- **实现差异待核对**：conversation_mode.j2 的小写字母选项 ID 指令与 check_options_dock 的数字语法覆盖须按 ADR-081 对账；本次未修改 prompt/守卫，不能宣称已修复。
- ADR-099 只保留三种现行终态形态与 trigger-only provenance；四层架构、交互宪法、Speech Commit Protocol 与默认吸收边界继续有效。NAMING 的 suggestion_ref/source_state 与终态形态须收窄到 trigger，不恢复 answer+suggestions。
- 自动检查至少包含 trigger 点击→下一回合编译、stale trigger 的具名原因、数字 id 与 1–5 结构外界、历史 answer replay 安全；这些检查归入当前核心合同或真实旅程，不恢复独立内部套件。
- live：浏览问题产生可用 dock（推荐、×/pencil 退出、合法且不外露宣告的 default path）；能力问答/闲聊只产纯 answer；有效 suggestion trigger 可 dock/点选/解算；历史 answer 硬刷新只读散文，无建议卡和崩溃。run_completed 不作为建议来源，使用 run_failed/craft_decompiled。

### 4.1.1 官网品牌宣传片基础链（Iteration 1A）

- fake provider golden wire 覆盖新 URL source_preparing、正文/PNG 就绪后的 briefing、缺失字段单组澄清、完整输入不重复提问、采集失败、非 website_promo 和普通“宣传片”不绑定固定 Skill；断言实际 System/User 顺序、工具白名单和 PNG media inputs，不断言模型文案。语言规则只住 System 顶层，user message 不重复注入。
- 当前定向检查：`test_website_promo_wire.py` 5 tests、`test_activity.py + test_previews.py` 26 tests、`test_projects.py` 1 test；另有 `test_question_groups.py` 与共享核心回归。Web 覆盖 QuestionDock 每页一问、自动前进、primary 选中态、勾选图标、整组一次提交和 QA 的 `option_id → option.label` 映射；TypeScript 通过。这里只记录实际运行的定向结果，不沿用历史全量计数。
- 授权纯函数已覆盖 auto/auto 的 NULL 估价不请求、execution=ask / credits=ask 的 NULL 请求，以及 auto/auto 超守卫线仍请求。Dock 与 Start gate 使用同一个 `requires_confirmation`，不再把 NULL 写成任何档必确认。
- 真实 LegitEvi 证据与 BrandProfile 已通过：实际 SourceSnapshot 和生产 `analyze_brand_seat` 形成包含 `#DC0000`（visual/inferred）、“接近 Inter”和原始宣言的档案。组跳过默认路径仍有效；数字选项整组提交另在项目 `655521c2-a0dd-46df-b8d8-cc85e77fbd17` 实测通过：preview/正式 digest 均为 `fd03d465…f395`，六槽在 PendingPlan 与 CreativeState 一致且均为 `user-stated`，target_seconds=30、subtitle_languages=[en]、aspect=16:9，其余文本槽保留所选标签；过期 digest/重复结算均 409，刷新后 pending=null，readiness 恢复 `design_video`。证据见 `scratch/website-promo-batch1-canonical-answers-20261117/`。
- 批 1 的验收终点是证据/BrandProfile、集中答案原子结算及本批状态刷新恢复；真实 trace 同时证明三组带图工具结果只完整送达一次，随后折叠。首稿写作、draft_repair、正式制作和 Iteration 2 媒体均属于尚未开始的后续迭代，不对其作通过/失败结论，不添加相关本批测试，也不将其问题列为批 1 阻塞。现有 answer 接口的自动续行发生在边界之外；本批未执行 produce_video 或真实 PNG/TTS 媒体生成。
- 本地开发库已确认 `h8e5a2c4d7f1 (head)`；生产 migration 与 migration 后恢复未验证。真实浏览器 full/panel/双主题/移动端和连续视听未运行。未提交选择只保证同标签 sessionStorage 刷新恢复，不跨设备同步；只有整组提交或跳过才调用 answer API。

### 4.1.2 官网宣传片 Iteration 2 上轮：语义分镜与双来源图片

- 已落码当前工作草稿的 N 幕 `SceneAssetSpec`、真实 scene_id 校验、显式 15 秒/两幕/24fps 约束、普通 plan/Start/Run 图片准备、逐幕缓存/attempt/恢复、受控 SVG 执行体、MiniMax submitted/unknown 保护、不可变 PNG SourceSnapshot、图片 MediaAnalysisReport 和独立 ContentReview。报告与 Snapshot 引用采用内容寻址存储，未新增主表/migration，未实现正式 ImageObject 绑定、CompositionVersion、音频/视频探针、Scene 渲染或 produce_video。
- 函数级 fake 定向曾实测 **20 passed, 1 deselected**：18 项本轮用例与 2 项既有模糊/完整入口 golden wire，覆盖 N=5 分批与局部失效、权限、Start/Stop、SVG 安全/digest、MiniMax fake cache/unknown/计量、分析与审阅身份、损坏媒体、fail/advisory 不重做及首次完整回模后折叠。新增函数级测试文件与驱动脚本已按要求删除，旧计数不再是当前可复验命令；新模块 ruff、命中 Python 文件 py_compile 和本轮 diff whitespace 检查通过。后续只从真实 Chat 输入验收。
- fake 证据边界：SVG 使用 fake deterministic rasterizer 后实际解码 PNG；MiniMax 使用 fake provider。函数/临时数据库测试中的 PNG、Snapshot 和报告不是任务 1/2 的真实出口，不能覆盖下面的真实失败。
- 2026-11-18 真实执行未通过。任务 1 项目 `dfe21df7-64be-472c-8eac-855f08477f61` 已在真实官网证据/BrandProfile 后出现六字段问题组，仍待真实用户作答。任务 2 项目 `80ad9110-354f-4ae8-aa91-1d2ec7b6aea2` 有 Brief、双来源 draft `a11262a79678…a885` 和真实 trace，但 visual Run `c34edab4…`、`3d854ec6…`、`8dd66899…`、`d7d86129…` 均失败，没有合格 SVG；最后的默认 Chromium 缺失已改为复用 `resolve_chrome_path()`，未重新验收。
- 目标项目 `0ff95f17-578d-4a15-94f6-3b89b1777d48` 的六字段 Dock 缺失已修为同时接受 options/items。当前 QuestionDock 每页恰好一问，选项点击自动前进，选中项使用 primary token 和右侧勾选图标，末页手动一次提交；QA 通过 `option_id → option.label` 显示人话。`QuestionDock.mount.test.tsx` 4 tests passed，历史时间线 46 tests passed，TypeScript 通过。真实 Chrome 复验显示 `1 / 6` 且首屏只有用途一项，无浏览器错误。该 UI 修复不改变下述媒体未通过结论。
- 两张实际 MiniMax PNG 为 Snapshot `44bb7a0e-d60b-5eec-bf1e-8dc1bb5e7f5d` / `6a129078…f3d1` 与 `bd1b079e-48f8-50c1-97d7-efac9f566167` / `956062ac…7141`。实际读图分别为小三角形、含文字且缺方向连接/引用回环，内容均不合格；当时 ContentReview 均为 `unavailable`（schema 拒收），不是 pass。按现有美元分项核算，真实用量费用合计 **USD 0.651669**：任务 1 USD 0.027243、任务 2 会话 USD 0.617426、MiniMax 图片固定费用 USD 0.007；审阅 step 的 tokens 有记录但未单列美元金额。大量恢复和直接执行属过度工作。地基未复核通过，不得进入中轮。

### 4.1.3 官网宣传片 Iteration 2 第二轮：Narration、BGM 与波形

- 当前仅有代码实现：分镜绑定原速 TTS、READY Alignment/cues、单幕重定时、ScoreSpec/NumPy 电子合成、私有 Music/Snapshot、authored BeatGrid、音频 MediaAnalysisReport 和持久化波形播放。
- 用户明确要求本轮不测试；未运行核心/API/Web/浏览器检查，未调用真实 TTS 或 Music，未形成任务 1/2 音频出口。第一轮真实图片失败仍是独立缺口，不由代码或 fake 证据抵消。

- 一次集中作答后的自主验收以 [Iteration 2 子合同 §0](tasks/website-promo-iteration2-media-slice.md#0-目标任务与迭代纪律) 为准。项目 `7dd2a1f1-75ea-4b21-8525-c0881d4f4e73` 的真实 Chat 诊断经人工 Start 取得两张 PNG（Run `be93f484-06ad-4efe-8467-e7150eaff0e0`），SVG 技术通过但内容审阅不可用，MiniMax 内容失败。随后有人为恢复提示，计划 Start 返回 422，未创建新的 Run。该诊断明确计为自主旅程失败。
- 图片计划改为按 draft_ref 和 scene_ids 解析服务器规格，保存旧计划兼容。补审复用固定 PNG、Snapshot 和媒体分析，只保存新报告。针对性图片恢复和官网入口 wire 共 6 项通过。未重跑真实 Chat 或 provider，未验证自动 Start/结算续行、验收停点、第二轮真实音频或后续成片。

- 项目 `9cba6a15-79b0-4a13-b922-f953279fbc30` 在一次作答后自动启动图片 Run `8b643ee7-cf52-4c2e-ad25-c22f1620349b`。五张 PNG 均可解码，但 XML 命名空间前缀在 HTML 内联时令 SVG 排版和图形丢失；四幕正式审阅失败，第三幕因审阅回包字段不合规而不可用。新增原生 SVG 视口与 PNG 尺寸验证，旧版 SVG 缓存重新光栅化，其他来源保留固定图。五份原始 SVG 均经本地 Chromium 复验，恢复原布局。图片恢复与官网入口定向检查共 9 项通过。未从 Chat 重启旅程，未调用真实审阅或其他 provider，未进入音频。

- 项目 `36d9b2b5-f10e-4e72-a391-172c57b25145` 的失败已纳入定向回归。图片探测的确切任务由服务端交给既有计划、报价与授权检查。计划被拒后留在当前阶段，Run 的结算事件沿原始制作请求续行。图片未通过时禁止进入音频，当前实现止于音频，正式保存与渲染留到后续轮次。图片恢复、官网入口与续行定向检查共 14 项通过，覆盖工具门与重复结算，尚无真实自主音频出口或浏览器试听证据。

- 项目 `029cdef6-70d3-4674-a120-d995764e5229` 已验证自动启动，原 Run 在第三幕 SVG 重复 `rx` 处失败。修复后逐幕预检、批次保留成功与失败结果、未知供应商结果的只读恢复、结算续行和 SVG 字幕区几何均纳入定向测试。本次未提交真实 Chat，未执行音频或成片。

### 4.2 授权、会话计量与配置

Canonical：CHAT_ARCHITECTURE §3.1，BILLING §6.5/§7，ADR-117/139；Video 首稿按 VIDEO_PROJECT 的呈现与授权合同。

- 设置读写覆盖缺席/非法值/部分键/同会话生效，确认控件只在 Settings「助手」，composer/dock 不出现偏好开关。
- auto/ask × quote=0/正价 × 守卫线 × NULL × 有无制作意图：服务端矩阵与真实 Chat 各覆盖代表路径；dock Start、口头/typed answer 共用 gate，Video 首稿不得同回合开工，confirmed_via/scope 证明真实。
- 真实回合检查 conversation_usage：每回合一行，tokens/cache/cost/model/project 归属正确，多迭代聚合、无调用空回合零行、记录失败不打断回复；永不上用户账单/UI，不替代 agent_calls。
- context 窗口边界与世界状态幸存需要核心覆盖；预算是否调整由真实 usage 分布决定，保持 prefix-cache 稳定顺序，滚动摘要不能代替溢出证据。
- 费用四面同源、NULL/守卫线文案诚实，积分余额/冻结/台账一致；工作段、Dock 两形态、打字机与信封权威不回退。
- 查询目标环境的 configs 旧 key billing.confirm_large_threshold，按已授权范围清理真实残留并记录执行状态；旧 confirm_strategy 不新增兼容语义。本次未查/改目标 DB，也未运行以上仪式链或 live 检查。

### 4.3 素材理解与对话回放

Canonical：CHAT_ARCHITECTURE §3.5/§8，ADR-102/113。

- 当前素材/咨询旅程、相关核心测试与 Web 检查仍待完成；不恢复 material-wait 事故套件。
- live：① 寒暄/能力问答零 worker 事件与素材处理；② 视频提问出现真实 read-active，等待实际 ASR 后同回合 grounded answer/诚实失败；③ 同素材追问 digest 命中、零等待。
- ④ 硬刷新每条 opening/user message 恰好出现一次，不丢不重；⑤ 无素材读取问题的上传不产生处理活动或虚假叙事；⑥ 素材读取回合只有一个 read Activity 生命周期，回答有依据，不逐资产重复叙事。
- ⑦ ask_user 不可见/散文宣告 default-path，不复读内部法条；⑧ in-flight beat 被抑制时，无 in-flight 的合法 run-birth beat 仍可出现；⑨ read/plan 都没有独立 transcript 节点/卡，资产卡只反映真实状态。
- worker 停摆导致无限等待仍是登记风险；超时/取消/降级不在本整理批擅改。ASR GPU/云加速为独立运营评估，不作为本验收完成项。

## 5. 共享机制与 UI 的当前验收

这些检查尚未闭环，不继承旧批次完成状态。旧 task 的过程、固定事故项目与旧数据救援工单不再是新架构施工前置；仍需的行为合同在各母文档/ADR，下面只登记当下验收和未定事项。

### 5.1 Render ownership 与恢复

Canonical：RENDERING、ADR-096。静态 owner/屏障包含同 output 全部写者；非 owner 失败不得交付部分 spec，track 局部原子写和完整 ClipSpec 校验继续有效，reconcile 不替代正常 compiler/runner。

待验：owner/其他写者启动及完成的两种顺序、写者失败阻断、屏障等待中取消、run 恢复不重复执行、fork owner 只等自己的写者；并发不同 track 不丢更新、同 track 冲突有诊断、联合约束复校；空/缺文件、spec 版本失配、归档或跨 run 在飞渲染不误认领。真实 worker/live 与纯测试证据分开。

无实际用户环境不再要求恢复特定历史 dev 产物；该操作工单退出，不记“已恢复”，也不把一次性裸 SQL 修复推广为正常路径。

### 5.2 Product artifact 身份

Canonical：ADR-097、MODULE_ARCHITECTURE。work_key/artifact_key/artifact_name/artifact_role 与 fill_key 独立；is_product_node 与 role 分层，无 key 为 unknown；名称按 ADR-058 手改撤名。成员不能从 rank/邻接/时间戳/共享 output/fill_key 猜出，display lineage 不参与调度/stale 闭包。

待验：fresh 视频→金句短片只有真实目标交付卡与 companion，transcript 在资产卡；同 output 只属一张交付卡、fork 独立、archive 可追溯、每 artifact 至多一个 activity owner；改变 rank/边序等不改成员；transcript overlay 不因 display 边错误失效。readiness 术语须有真实事实。跨产物 product_artifact/artifact_version 表是 OPEN，不能与 Composition 同期默认建另一套作品层。

### 5.3 Product graph、staging 与可选 Canvas

Canonical：ADR-086/098/113、CHAT_ARCHITECTURE §5。fresh graph 禁 task_book/transcript/纯执行节点；rank 唯一，lineage/ctx 不参与 rank 与 RunOp，布局不能影响执行；effective/display 只读，settled-rank freeze、append-only 与 source→target reveal 顺序保留。

待验：多文件上传/真实进度/失败重试/删除/attach 阻塞、PUT 成功未 attach 的 TTL 回收且不删已引用 key；fresh 图资产/产物身份一致；恶意反向 frame 不改 RunOp 拓扑与隐藏 modifier 顺序；server display_ranks 与前端投影同 fixture 同数、单成员 cohort 无幽灵 corridor、并行 writer/新增成员不移动旧卡、素材删除 reflow 为具名后果；背景 refetch 不动相机。移动端纯 Chat、深浅主题与真实 Start 都要验证。

空 frame 出生保障、缺帧 dev 失败/prod rank 回退、按 rank reveal/reduced-motion、同族分组/长边/settled 居中仅为后续需求，不把旧 C-3/Batch D 当成新视频前置。禁止服务端逐节点 drip-feed、第二 rank 或为排线造语义节点。

### 5.4 素材卡、Transcript 与精确编辑边界

Canonical：ADR-113/115、UI_GUIDELINES、VIDEO_EDITOR。源 transcript/extracted_text 与 edited_transcript overlay 分开，words/timestamps 不可变；cues 只读派生；资产 GET/PUT transcript 零 run/积分，无 graph JSON 双写，不冒充 ASR 时间戳。

待验：StageSkin/视频轴/cue seek/cross-highlight 与真实源区间一致，overlay 时隐藏不可靠时间皮，恢复原文后回归；NLE_AXIS_PX=116 与镜像常数、26px modifier lane、port/handles 同步；不同旧尺寸与现有布局不溢出，深浅主题、medialess/粘贴资产诚实，L0 常驻/L1 HoverChip/L2 inspector 不藏结构。刷新后 overlay 与时间轴/锚一致。初始 fixture 的 48 cues/5:40 badge、2:59–3:45 clip 与六字幕块只是可替换的具体检视样例，不要求保留某个事故项目。

未实施：edited-transcript 驱动 re-cut、overlay 进入 Operation Model、粘贴估算词轴、drag-select、modifier-lane 内容面/port、竖屏折叠；无新批准不扩首批范围。

### 5.5 消息数组、Checkpoint 与 Candidate Surface

Canonical：CHAT_ARCHITECTURE §8、ADR-108/109/110。seq 可有间隙；首回合与 conversation 同事务分配，后续用独立计数器短事务。append 定位/update 原位，禁止时间戳重排；cancelled 留审计但不显示，failed 诚实告警，零 delta 走 settled/typewriter。

待裁决：candidates_log 聚合行是正式例外还是改细粒度行；不得默许豁免或为数组化破坏单卡 repaint。不增查询端点。覆盖 set/同集重发/selection/revise/失败/answer-turn 六类载荷的 live/replay 顺序、幂等/替换、selection 无空行、失败回滚与持久化一致、跨轮重选。event/sync 无 Activity 只作 parity 观察，不自动扩需求。

Checkpoint 五路承重覆盖：非终态非空散文合法参数且有 channel 时 post-validation/pre-execute 发射且 execute 不重复；终态仅 settled；参数拒收不发/不执行/不留残片；无 channel 最终 envelope 不丢不重；cap=4 后记 capped 且不把截散文回灌 ledger。保留 tool_loop_checkpoint/tool_loop_checkpoint_capped 读数，结构性单读零 checkpoint 合法，不追数量。

fresh 首/后续 conversation 分别检查 FK/seq、刷新切 tab、WorkSegment 与 failed/cancelled；保留历史的环境才要求活动旧行迁移及回放证明。无用户 reset 路径不需要迁移事故项目。

### 5.6 Lifecycle 与后续 hygiene

Canonical：ADR-087/089/117/139。待验 derived/reasons、PLAN_READY≠CONFIRMATION_READY、missing stamp=unknown、估价完整性非 PLAN_READY 前置；/generate 的历史 context.tasks 不得在无有效 confirmed/approved provenance 时充当授权，生产暴露尚未核实，需修实现或明确重裁。

scope 不可证保持 unproven；targeted tasks=None、legacy slot-run 安全 false negative 不强行放行。pipeline↛chat，trigger 白名单仅 run_completed/run_failed/craft_decompiled。旧 plan-card disclosure 按当前面清理由真实旅程复核。旧 HOLD/相位退休记录不是当前证据，按 fresh 行为重验，不复做过时施工。

若删除 _read_face，先证明目标实例 generator/processor/agent/modifier/materialize 及旧 toolset 无消费者/存量；允许本轮授权 reset 后查零，不伪造迁移或已执行。已应用 Alembic 历史保留；无用户旧数据不再要求兼容搬运，仍保留数据的其他环境须先读容忍再收窄，不得混用授权范围。

后续 hygiene 不入关键路径：按职责拆 chat/service、models/schemas、graph_fill；Message.intent union；edit_output 事务对称性（失败零残留或明确 ADR 例外）；ChatDock 仅按依赖需要评估。逐缝小提交、行为不变，compile/import/依赖门与受影响旅程验证，不能损坏草稿保活、SSE、授权与唯一写口。

### 5.7 现有 UI 自足与锚卡

Canonical：UI_GUIDELINES、CHAT_ARCHITECTURE、ADR-118/122/143。待验移动纯 Chat 上传→授权→生成→delivered/partial/failed→修订；unknown 能力、无 world、pending plan、缺/重复 output_refs、失败不出假锚卡。桌面 auto/chat 切换按当前渲染能力，不钉历史设备；锚卡只是收据投影，N 个平铺/稳定去重，无新订阅、合集卡或第二 live 状态源。

真实 MediaLightbox 播放、跨 Home/Lightbox 声音互斥、离屏暂停所有权、copy/免责声明、双主题/无横溢、MentionEditor 不 remount、背景相机不动、WorkSegment 正确收口都未自动通过。交付正文始终只讲实际结果，不给界面引导或内部 ID。Home 真片状态只读 home-creation-entry-refresh；空货架/假 Queue/mic/反馈按钮不复活。
