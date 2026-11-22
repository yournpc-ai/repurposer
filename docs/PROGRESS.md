# PROGRESS — 进展、排期与需求池

I6 有条件收官。通用文字动画与显式 Skill 的 OxValue 宣传片均已交付两个固定版本，Chrome 验证播放、刷新与下载。I7 第一批在隔离库完成两条真实 MiniMax 旅程。导出成功后强杀 API，恢复沿原 opening 审片及交付，只扣费一次。OxValue 第二镜头由模型修改两个已有位移点，保留缩放和六段旁白；新版预览和正式 MP4 已比对全部 270 帧。[I7 实测边界](tasks/agent-editor-evidence/iteration-7/README.md)。费用、恢复偏差及实测边界见[最终验收记录](tasks/agent-editor-evidence/iteration-6/final-closure.md)。

**2026-11-22 成片存储策略更新**　正式导出与素材共用当前公开 TOS 桶。新成片写入 `exports/`，既有公开测试成片按原对象地址回放。成片预览使用公开直链，上传与带文件名的下载继续使用签名。项目、版本、导出费用和交付检查仍由原有接口负责。下方关于私有桶的记录属于此前的验收环境。

> 更新至 2026-11-22。Agent Editor 的施工顺序、作品模型和验收标准以 [主合同](tasks/new-agent.md) 为准。下方历史官网项目的阶段和开放事项继续用于核对各自项目。

## 0. 当前里程碑与施工序列

### 0.1 里程碑状态

- **I8 首个专业编辑切片有条件通过。** 已有视频的固定图片插入、同对象续改、局部回放、授权交付和保存后强杀恢复已有真实记录。原 Dev 库保留，默认入口改用独立库。横图、竖图、歧义首错及原素材回归分别计数。双图 QuestionDock 两次浏览器续行未通过，末次修正只验证了 Provider 载荷。下一步在新工程点选绿图，核对原请求的插图、局部播放、刷新与零扣费。[当前范围](tasks/i8.md) · [五面证据与费用](tasks/agent-editor-evidence/iteration-8/README.md)

- 6A 已在原验收库核对回归记录，并以真实认领函数复现跨时钟误回收。历史首个 token 与供应商最终账单未留证。详见 [执行审计](tasks/agent-editor-evidence/iteration-6/README.md)。6B 已在真实隔离栈完成原接缝、片尾卡、强杀恢复和十用户私有播放。TOS 建桶返回 403，云端上线待验。[6B 验收](tasks/agent-editor-evidence/iteration-6/export.md)。

- 6C 隔离验收使用 PostgreSQL 5966。合成文字卡经原生导出处理函数、ExportJob 和 Renderer 写入现有 TOS；按不可变版本配置公开测试许可。对象匿名 GET 为 200，其他用户访问应用的 Output、签发与下载入口均为 403。事故旁白历史回放和原库删除盘点等待只读实例或一致性备份。[真实 TOS 导出记录](tasks/agent-editor-evidence/iteration-6/public-test-export.json)

- 6C 在隔离库完成三类 MediaJob 的实际生成、跨项目图片隔离、原生多调用、进程强杀与恢复费用确认。事故原库仅供历史研究。[媒体验收及首错](tasks/agent-editor-evidence/iteration-6/media.md)

- 6D 已从 Agent 主线删除 Workflow/Graph/Run/Step。隔离库从零安装、两次十用户窗口、同项目边生成或边导出边编辑及原 opening 交付均有实测记录。五个新项目的用户旅程、实际积分、首错及重试按样本登记。[6D 验收](tasks/agent-editor-evidence/iteration-6/6d-acceptance.md) · [Chat 文件交接](tasks/agent-editor-evidence/iteration-6/ui-handoff.md)

- **当前产品主线为 Agent Editor v1。** 六个独立素材原始首次验收仍为 3 完整、2 部分、1 失败，跨素材普遍稳定尚未证明。三条未完整通过任务已完成首错归因和最小闭环：开放演讲复测在 17 次请求内交付、字幕本轮目标完整，但开放与单人仍有视觉误述；两个新增独立素材主任务达成。接缝、片尾卡和媒体生成回归被 Worker fencing/固定音频恢复故障阻断，不能算作保持成功。主观音频、自然语言事实和开放任务稳定性仍开放。[主合同](tasks/new-agent.md) · [首错归因与最小闭环](tasks/agent-editor-evidence/iteration-5/closure/cross-material/first-error-repair/README.md)

