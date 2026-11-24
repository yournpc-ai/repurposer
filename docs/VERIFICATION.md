# Verification — 测试政策、核心覆盖与当前验收

> Status: 当前规范（2026-11-10）。本文是测试运行纪律、核心合同↔测试映射与跨模块验收的唯一母文档；排期仍归 PROGRESS。测试/文档退役不是产品验收通过，绿色历史标记不等于当前 HEAD 或真实旅程已通过。
>
> 视频验收见 [Agent 总合同](tasks/new-agent.md) 与[当前 I8 证据](tasks/agent-editor-evidence/iteration-8/README.md)。覆盖 Composition 版本、时间与 video-spec，以及共享权限、授权、计费、执行身份与消息回放。保留开放项及其验收条件。

关键帧编辑验收分别核对版本写入、完整受影响运动和真实模型判断。恢复验收从导出成功的持久边界中断进程，核对同 opening 的实际调用、版本、Job、账本与交付卡。I7 以真实 MiniMax 断点恢复、Chrome 刷新和下载、270 帧图像配准、五处文字识别及旧新版本差异完成两条验收。模型审片的采样时点单独记录。[I7 已验证范围](tasks/agent-editor-evidence/iteration-7/README.md)

## 1. 测试运行政策

### 1.1 当前资产边界

测试体系按四层 Chat-Origin 金字塔组织（完整结构与命令见 `docs/TESTING.md`）：

1. **Layer 0 纯合同与 Py↔TS 一致性**：`apps/api/test/unit/`、`packages/video-spec/`、`packages/sound-engine/`（零 DB、零网络）。
2. **Layer 1A Chat-Origin 集成套件**：`apps/api/test/chat_origin/`，覆盖 `/api/v1/chat` SSE/JSON、创作与动效块、风格与字幕编辑、实时观察与侧聊安全、多会话/压缩/Eval 反馈/工作台、Skill 蓝图与槽位预览、付费授权与导出竞态。
3. **Layer 1B 基础设施与迁移一致性**：`apps/api/test/infra/`，覆盖应用启动与 Alembic `upgrade head` 表结构一致、Composition CAS 写口、存储适配器与作业删锁。
4. **Layer 2 Web Studio 与 Render 服务**：`apps/web/src/**/*.test.*`（含 EN↔ZH i18n 一致性）、`apps/render/src/**/*.test.ts`。
5. **Layer 3 真实视听评测 CLI**：`apps/api/scripts/eval_chat_e2e.py`（`make eval-chat`），在独立临时 PostgreSQL 与 `local://` 存储上运行真实 `/api/v1/chat` 场景并校验 SSE、工具效率、无内部 ID 泄漏及 1080p MP4 视听流。

内部 helper、提示词文案与实现形态不另立永久测试；重构使测试失去合同依据时直接删除，不留注释尸体。

### 1.2 当前验证层

- 快速纯合同门禁：`make test-fast`（Layer 0 API `unit` + `video-spec` + `sound-engine` + Web `tsc`）。
- Chat-Origin 与全量 API 确定性测试：`make test-chat` / `make test-infra` / `make test-api`（不调用真实模型、不执行付费制作；会话级临时 PostgreSQL + 每测毫秒级表清理）。
- Web 与 Render：`make test-web`、`make test-render`；整仓确定性总门禁：`make test-all`。
- 真实视听评测（按需授权）：`make eval-chat SCENARIO=<name>`（列出场景：`make eval-list`）。需要模型配额；评测只锁用户可见结果、SSE 遥测、数据库真值与视听流，不锁 LLM 文案。
- 诊断脚本不是部署门禁，读数不能替代确定性测试、真实评测或人工验收，也不能为放行调整断言。

#### I8 普通编辑回合的定向验收