- **R1 — Core Product Beta：已封板**。实现与验收已闭环；baseline LLM 方差族 S1 / S6f / S10 仍是登记的开放观察项，不作为新的 release regression 自动放大范围。验收以当前合同与验证登记为准。
- **既有 Chat-only Video Project 验收范围**：Project / Composition / CompositionVersion、Track/Clip/Object、Skill 和 video-spec 承重；创作、修订、授权、交付与观看在同一 Chat。P8/P9 已完成指定退役与真实验收，旧 Film、旧文案产品、旧 Clip/ClipSpec 和多 Output 画廊不再作为现役实现。剩余主观视听、许可、完整 live 矩阵、部署与发布统一按 `tasks/skill-package-promo-video.md` 及其创作循环合同推进。
- **R1.1 — Commercial / Distribution：支付首批 ACTIVE，其余排期挂起**。Stripe 一次性积分充值已落码并通过本地真实付款主旅程，重放/并发等验收、公网 test 与 live 仍未完成，范围与合同见 §0.3；落码与本地主链通过不代表可 live 收款。

### 0.2 Active batch 与开放事项

“当前”表示本轮优先；“开放”表示仍有未实现、未验证或阻塞事项，但不等于已授权立即施工。Agent Editor 的排期只读主合同 §8。其余项目按各自合同登记，旧官网批次与历史 Run 展示不构成本主线的开工条件。完成项从本表移除；长期约束归母文档，未验收项不得写成完成。