已测普通编辑、片尾观察与创作认可待定的原句样本见 [P1 定向实测](tasks/agent-editor-evidence/iteration-8/final-acceptance/README.md#p1-普通编辑与结束--2026-11-23)。A–G 是可在少数真实 Chat 旅程中合并取证的行为维度。每条从用户原话出发，按同一 opening 对照实际工具调用、已保存的改动、模型真正收到的媒体（如有）、最终正文与刷新结果。接受等效合法的工具组合。区分自然出现、受控触发和仍未覆盖的分支。

| 用户请求与维度 | 工作行为 | 通过判据 |
|---|---|---|
| A「把图移左，再缩小一点」 | Agent 可连续 translate、scale，自行决定何时看 | 两次写入均有回执；改动限于目标属性，其他对象、素材引用与动画保持。可直接报告已修改 |
| B「让产品图和人物都看得清」 | 合法的中间位置遮脸；Agent 自主看片，发现问题后调整位置 | 历史保留中间修改；工具记录、实际送达的画面与后续修订相符，最终局部可核对两者可见 |
| C「先把图向左移，改好告诉我」 | 写入后经自然正文或 answer 结束；覆盖没有预览的样本 | Chat 准确说明位置已改；没有看片也可结束。宣称已确认没有遮挡则须有实际所见 |
| D「播放第 2 到 4 秒」 | 从当前稿交回指定窗口；对照 Agent 是否也收到了画面或声音 | Chat 可实际播放该段。仅有播放器时不能声称模型或用户已看过；已有适用观察时，收尾无需重播 |
| E「把主镜头再留半秒，做不到就告诉我」 | 无可用源余量及替代动作时，Agent 读结构、说明限制 | 拒绝调用不产生写入；Chat 说明原镜头边界及可继续条件，旧成片可打开 |
| F「结尾再留半秒，其他保持原样」 | 字幕已延长，随后重复拒绝或耗尽预算；分别核对两个停止出口 | Live 与 Replay 同样说明字幕延长半秒、主片未延长、旧文件仍在及可继续之处；已保存的修改可追溯，重放不重复写入或收费 |
| G「可以了，导出」 | 原授权固定当前内容，核对 ExportJob、真实 MP4、审片与交付 | 播放、下载、历史卡及扣费对应同一授权和 Output；之后改稿仍能打开原文件 |

**片尾意图对照**　沿用同一 v3、前三轮 Chat 和已交付 Output。记录每个 opening 的起点、累计改动、真实 Provider 对话与可见媒体。本表为场景名，与上表行为维度及历史 P1 样本字母独立。

| 场景 | 输入与验收依据 |
|---|---|
| A 原句 | “结尾再留半秒，其他保持原样。”核对新增半秒、其他约束、实际选择及说明。上下文支持多种结尾时，创作认可可记未定。 |
| B 明确黑底 | “让主视频正常结束，最后品牌标题在黑色背景上再停留半秒，其他不变。”核对主片止点、标题和实际新增画面。 |
| C 明确主画面 | “最后一帧产品画面再停留半秒，不要变成黑底标题。”核对新增半秒是否确为所指画面。对象有实质歧义时可澄清，能力不足时如实说明。另加字幕、用其他图片替代或未经许可生成均不能签收为完成。 |
| D 认可后续改 | 从已有黑底片尾继续：“这个黑底品牌结尾可以，再留半秒。”按本轮起点核对只增加 0.5 秒和旧片尾其余部分。 |
| E 回归 | 保留连续位移与缩放、自选局部播放、无预览诚实结束，以及 P0 部分写入、重放、旧文件与费用的原始分母。 |

操作和明确要求可判定通过或失败。感知陈述须核对媒体覆盖；技术完成、沟通偏差、审美认可分别记录。需要用户决定时只问影响核心目标的问题。

分别签收 Tool 合法性、Agent 的创作判断、回合陈述真实性与交付可靠性。局部编辑核对领域修改；有感知声明时按其实际媒体核对。保留首次失败和费用，修后复测另计。正式媒体时钟、文件摘要、已授权导出和强杀恢复沿用原证据，仅补测改动涉及的交界。[I7 恢复](tasks/agent-editor-evidence/iteration-7/README.md) · [I8 最终验收](tasks/agent-editor-evidence/iteration-8/final-acceptance/README.md)

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

核心测试按四层目录与标记组织（详见 `docs/TESTING.md`）；下表仅映射归属位置，不声明未运行项已通过。

| 用户依赖的合同 | 确定性测试座 | 真实评测 / 额外证据 |
|:---|:---|:---|
| 应用组合根与 Alembic 迁移一致 | `test/infra/test_platform_boot_and_migrations.py` | 活 API 健康检查与迁移实测 |
| 支付、积分、计量与报价 | `test/unit/test_billing_and_payments.py` | 真实 webhook、费用确认与钱包台账 |
| 风格、字幕、动效块、音效与 video-spec Py↔TS 一致性 | `test/unit/test_composition_style_parity.py` / `test_text_style_parity.py` / `test_motion_blocks_and_sound.py` / `test/unit/test_video_spec_and_generator.py` | `packages/video-spec`、`packages/sound-engine` 与浏览器渲染 |
| Chat-Origin 创作、编辑、音效、观察、侧聊、多会话与工作台 | `test/chat_origin/test_chat_creation_and_motion_blocks.py` / `test_chat_editing_and_audio.py` / `test_chat_observation_and_side_chat.py` / `test_chat_multiconv_compact_eval_workbench.py` | `make eval-chat` 真实 SSE 与视听流校验 |
| Skill 蓝图、槽位预览、包安全与内置技能 | `test/unit/test_skills_and_packages.py` / `test/chat_origin/test_chat_blueprints_and_slot_promo.py` | 真实多幕复用与浏览器槽位预览 |
| 付费授权、导出/停止竞态、交付与产物探针 | `test/chat_origin/test_chat_delivery_and_media_races.py` / `test/chat_origin/test_export_stop_races.py` / `test/unit/test_previews_and_probes.py` | 明确授权的制作与 worker 恢复 |
| Composition CAS 写口、存储与作业删锁 | `test/infra/test_compositions_store.py` / `test/infra/test_storage_and_exports.py` / `test/infra/test_projects_and_jobs.py` / `test/infra/test_account_settings.py` | 真实并发写入、对象存储与发布回执 |
| 网页采集、SSRF 策略、品牌就绪度与 Provider 协议 | `test/unit/test_web_capture.py` / `test/unit/test_website_readiness.py` / `test/unit/test_provider_protocol.py` / `test/unit/test_chat_turn_policy.py` | `inspect_model_trace.py` 与真实采集取证 |
| 前端 Studio 交互、渲染器与 EN↔ZH 翻译一致 | `apps/web/src/**/*.test.*`（含 `src/lib/i18n/parity.test.ts`） / `apps/render/src/**/*.test.ts` | 真实浏览器交互与 1080p 动态视听 |

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