| 状态 | 工作 | 当前事实与下一步 | 状态 / 合同 |
|---|---|---|---|
| 历史验收 | **Agent Editor · 首错归因与最小闭环** | 六个独立素材原始首次仍为 3 完整、2 部分、1 失败，不回填分母。单人是最终视觉陈述过强，字幕是审阅已指出硬要求未满足后仍交付且漏报，开放演讲首错是已有作品上误用 `create_video`。本轮仅调整现有停止/未满足项 Prompt，并在固定源预览补源音频事实。原话复测中字幕本轮目标完整，开放 17 次请求交付但仍有留边误述，单人仍有手部误述；两个新增独立素材主任务达成。双人视觉编辑与 API 续改保持；接缝、片尾卡、媒体生成三项回归因 Worker fencing/固定音频恢复失控未通过。当前 API core 509、Web 44 文件/411、Renderer 28 通过，三份新 Output 实播/硬刷新、Stop 和 Studio 续发已核验。开放审美、主观音频、自然语言事实与 Worker 故障仍未关闭。 | [首错、五面、费用与开放项](tasks/agent-editor-evidence/iteration-5/closure/cross-material/first-error-repair/README.md) |
| 历史项目 | **Chat-only 视频创作主链** | 已验证 URL 首稿/确认/钉版交付、真实上传选段/字幕/配音、重复确认幂等，以及缓存重传后同片刷新播放。保存版局部修订已改为直接 Op 批与当前目标投影，一次相关修改原子落一个版本；两次真实模型直接 Op 调用（单 Op 与双 Op 批）均通过 schema，但通用成功率未测量。剩余完整 live 矩阵、主观视听、样片、Remotion 许可、部署与公开发布归 P6+P7，精确编辑和 Output region 目标解算归 P10 | [统一视频合同](tasks/skill-package-promo-video.md) |
| 历史验收 | **官网品牌宣传片批 1A：装配修复、集中澄清、品牌档案与创作状态继承** | Readiness 三阶段、真实 PNG analyze_brand、扩展 Brief/CreativeState、集中问题组前后端和版本/Run 继承已落码；fake provider golden wire 通过，`test/core` 437 项与 Web 410 项通过，TypeScript 通过。真实 LegitEvi BrandProfile 含实测 `#DC0000`、“接近 Inter”和原始宣言；数字 option_id 整组提交已验证标签回填、六项 user-stated、preview/正式 digest 一致、过期/重复 409 与刷新恢复，当时 readiness=design_video（现 create_video）。旧批 1A 验收止于集中作答与本批状态恢复；当前首稿与后续编辑由 Agent Editor v1 主线统一，真实网站行为与能力限制见续批证据。开发库已确认 h8e5a2c4d7f1，生产 migration/恢复和本批真实浏览器问题组仍未验证 | [任务合同](tasks/website-promo-evidence-brief-workflow.md) / [验证登记](VERIFICATION.md#411-官网品牌宣传片基础链iteration-1a) |
| **当前** | **网页采集批 1：通用协议、部分成功与集合采集** | `capture_web` 已改用 CaptureRequest；服务端自动 baseline/scale/血缘，逐 output/member/state 与写盘部分成功，有界 issues 进入 Asset/Snapshot 和即时结果；支持共同 blank plate、普通/透明纹理，单 Generator 固定资源上限 64 且既有字节预算不变。纯采集/Generator/app-boot focused 107 项已通过；digest 复用与结果投影两个 DB 用例断言均通过，但临时库 fixture 收尾未正常退出；数据库 focused、完整 core 与真实 Chat 素材采集/首稿仍待当前环境或用户验收。批 2 `page_script` 未实现，正式 Composition/Renderer 未改 | [采集合同](VIDEO_PROJECT.md#92-网页理解与镜头素材采集两阶段) / [统一视频合同](tasks/skill-package-promo-video.md) |
| **当前** | **Stripe 一次性积分充值** | €10/€20/€50 输入预设、自由金额 input、服务端统一 `price_data` 下单（无 Stripe Price 配置）、payment_orders/migration、Checkout/webhook/purchase、Settings 购买面与返回确认已落码；既有 €10 订单已验证本地 Checkout → webhook → paid/purchase → UI 且仅有一条 purchase 台账，migration 已由 dev 执行；`payment_webhook_events` 持久审计与 worker Resend 告警已落码，但新 migration、真实 DB 重放/并发/故障恢复与邮件投递未运行；统一金额链改动后的真实联调、€20/€50、取消/过期、pytest/web 检查、公网 test 仍未运行 | [支付架构](PAYMENTS.md) / [施工与验收](tasks/stripe-credit-topup.md) |
| **当前** | **Landing 对话式视频叙事与内测商业面** | 暖白底三层 Hero（Rookie Cut 品牌与新主标题）、四类 Tab 自动演示/独立背景、340svh 固定滚动叙事、静态 Gallery（当前不挂载）、正文 FAQ、简洁 CTA 与参考三列 Footer 已落码。演示使用公开候选样片与交互投影，未验证为真实 Chat 回放或修改后成片；真实类别样片与多轮交付仍按 P6+P7 验收。既有 TypeScript 与 landingCreate 定向检查通过；最新 Header/Hero 视觉调整尚未复跑静态检查或浏览器验收，桌面首屏/Tab/FAQ/Footer、其余尺寸、双主题、reduced-motion、媒体播放与登录预填完整旅程均待复验。Footer 未配置项目仅保留文字座位，发布前需真实链接或移除；公开 1,000 开户赠额前核对数据库配置；支付与公开授权门未关闭 | [当前合同](LANDING.md) |
| 历史项目 | Agent Tools 修复批验收尾项 | 代码批已完成并落 main；需活 API + dev worker 运行当前注册旅程矩阵，覆盖长程序经 `get_node` 修订、distilled `specific_instruction`、pending-plan/run-history 读面；另需抓真实 SSE 验证 reasoning/think 永不进入用户 wire。完成证据出现前不关闭 | [验证登记](VERIFICATION.md) |
| 历史依赖核对 | 早期 Agent Working Loop 开放记录 | 当前真实 Chat 旅程、SSE、CJK 长素材检索及仍支持的候选和恢复路径待验收。旧探索存储的验收改为验证退役 migration、保留数据及回退条件 | [合同与验收](tasks/agent-working-loop-iter-3.md) |
| 历史项目 | 积分与视频交付修复验收 | 并发/幂等结算、失败交付判定已有定向回归；单次上传 10 分钟；chat `retry_upload` 已改为当前回合的独立上传工具与状态行，走 /upload 并保留原 Run/失败步骤；缓存 miss 不重渲染。定向 API 121 项、历史回放 44 项及 Web/render tsc 通过，新上传 UI 真实浏览器旅程尚未复验；历史预扣补偿尚未执行，Surge 大文件真实重传、upload-only 与浏览器端完整旅程仍待验收 | [账本](BILLING.md) / [渲染](RENDERING.md) |
| 历史项目 | 旧画布确认迁移的未验项 | 当时缺少 rejected-turn 无残留、等待节点、相机 fit、采集前估价、刷新重建和跨轮防复读的完整浏览器证据。现役 Chat 的问题、报价和刷新按消息回执验证。 | CHAT §8；历史 ADR-099/111 |
| 开放 | 消息回放与素材检视 | seq/首回合事务、interim_prose 五路、Candidate聚合例外裁决及live/replay，素材overlay/StageSkin/NLE轴和双主题仍待验证。新鲜数据重建不要求旧行回填，保留数据环境另守读容忍与迁移条件；re-cut等后续需求未取消 | [消息与UI验收](VERIFICATION.md#54-素材卡transcript-与精确编辑边界) |
| 开放 | 素材理解与对话面验收 | 素材/咨询真实旅程和 live 场景仍待完成：消息回放不丢且不重复叙事；不得创建独立转写节点/卡，资产卡只在真实处理状态出现后显示处理中；休眠期状态诚实；in-flight beat 不重复落；法条词汇不被复读。ASR GPU/云加速是独立运营项，不属于本验收 | [验证登记 §4.3](VERIFICATION.md#43-素材理解与对话回放) |
| 开放 | Credits / permissions（ADR-117） | 代码层已收口；仪式链、conversation_usage 真实行检查和配置清理仍待用户验证 | [验证登记 §4.2](VERIFICATION.md#42-授权会话计量与配置) |

### 0.3 R1.1 — Commercial / Distribution（支付首批 ACTIVE，其余排期挂起）

Stripe 一次性积分充值首批已落码，migration 已由 dev 执行，既有 €10 订单已验证本地 Checkout → webhook → paid/purchase → UI 主旅程且仅有一条入账台账；€10/€20/€50 预设与自由金额现已统一为前端提交 `amount_minor`、服务端 `price_data` 下单，无 Stripe Price 配置依赖。统一金额链改动后的真实联调、测试套件、重放/并发等剩余验收尚未运行。公网 API origin/反代与 Dashboard endpoint 是当前外部待办。其余商业化与分发仍按外部凭据、平台审批和后续排期启动，不倒灌成 Video Project 当前主线的结束条件。

| Batch | 范围 | 状态 | 依赖 | 合同 |
|---|---|---|---|---|
| B4b | hold GC：资格谓词与 claim 谓词语义镜像 | PLANNED | B4a | [合同](tasks/r1-1-batch-4b-hold-gc.md) |
| B5a | Stripe 一次性积分充值：公司 test 账号、CLI/公网 webhook、固定/自定义金额 Checkout、支付订单、purchase 台账与 Settings 购买面 | ACTIVE | 固定档位本地真实付款主链已验证且仅一条 purchase 台账；自定义金额真实联调、剩余资金/权限验收、测试套件、公网 API origin/反代和 Dashboard endpoint 待完成；live 配置另行 | [支付架构](PAYMENTS.md) / [施工合同](tasks/stripe-credit-topup.md) |
| B5 | 订阅/权益/计费中心/agent_calls、渠道联调与已发布产物删除边界 | PLANNED | R1 + B2 + B5a | [合同](tasks/r1-1-batch-5-commercial-distribution.md) |

### 0.4 新会话执行规则与启动 Checklist

**事实源分工**：current code / DB constraints / migrations 说明“现在如何实现”；new-agent 总合同确定架构边界，当前任务合同和本节记录已授权范围与验收状态；旧 ADR 仅用于追溯。二者冲突时先标记 discrepancy 并查证，不得以旧计划推翻代码，也不得以代码暂未实现推翻已拍板需求。

**执行规则**：
1. 开工先看 `git status`、current HEAD 与并行归属；工作树可以有未提交成果，禁止用 reset / checkout / stash 制造“干净基线”。
2. 阅读范围 = 本文件 §0 → 当前任务状态/合同的相关章节 → 适用规范。视频阶段施工固定先读 VIDEO_PROJECT §0 创作方针，Generator 的目标/现状按 §4.3.2 与施工合同区分。按 [CLAUDE 默认阅读与收尾协议](../CLAUDE.md#默认阅读与收尾协议) 先搜索定位再读取；局部修复不通读模块欠账，compact 后不重新通读历史。
3. 一次只解决合同内 correctness/product gap；发现合同与代码或现行法不一致时先报告，不自行扩 scope。
4. 每轮从代码与真实证据重新验证 DoD；旧测试计数、旧 audit 和其他会话的“基线绿”不能替代当前验证。
5. migration、状态机、并发与授权改动必须有匹配覆盖；测试归属遵循 [Testing 规则](../CLAUDE.md) 与 [验证合同](VERIFICATION.md)。
6. 验证按改动面执行；部署前仪式链与付费边界见 CLAUDE.md。未运行的 LLM/真实旅程检查必须写“未运行”，不得改写为通过。
7. 触及 agent loop / 意图 / prompt 时，验收必须回答：Agent 看见了什么、对用户需求的内部表示是否一致、如何知道自己做对了。
8. 状态更新覆盖旧快照；规则变化更新唯一事实源；普通修复不新增 ADR；不保存历史报告或归档，失效内容直接删除。

**启动 Checklist**：
```text
[ ] 读 PROGRESS §0，确认当前优先与本任务是否已授权
[ ] 读当前任务状态/合同及指定章节，确认未完成项与禁止事项
[ ] 核对 git status、current HEAD、并行归属和真实代码座位
[ ] 明确本批验收层级与付费/部署边界
[ ] 完成后更新当前快照、剩余风险与下一步；不追加会话编年史
```

**Non-negotiable constraints**：LLM 面不直接写 DB；tool schema 是 action 边界；`apply_composition_edits` 是作品编辑写口；`_mutate` 双层 dedupe 不得破坏；video-spec 是唯一在线渲染协议且不得混入 renderer 私有概念；打字机律不得破坏；perception 只读（明确批准的 world-seat 例外归对应 ADR）；终态写携带执行身份；MediaJob 与 ExportJob 按各自认领身份提交，同项目可继续编辑。详细约束按任务读 [North Star](ARCHITECTURE_NORTH_STAR.md) 对应章节，不要求所有任务通读。

## 1. 后续能力、延期事项与上线条件

当前编辑能力和开放验收归 §0 与 I8。

### 1.1 已撤销的运营规划

旧选题中台、定位根迁移及多渠道内容输出已退出路线。冻结历史 Persona、Publication、凭证和素材外键，处理存量依赖时须保留权限、历史作品和账本。

### 1.2 商业化与分发（支付首批 ACTIVE，其余排期挂起）

Stripe 一次性积分充值已落码并通过本地真实付款主旅程，剩余资金/权限验收、测试套件与外部公网配置见 §0.3 B5a、`PAYMENTS.md` 和对应施工合同。订阅、权益、用户计费中心、渠道联调及 hold GC / cache identity 仍按对应合同挂起，支付商、平台开发者权限和公司主体审批是外部前置。

### 1.3 法务、合规与上线准备（PLANNED）

- 法务页面、用户协议、隐私政策、Cookie 同意；律师人选、文书与预算仍是外部依赖。
- AI 内容标识：导出文件携带机器可读标识，合成轨道与纯剪辑按 `DECISIONS.md` ADR-026 分级；披露随发布携带。
- SEO、验证码邮件域名认证（SPF/DKIM）、数据生命周期说明、错误/可用性/API 成本监控。
- 上线回归须覆盖多用户权限、并发编辑、生成或导出失败后的计量与恢复。
- go/no-go 前需端到端上线演练和 2–3 名真实用户走查；已知阻塞、未验证项和回退条件必须进入评估材料。已落码不等于真实旅程通过，更不等于正式上线。

### 1.4 当前排期决策

当前 go/no-go 目标日与最迟回退位存在冲突，需总监确认目标日期和范围压缩方式；具体决策与外部依赖见 §3。未拍板前，目标日期不作为完成承诺。

## 2. 待核对的现役依赖

下列问题仍能指向具体消费者，保留触发条件与验收边界。实际优先级归 §0。原需求池中的旧 Run、渠道内容和选题运营优先级已撤销。 [原需求池](https://github.com/yournpc-ai/repurposer/blob/b01823d614ddff4972e26fc1a56987f5f5f30336/docs/PROGRESS.md#2-需求池未排期常驻)

| 问题 | 依赖 | 核对范围 |
|---|---|---|
| 媒体展示一致性 | 项目缩略图已下发 `thumbnail_aspect`，核对前端实际消费；复用现行媒体组件 | 视频/图片处理时保存尺寸并透出，旧素材使用共享探测；9:16 产物与竖屏项目缩略图按真实画幅完整展示。Chat、composer 和上传 chip 共享媒体类型/图标，Home 卡片保持仅预填 prompt；覆盖双主题及旧数据。 |
| LLM 滚动摘要（超长会话历史） | 先用 `apps/api/scripts/context_budget_audit.py` 观察窗口折叠真实溢出率 | 当前仅滑动窗口折叠（`chat.context_budget_tokens`）；没有早期引用丢失的真实发生率证据前，不新增摘要生成 |
| 渲染服务源站限速韧性 | 无 | 当前缓解 = 渲染进程 `HTTPS_PROXY`；长期方案 = 源下载落盘再渲染或 renderer 显式 proxy dispatcher，避免直连 TOS 限速导致取帧超时 |
| 字幕简繁归一跟 `target_language` | 先拍板 ASR 逐字保真与展示一致性的边界 | 避免同一帧简繁混排；字幕层按目标语言归一，不静默改变需要保真的源文 |
| TRANSCRIPT 资产生产侧语言印记 | 消费侧已读 `meta.language` | transcript/docx/pdf 等文本 processor 完工时写入语言探测或上传者声明，给纯文稿项目提供源语言锚 |
| 归档 version 存储成本观察 | 归档写门持续产生真实版本后观察增量 | 归档文件是回滚物理基础，当前仅随项目删除 GC；有存储曲线证据后再评压缩/清理，不预设删除版本 |
| fenced 残留清理（孤儿媒体 + 孤儿问题） | 存储 GC 与问题生命周期设计 | 只清理可证明孤儿的直传媒体与 fenced Suspend 问题；不得误删用户内容或审计证据，保持 fenced 零副作用 |
| 素材理解复用身份 | 启动前先确认现役 producer 和重复处理成本 | 若需持久复用，以 owner、素材哈希、处理版本和判断 prompt 身份判定命中；同一有效输入并发复用须有唯一赢家且不重复收费，身份变化应 miss。旧素材读容忍，迁移需有回退或前滚路径。 |
| 发射层 / provider 方差受控复测（S5 族） | 与建议发射率共用取证面 | 固定模型/provider/温度/工具/输入/初始状态重复采样，按失败签名记频率；区分采样波动、prompt 不足、应用处理不稳与评测器过敏，不用单次绿红直接归因 |

## 3. 外部依赖与决策点

**外部依赖：**

- LinkedIn / TikTok 开发者权限：**暂缓申请（时间未定）**。需以公司主体申请、审批周期数周；双平台代码已完成。联调排期届时按实际申请时间重排。
- 支付商入驻审核：启动时间随 R1.1 排期；需预留数周审批周期。
- 法务文书：律师外部产出通常需 2–4 周；人选、预算与启动时点待拍板。

**需要拍板的决策点：**

| 决策 | 需要谁 |
|---|---|
| 支付商选型（欧盟 VAT 由平台代处理 vs 自建税务）与入驻启动 | 总监拍板 + 工程调研 |
| 目标上线日：go/no-go 目标 **2026-11-17**，最迟回退位 **2026-10-30**；两者相差十二个工作日，需确认目标日期、范围压缩和外部依赖回退方案 | 总监 |
| 律师人选与预算 | 总监 |
| 定价套餐的业务输入（档位 / 免费额度 / 计价形态） | 总监 + 业务侧 |

---
