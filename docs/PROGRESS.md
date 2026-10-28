# PROGRESS — 进展、排期与需求池

> Status: 活跃快照。§0 为当前优先级与开放事项；需求池持续维护。状态就地更新，删除失效快照，不保存周期归档。
> 本文是**排期 / 优先级 / 需求池的唯一事实源**（未排期需求见 §2）；其他文档只引用当前优先级或需求池条目，不复述排期。

## 0. 当前里程碑与施工序列

> 新会话先读本节，再进入当前任务的状态/合同与其指定的具体规范章节。§1 保留后续能力与上线条件，§2 是常驻需求池；已完成工作不在这里留施工记录。

### 0.1 里程碑状态

- **R1 — Core Product Beta：已封板**。实现与验收已闭环；baseline LLM 方差族 S1 / S6f / S10 仍是登记的开放观察项，不作为新的 release regression 自动放大范围。验收以当前合同与验证登记为准。
- **当前主线 — Video Project 新架构**：按 ADR-145 与四阶段合同建设 Project / Composition / CompositionVersion、Track/Clip/Object、Skill 和 video-spec；A 最小基座已落地；B 按基础闭环、官网片、混合合成、程序画面、生成媒体、旁白余项分批实施，批次合同见施工文档 §2.5；C 为个人 Skill，D 为发布清理与独立扩展门。旧 Film 只作当前实现与对照，不再按旧 PLANNED 形态扩展。
- **R1.1 — Commercial / Distribution：排期挂起**。启动条件与合同见 §0.3，不因旧批次已备而自动解冻。

### 0.2 Active batch 与开放事项

“当前”表示本轮优先；“开放”表示仍有未实现、未验证或阻塞事项，但不等于已授权立即施工。完成项从本表移除；长期约束归母文档，未验收项不得写成完成。

| 状态 | 工作 | 当前事实与下一步 | 状态 / 合同 |
|---|---|---|---|
| **当前** | **Video Project 新架构** | **B-I～B-VI 各自限定出口及增强网页采集首个静态镜头已有真实 Chat 证据，完整 B 仍未封板。**字幕浮点毫秒量化已修；AgentVeil 正常 Chat 已完成增强采集 → 首稿 → `focus_web` 相机修订 → 制作 → 标题修订再交付 → 浏览器硬刷新，未改快照复用且 Run 不重复，证据归施工文档 §2.0 与 `artifacts/video-project-b/web-capture/`。全量 API1348、`check_gates` 通过；web/render 既有结果本轮未重跑。仍欠亲耳试听/音乐循环接缝、真实加速第二 pass、完整付费 prompt_gate 与剧本矩阵、多轮/Director 稳定性、长页补读/空底板/交互状态、内容审片、B-UI 及 §2.4 其余条目；B-VI 剩余 split/trim/必要转场/BeatGrid 未取消。C/D 未开始，综合验收作品未提前制作 | [目标架构](VIDEO_PROJECT.md) → [四阶段施工](tasks/video-project-implementation.md)（§2.0 / §2.5 / §9；综合验收作品见 §5.1） |
| **当前** | Home 创作入口真实样片 | Ads 族只展示 Product Promo 与 Text Animation 两个子 tab；Text Animation 使用项目 `9345ddc2` 与 `f52c489c` 的真实文字源 Film，Product Promo 前两张为 ZYMIX / AgentVeil 真片，其余两张占位卡仍待用户选定对应链真片。网页 Film 相机、默认字幕落点与强调标记渲染修复待 prompt/live/render 复验，既有 AgentVeil demo 未重渲染。配方点击只预填 composer，货架可点不等于制作能力通过 | [任务状态](tasks/home-creation-entry-refresh.md) |
| 开放 | 共享执行、图与产物验收 | render owner/并行写入/恢复、产物成员、staging、fresh graph、rank/RunOp 解耦、lifecycle/授权证明仍需真实验证。旧批次状态不作当前证据；无用户旧数据按本轮授权 reset，不再保留指定事故产物救援与业务搬运工单，reset 未执行不等于已清零 | [共享验收](VERIFICATION.md#5-共享机制与-ui-的当前验收) |
| 开放 | Agent Tools 修复批验收尾项 | 代码批已完成并落 main；需活 API + dev worker 运行当前注册旅程矩阵，覆盖长程序经 `get_node` 修订、distilled `specific_instruction`、pending-plan/run-history 读面；另需抓真实 SSE 验证 reasoning/think 永不进入用户 wire。完成证据出现前不关闭 | [验证登记](VERIFICATION.md) / [六段走查](tasks/agent-working-loop-iter-3.md) |
| 开放 | Agent Working Loop 持续闭环 | 代码层已落，六段 live 验收、Candidate Surface live/replay、CJK 长素材检索与探索存储真实 DB 迁移仍待完成；验收后才可按覆盖映射、当前矩阵、无回归证据与生产引用清点执行 `edit_graph` 退役小提交 | [合同与验收](tasks/agent-working-loop-iter-3.md) |
| 开放 | 积分与视频交付修复验收 | 并发/幂等结算、失败交付判定已有定向回归；单次上传 10 分钟、chat `retry_upload`、确定性重传建议与缓存 miss 失败闭已落码，新增/更新测试尚未运行；历史预扣补偿尚未执行，Surge 大文件真实重传、upload-only 与浏览器端完整旅程仍待验收 | [账本](BILLING.md) / [渲染](RENDERING.md) |
| 开放 | Agent 交互与画布确认迁移 | DeferredFrames 现行规则已归 CHAT；仍需真实 rejected-turn 浏览器证据：零客户端散文/预览、零服务端 commit/dock 残片，并保留有序原始事件。ADR-111 仍欠等待态节点面原型与 live 走查；相机 fit 缩放夹、capture 前估价面和刷新重建面须在同一份新合同中定清；跨轮防复读需可复现证据后再升级 | CHAT §8；现行决策 ADR-099/111 |
| 开放 | 消息回放与素材检视 | seq/首回合事务、checkpoint五路、Candidate聚合例外裁决及live/replay，素材overlay/StageSkin/NLE轴和双主题仍待验证。新鲜数据重建不要求旧行回填，保留数据环境另守读容忍与迁移条件；re-cut等后续需求未取消 | [消息与UI验收](VERIFICATION.md#54-素材卡transcript-与精确编辑边界) |
| 开放 | 素材理解与对话面验收 | prompt_gate、全量剧本和 live 场景仍待完成：消息回放不丢且不重复叙事；不得创建独立转写节点/卡，资产卡只在真实处理状态出现后显示处理中；休眠期状态诚实；in-flight beat 不重复落；法条词汇不被复读。ASR GPU/云加速是独立运营项，不属于本验收 | [验证登记 §4.3](VERIFICATION.md#43-素材理解与对话回放) |
| 开放 | Credits / permissions（ADR-117） | 代码层已收口；仪式链、conversation_usage 真实行检查和配置清理仍待用户验证 | [验证登记 §4.2](VERIFICATION.md#42-授权会话计量与配置) |
| 开放 | 新视频视听与现有 UI 验收 | 网页/MG双源、逐字保真、默认字幕/章节/reveal、严格slide与音轨要求归新视频B；纯Chat/锚卡/声音互斥/移动端/双主题仍需真实走查。旧实现测试与事故工单退出不代表新能力已通过 | [视频要求](VIDEO_PROJECT.md#15-新链必须承接的产品语义与验收缺口) / [UI验收](VERIFICATION.md#57-现有-ui-自足与锚卡) |
| 开放 | B-UI：Chat 产物平铺与共享查看器 | 待施工；B-VI 首个旁白出口已通过，下一功能批为 B 支撑增量（按需采集与审片），其后为 B-UI。本项作为 B 最后一个功能批次，其后集中核对 §2.4 欠账，不因查看器完成便标完整 B 封板。不等待 C/D4。每个 Output 独立浏览、版本仅作字段标识；消息行分散入口，共享翻页与缩略导航，包含历史归档交付 | [产品合同](VIDEO_PROJECT.md#104-chat-产物平铺与共享查看器) / [施工与验收](tasks/video-project-implementation.md#252-b-ui产物平铺与共享查看器待施工) |
| 开放 | B 支撑：按需采集与内容审片 | 增强网页采集首个静态镜头已通过真实 Chat 制作、局部修订再交付与硬刷新；只代表该切片。长页补读、空底板与交互状态按后续镜头需要保留，内容审片待施工，其后为 B-UI；D4 时间点编辑按独立消费者实施，不先建共享帧平台 | [施工与验收](tasks/video-project-implementation.md#253-b-支撑增量按需采集与内容质检采集首个静态镜头已通过内容审片待施工) / VIDEO_PROJECT §8.5、§9.2 |
| 开放 | C：真实加载 video-shotcraft 与最终自我介绍视频 | 待施工；C4 固定外部来源、选择声明镜头范围，真实加载并换产品素材复用；仅导入指令或报告缺口不算本消费者通过。最终产物为产品自我介绍视频，展示真实创作、审片与修订；不代替各阶段及 D 发布门 | [C4 与验收](tasks/video-project-implementation.md#3-阶段-c个人-skill-保存调用与外部导入) / 同文 §5.1 |

### 0.3 R1.1 — Commercial / Distribution（排期挂起）

商业化随支付商对接节奏或更后排期再启动；启动时在本节更新为当前批次并确定验收窗口。外部凭据与平台审批由 R1.1 吸收，不倒灌成 Film 当前试用的结束条件。

| Batch | 范围 | 状态 | 依赖 | 合同 |
|---|---|---|---|---|
| B4b | hold GC：资格谓词与 claim 谓词语义镜像 | PLANNED | B4a | [合同](tasks/r1-1-batch-4b-hold-gc.md) |
| B5 | 支付/订阅/权益/计费中心/agent_calls、渠道联调与已发布产物删除边界 | PLANNED | R1 + B2 | [合同](tasks/r1-1-batch-5-commercial-distribution.md) |
| C1 | skeleton cache identity；不阻塞其他 milestone | PLANNED | 无 | [合同](tasks/r1-1-batch-c1-cache-identity.md) |

### 0.4 新会话执行规则与启动 Checklist

**事实源分工**：current code / DB constraints / migrations 说明“现在如何实现”；PROGRESS、现行 ADR 与任务合同说明“已决定做什么、做到哪一层”。二者冲突时先标记 discrepancy 并查证，不得以旧计划推翻代码，也不得以代码暂未实现推翻已拍板需求。

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

**Non-negotiable constraints**：LLM 面不直接写 DB；拓扑由代码裁决；tool schema 是 action 边界；`apply_wiring_ops` 是唯一图写口；`_mutate` 双层 dedupe 不得破坏；clip-spec / film-spec 只按 `spec.family` 分派且不得混入 renderer 概念；打字机律不得破坏；perception 只读（明确批准的 world-seat 例外归对应 ADR）；`craft_scan` 零 LLM；终态写携带执行身份；project `{PENDING,RUNNING}` 至多一个 owner。详细约束按任务读 [North Star](ARCHITECTURE_NORTH_STAR.md) 对应章节，不要求所有任务通读。

## 1. 后续能力、延期事项与上线条件

本节只登记仍未完成的产品范围与验收，不复述已完成批次。`PLANNED` 表示已拍板但未实施或未闭环，不代表已经授权插入当前 Film 主线；排期变化就更新本节。

### 1.1 运营端与定位根（PLANNED）

目标架构见 [POSITIONING.md](POSITIONING.md)，代码层落地前仍使用 `persona`。启动前提是当前生产层闭环收口；具体窗口由 §0 更新。

| 范围 | 已拍板需求 | 完成验收 |
|---|---|---|
| 选题与内容生产中台 | `topics` 及生命周期、选题 agent、选题卡 prompt 预填；分镜/脚本/预设/文章等内容形态与渠道适配进入 tool registry；发射复用 `POST /chat`，不新增意图入口或直接 run | 选题 → 计划与授权 → 产物 → 精修全链可走通 |
| Memory 与身份显化 | 风格学习与校准回路使用用户选用行为和 operations 编辑痕迹；人设页说明学到了什么、来源与纠偏入口；现有声纹与皮肤机制不因重构回退 | 用户能检查并纠正人设，校准输入有真实记录 |
| 定位根与渠道归属 | `personas` → `positionings` 全栈迁移；内容定位字段、三分区、`channel_accounts.positioning_id` 与公共渠道档案；定位可通过对话共建；素材档案上提到定位根 | 数据迁移后既有功能不回归；每个渠道明确定位归属；定位 → 素材 → 产物关系可查 |
| 回访型 home 与运营闭环 | 回访态呈现选题管道、最近产物和渠道状态；首次态仍由配方卡接住；home 不新增第二创作意图面 | 定位 → 选题 → 生成 → 精修 → 发布全链联调；多定位 × 多选题 × 多渠道 × 多语言组合完成质量验收 |

R5 虚拟视频仍是已拍板的 AI 生成能力，先作为平台 tool 落位；画廊座位须按 `RECIPES.md` 的真实场景与真实成对示例闸门重新取得。R5 未实现不等于需求取消。

### 1.2 商业化与分发（排期挂起）

支付、订阅、权益、用户计费中心、渠道联调及 hold GC / cache identity 的范围和依赖见 §0.3 与对应合同。支付商、平台开发者权限和公司主体审批是外部前置；未重启前不倒灌为 Film 试用的完成条件。

### 1.3 法务、合规与上线准备（PLANNED）

- 法务页面、用户协议、隐私政策、Cookie 同意；律师人选、文书与预算仍是外部依赖。
- AI 内容标识：导出文件携带机器可读标识，合成轨道与纯剪辑按 `DECISIONS.md` ADR-026 分级；披露随发布携带。
- SEO、验证码邮件域名认证（SPF/DKIM）、数据生命周期说明、错误/可用性/API 成本监控。
- 性能压测必须覆盖多定位/多选题并发与失败不扣费；上线回归覆盖 chat、plan、generation、editor、persona、topics 与全部已开放配方通路。
- go/no-go 前需端到端上线演练和 2–3 名真实用户走查；已知阻塞、未验证项和回退条件必须进入评估材料。已落码不等于真实旅程通过，更不等于正式上线。

### 1.4 当前排期决策

当前 go/no-go 目标日与最迟回退位存在冲突，需总监确认目标日期和范围压缩方式；具体决策与外部依赖见 §3。未拍板前，目标日期不作为完成承诺。

## 2. 需求池（未排期，常驻）

> 未进入当前主线的已登记需求。已完成项直接移除；触发条件驱动的需求见“可选需求”，明确后置的见“明确不在本周期”。优先级和依赖变化时就地更新，不保留需求拍板过程。

| 需求 | 优先级 | 依赖 | 来源 / 备注 |
|---|---|---|---|
| 首发推荐分：维度明细 | P1 | 首发推荐分已持久化；与 `tasks/output-quality-verify.md` 的覆盖范围对账 | 结果网格展示评分维度与理由；规格来源 = DECISION_MATRIX §B、STRATEGY §2.1 |
| persona 校准打分 | P1 | 内部源 = 用户选用行为 + operations 编辑痕迹；外部发布回流不在当前周期 | 定位根落地后校准对象为定位的人设分区；规格来源 = DECISION_MATRIX §G、STRATEGY §2.1/§2.2 |
| LLM 滚动摘要（超长会话历史） | P2 | 先用 `scratch/context_budget_audit.py` 观察窗口折叠真实溢出率 | 当前仅滑动窗口折叠（`chat.context_budget_tokens`）；没有早期引用丢失的真实发生率证据前，不新增摘要生成 |
| 结构化节拍图 + clip-spec motion 枚举 | P2 | 覆盖问责能力；仅限 video 源 crop 动态预设 | 实施前新增 ADR，划清与 stills Ken-Burns 拒绝边界；规格来源 = STRATEGY §2.5 |
| 去静默 / 去口头禅 | P2 | 词级时间戳；随 editor 一键操作方向评估 | 保持专业知识表达密度，避免跳剪损害自然感；取舍来源 = DECISION_MATRIX §E |
| LLM provider 抽象 | P1 | ADR-025 边界；第二 provider 的触发可为代码/视觉能力、成本或 EU 驻留，按实际消费者接入 | 用户面是“优先 EU 托管模型”等策略开关，不是模型 SKU 货架；provider 失败在边界归一，消费方不猜异常来源（`research/deepseek-harness.md` §3） |
| 字幕翻译 + 校对视图（side-by-side） | P1 | 多语言输出能力 | 对照校对交互来源 = DECISION_MATRIX §G |
| 多语言文案质量（跨语言风格保真） | P1 | 术语表（见可选需求） | 保留用户写作风格，不把音频 voice 概念混入文风；规格来源 = DECISION_MATRIX §G、STRATEGY 牌 4 |
| 产品度量地基 | P1 | 无 | 建立上传 → 生成 → 精修 → 发布 → 回流漏斗埋点；指标契约归规划中的 `METRICS.md` |
| 真实 Gallery（公开项目流入 + remix） | P2 | `projects/outputs` 公开性字段先登记 MODULE_ARCH §4 并通过 ADR | 公开项目可序列化为 RECIPES §7.1 数据包并进入 remix；启动条件与权限边界 = STRATEGY §5「当前边界与 deferred」 |
| 虚拟视频卡（画廊候选） | P2 | §1.1 的 R5 能力 + 真实成对示例 + RECIPES §4.8 闸门重过 | 出列不等于否决；只有真实知识专家场景与产物证据成立才恢复画廊座位 |
| 使用示例跑一遍（demo 素材试跑） | P2 | 试跑限次或免费额度；复用 `demo/uploads/demo_talk.mp4` | 用户显式点击示例后才进入同一 chat 主线；自动 Start 仍须制作意图与费用守卫，不建独立通道 |
| 模型 EU-hosted 选项（Mistral 等） | P2 | LLM provider 抽象 | 与 EU 客户驻留要求联动 |
| 渲染服务源站限速韧性 | P2 | 无 | 当前缓解 = 渲染进程 `HTTPS_PROXY`；长期方案 = 源下载落盘再渲染或 renderer 显式 proxy dispatcher，避免直连 TOS 限速导致取帧超时 |
| persona 精修 chat 化 | P1 | 定位根落地后入口挂到定位的人设分区 | per-field 再提炼必须有 merge 语义，保留手改；对话微调只有 persona 级一个入口，不给每模块各加气泡；不得让 `generate` 全量覆盖用户修改 |
| persona AI 印象摘要字段 | P2 | 现有 persona 提炼链；摘要进入 `PersonaContext` 与表列 | 概览卡顶部增加一句 AI 生成画像；现有字段拼装视图不因此回退 |
| insert_broll 技能 | P1 | ADR-044 layers 契约；排在 reframe spike 结论之后 | 面向用户自己的幻灯片/截图；LLM 只做语义定位，机械工序选页与取窗后生成 layer 条目；不扩成 stock B-roll 库 |
| run 收官散文兑现核对 | P2 | 先核对 `run_completed` 触发回合是否已兑现 | 目标行为 = 按 ADR-135/141 的当前分支只陈述确定性 delivered/partial/failed、真实产物与费用事实；不强制默认建议 pills 或唯一下一步，不伪造主观质量判断，不新增第二进度面。已兑现则关闭本行，未兑现则保留缺口 |
| landing 叙事骨架重构（六幕 + 商务尾） | P2 | 足够真实产物密度；当前仍缓做 | 结构、背书插槽与文案纪律归 `LANDING.md` §4；证据归 `research/flora.md` §2 |
| reframe per-clip 检测缓存 | P2 | `speaker_map` 素材级事实作缓存源 | 同素材多 clip 复用检测，避免每 clip 重复探测与计费 |
| speaker_map 本人含量门禁 v2 | P2 | 多人话轮归属可靠性经过真实素材验证 | 只从用户本人话轮学风格；未实装，来源 = ADR-045 |
| morph 罕见拓扑双渲染 | P2 | 无 | non-fork → fork → non-fork 且无 producer 的链形中，抑制与 rescue 可能重复支付一次渲染；需消除重复执行 |
| pre-fail rescue 步骤标签纠偏 | P2 | 无 | rescue 重挂的 render 步骤不能误标 `skipped: upstream failed`；只修展示真值，不改变产物语义 |
| reframe 检测窗残毫秒竞态 | P2 | 无 | 增量重放已覆盖主要并发编辑窗口，仍需关闭检测窗内残余竞态 |
| undo 重挂的陈旧 MP4 处置 | P2 | 产品拍板“清理还是保留” | undo 触发重渲染后旧 MP4 仍挂产物行；决定产物身份与清理行为，并移除对应死代码 |
| 编辑器 staleness 模型统一 | P2 | 无 | 统一编辑器对 run 中途变更的感知与刷新语义 |
| 定点 reframe 报价虚高 | P2 | 无 | `reframe_clip` estimate 应按 `target_output_id` 目标集求和，不按全项目 clip；当前属于展示偏差 |
| 字幕简繁归一跟 `target_language` | P2 | 先拍板 ASR 逐字保真与展示一致性的边界 | 避免同一帧简繁混排；字幕层按目标语言归一，不静默改变需要保真的源文 |
| agent 调用台账（`agent_calls`） | P1 | 会话层已有 `conversation_usage`；本项补 run 层调用事实与取证 envelope | 每次 provider 调用（含空内容、max-tokens、校验失败首试）记录 agent/run/step/attempt/outcome/tokens/error/prompt 模板与 usage；可重建渲染后 prompt/schema/上下文哈希，大 prompt 走对象存储；同时支撑 repair、质检违规与 edit-ops 归因。作为 R1.1 成本校准前置，动工时补 ADR |
| 闸门编目（invariants 登记表） | P2 | 无 | 登记出生地校验、启动自检与运行时数据闸的名字/位置/统一拒绝形态；无闸模块显式说明理由；闸只断言自有数据关系，不断言服务或方法存在 |
| LLM 录制回放层 | P2 | agent 调用台账，共用 MiniMaxClient 边界 | 在适配器 seam 录真实 provider 流并无密钥回放，供确定性回归与 transcript diff；真实剧本矩阵继续承担行为探测 |
| 执行中自适应重规划 | P1 | interrupt、计划 refine、素材理解与 agent 调用台账 | 节点事实与当前计划假设冲突时自动 interrupt，模型重 authoring，展示 diff 并经确认后续跑；信息超出理解 schema/单节点参数域或 retry 不中时升级，素材不足诚实降级。不是开放式 tool-loop，模型驱动拓扑编排仍禁止 |
| “AI Generated”标识偏好与合规边界 | P2 | 合规包；先与 ADR-026 对账 | 可选视觉标识可采用默认开、设置可关并说明修改位置；自动分级、机器可读 C2PA 与法定披露不能被偏好关闭，也不依赖发布通道 |
| TRANSCRIPT 资产生产侧语言印记 | P2 | 消费侧已读 `meta.language` | transcript/docx/pdf 等文本 processor 完工时写入语言探测或上传者声明，给纯文稿项目提供源语言锚 |
| verify judge QuoteReadability schema 兼容 | P2 | agent 调用台账可提供 outcome 取证 | 兼容 MiniMax 可能返回的 per-quote 裸数组与 pydantic object：对齐 prompt/schema 或在边界归一 wrapper；judge 失败不得伪称质检完成 |
| `media_text_fallback` × repair 组合漂移 | P2 | agent 调用台账提供 funnel 取证 | 媒体降级应在 attempt 内发生；schema 拒收不能既消耗 repair 轮又保留未降级的 parts payload。修正后核对 clips 与 registry 两处 `media_text_fallback=True` |
| 步骤级 LLM 命名（per-task `name`） | P2 | ADR-058；排期窗口待指认 | `name` 进入 TaskItem 与 builder 写口，RunTaskList/打勾流读取；`taskLabel` 推导只作回退，手改仍撤名 |
| stub 塌缩（“No source material”行） | P2 | 无 | 无素材 writer-only run 的 stub 行不渲染 |
| mobile OutputChatCard 核对 | P2 | 无 | 核对移动端产物卡在 `runTitle` 章名与当前锚卡机制下的读法一致性 |
| MG 与代码画面创作 | P2 | 已归 Video Project B-I～IV | 原生对象动画与 Generator 程序画面沿 design_video/revise_video/produce_video 共链；范围与出口见施工合同，不另建 generate_motion_graphics 产品链 |
| 刀 A overlay 词汇扩展 | P2 | 现有 ASR / speaker_map / beat_map 与 overlay 契约；逐项验收后上架 | 按“一行扩展配方类型”增加词汇，不把 film-spec 的全幅生成链复制成第二套 overlay 系统 |
| Film 帧级精细估价 | P2 | 当前秒级简式估价与确定性帧分配 | 报价使用实际帧/复用范围，保留 NULL 不可报价与守卫线；不得为精确总价伪报未出生的渲染 fanout |
| Film 独立 prompt_gate 探针族 | P1 | 现有 prompt_gate 与 Film 工具注册表 | 增加 Film 专属的呈现、版本、拒绝、grounding 与授权形态探针；先校准读数，绝对阈值不得为放行回归下调 |
| 个人创作 Skill | P2 | Video Project 阶段 C，依赖已声明内容能力 | 保存/调用/导入创作方法，可包含已支持的 Generator 来源和参数；外部脚本不自动执行，受控视觉程序按 VIDEO_PROJECT §8.1.1 生产，业务引擎与权限仍由系统掌握 |
| 对话剪辑工具族（cut / stitch / reorder） | P2 | 两站机制；复核 L3 边界 | 以 video×editor + chat 修订提供对话剪辑；只扩 agent 工具，不建设多轨 NLE，专业需求仍导出剪映/Premiere |
| 能力画廊 generate/edit 分组徽标 | P2 | 节点 prototype 属性 | 从注册表与媒体入边派生 generator/editor 展示分组；不把该轴变成节点 type |
| quotes/carousel 两站拆分 | P2 | 两站机制 | 拆为文案稿 table×manual + 图装配站；改文案不重新购买图渲染，billing 应显示 renderer capture 为 0 |
| 样式覆写 UI | P2 | `style_overrides` JSONB 地基 | 支持皮肤六件之外的 run 级覆写；卡面控制形态与数据层同批设计 |
| 分镜表表格档节点 | P2 | 表格档节点与编辑映射 op 设计 | 持久化槽位与覆盖理由；删行 = 弃选、改时间窗 = 重切、改论点 = 重选，均为确定性 op；保留用户原话 |
| 画布存在证据走查 | P2 | 运营端上线后的真实用户池 | 邀 3–5 名目标用户完成多产物、隔天修订、来源核对；观察是否借画布理解产物关系，证据不足则收敛纯 chat；审美偏好不触发结构翻案 |
| 超出有界子页发现的自动 discover | P2 | 当前仅承诺同 host + BAD_LINK 过滤 + 最多 3 个子页；扩展需显式多 URL 高频使用，且每页独立清单/来源标注方案就绪 | 当前有界子页验收归 Film execution §1.1 D；只有真实需求证明不足时才扩根页抽链，避免无关页稀释 grounding |
| 能力缺口喂给（decompiler gaps → 需求池候选） | P2 | 积累 CraftGap 观测后按价值排期 | `unsupported` 永不承诺；`not_yet` 是契约已有座位但写手未到，可作为需求候选；旅程二负责带理由纠偏 |
| Turn budget = iteration cap + wall-clock deadline | P1 | 现有 turn_state 与准入门 | `max_iterations` 还需墙钟 deadline，避免多轮 quiet read 拉长 abort/超时与 trigger 竞速窗；到期采用诚实降级，不借机引入新的 AgentBudget 架构 |
| turn 级事件可观测性落库 | P2 | agent 调用台账 | 将拒绝轨迹、异常类与耗时剖面落 DB，使回合中途死亡可诊断；不是另存一份 stdout 日志文件 |
| 画布可读性（同族链分组 + 长边路由 + 居中） | P1 | Product Flow Alignment Batch C | 剩余 = 项目页 groups、asset→asm 跨列长边路由、settled 路径居中；不得为排线创造语义节点，验收用 5 秒三问；若合同已完整吸收则关闭本行 |
| 零探索退化形态 | P1 | ADR-089 §8 迁移弧与 edit_graph 退役证明 | 范围清晰的请求直接生成单 Content Plan，不经探索链；随后退役 `propose_tasks` 与 `select_clips` 的 LLM 可见性，不改变付费授权边界 |
| 深度 reviewer / 看片复核 | P1 | Video Project B 支撑增量；规则见 VIDEO_PROJECT §8.5 / §11.3 | 先直接抽取成片关键帧，跑通一次问题发现/修订/复核；复用现有机制，模型意见不作为未经校准的新审批门 |
| 常驻自主拨盘（standing autonomy dial） | P2 | R1.1 商业形态明确后评估 | 可设常驻额度信封并在设定时披露费用语义；不恢复 review 档，不创造制作意图，也不绕过 `always_confirm_above` / NULL 不可报价守卫 |
| 选项唯一座位（消息流零选项，ADR-100） | P1 | 现行规则 = CHAT_ARCHITECTURE §8.5/§8.8；验收 = 验证登记 §4.1，排期窗口待指认 | 固定选项全部归 dock，trigger 建议 dock 机器保留；收窄 ADR-099 的 suggestions/answer 面，probe I 改测新目标，路由安全零容忍与 substrate 排查方法随合同迁移 |
| Canvas 密度组织学（journey 分组 / 折叠 / 归档） | P2 | `journey_id` 身份前提（ADR-088 §10） | 多旅程候选、精选、方案与产物累积后提供呈现层分组/折叠/归档；不得为组织创造语义节点 |
| FRAMING 默认参化 | P2 | 先验证 caption_mode 默认参化的同构性 | 访谈/单讲的镜头选择可改为推导默认 + 卡面事实 + 手改通道，减少 blocking ask；需保留用户显式选择 |
| operations 用户级 undo/restore UI | P1 | 现有 REST undo/journal/restore 与归档 409 | 不新增 `undo_edit` chat 动词，不做完整 version UI；只在卡面 factsbar 或产物档案提供最小回滚入口 |
| `set_caption_visibility`（edit_output 第五件） | P1 | 前四种编辑形态经过野外观察 | 与 `caption_enabled` 计划默认对账后再定参数形状（ADR-090 §1） |
| 失败渲染触发 reaper 重跑的副作用 | P2 | 图生命周期与重试语义 | 核对“节点滞留 running → reaper 重跑 select_clips → 整链 wipe 再生”是否仍可复现；目标 = 渲染失败落 failed 并可重试，而非全链重跑；重试不得绕过授权与计费守卫 |
| 未复现异常留观 | P2 | 下次 live 验收窗口 | 曾登记“run TIMEOUT 但渲染 completed”与“多义问题待决时带 pin 编辑 /chat 500”；后者用 `scratch/repro_chat_500.py` 未复现。只有重现后才升级为已确认缺陷并取证 |
| 归档 version 存储成本观察 | P2 | 归档写门持续产生真实版本后观察增量 | 归档文件是回滚物理基础，当前仅随项目删除 GC；有存储曲线证据后再评压缩/清理，不预设删除版本 |
| R1 残留（remix e2e + fixture 地基） | P2 | 真实 Gallery 的 remix 通道 | 补 remix 全链 e2e（矩阵 S10 座位）并复位剧本 fixture 地基；不重复登记已由其他合同覆盖的触发/出生机制 |
| 工作请求的非空 bare answer 代码 floor | P1 | 当前 ToolLoop/propose_turn；空 bare-answer 已有修复 | 非空无工具回复仍会作为 answer 持久化。需裁决何时工作请求必须有代码侧“未执行”兜底，同时保留合法信息回答与 Film 方向讨论；这是待取证/裁决项，不作为已证实 release blocker |
| @output pin 强制覆盖的自然分歧验收 | P2 | 当前纯件已覆盖 pin≠模型目标 | live 已验证钉非焦点目标，但“模型自选与 pin 不一致”的分歧分支尚未自然复现；补 live 证据或明确接受纯件验证层级，不把未自然触发写成缺陷 |
| bare-answer 的 mention pin 持久化核对 | P1 | 当前 mentions 注册表与消息持久化路径 | 旧记录显示 pin 只随 PendingPlan 写入时 bare answer 可能丢失；先复现，若仍存在则让 pin 随用户消息独立持久化，刷新不得蒸发 |
| fenced 残留清理（孤儿媒体 + 孤儿问题） | P2 | 存储 GC 与问题生命周期设计 | 只清理可证明孤儿的直传媒体与 fenced Suspend 问题；不得误删用户内容或审计证据，保持 fenced 零副作用 |
| 跨项目 decompile 首见通知 | P2 | 产品拍板“复用命中是否按本项目首见发声” | 当前按 conversation/trigger/ref 去重；跨项目复用时不得重复打扰，也不能让本项目理解状态被误称已呈现 |
| 结构级 remix 产品承诺 | P2 | 先评审参数级 remix 的真实用户证据 | 决定是否承诺骨架时序结构复用；未拍板前只保证当前确定性参数消费，不把 CraftSkeleton 内部结构当上屏方案 |
| `select_clips` 整族删除范围复核 | P1 | 产品语义评审 + 当前图/产物生命周期 | run authority 只阻止并发误毁，不等于删除范围合理；核对重跑会删除哪些既有产物、发布与操作历史，未拍板前保持现有限制 |
| 多活跃 run 产品终局 | P2 | 删除范围与跨 run 修订语义先明确 | 当前仍为 project `{PENDING,RUNNING}` 至多一个 owner；是否放宽是独立产品决策，不得由技术重构静默改变 |
| understanding 复用身份 | P2 | C1 skeleton cache identity 的评审结论 | 评估 `_find_reusable_understanding` 是否需要同类 hash/version/并发治理；不与 C1 搭车隐式扩 scope |
| 纯 pytest 基线复核 | P1 | 纯函数套件全绿承诺 | 上次未销号范围 = decompile / graph_wiring / import_direction / wire_tiers；旧数量与归因不作当前事实，需在当前 HEAD 重新运行并按真实结果归位 |
| trigger beat ③ 引号例句（prompt 卫生） | P2 | `trigger_system.j2` beat ③ | 引号例句可能被照抄，需改成风格/原则约束；不新增禁词补丁 |
| 能力菜单欠卖（dub_clip / remove_filler） | P2 | `_MENU_PHRASES` | dub_clip 应说明声纹克隆，remove_filler 应覆盖 repeated takes；措辞先从完整 procedure 核对真实能力 |
| 建议发射率与 substrate 排查 | P1 | 随 ADR-100 改靶；gate 仪表与 stub execute | probe I 不为放行降阈；路由劫持零容忍，探索问缺少下一步才计失败。固定模型/参数/场景重复采样并保留原始输出 → 工具调用 → 应用处理，区分模型未提、未调用与被丢弃；补 `answer-args-invalid`，语义失败先人工标注 |
| 发射层 / provider 方差受控复测（S5 族） | P2 | 与建议发射率共用取证面 | 固定模型/provider/温度/工具/输入/初始状态重复采样，按失败签名记频率；区分采样波动、prompt 不足、应用处理不稳与评测器过敏，不用单次绿红直接归因 |
| 评测系统语义三修 | P2 | `reply_quality_probe` 当前基线 | ① 未确认却暗示开工需独立语义断言；② 被拒绝备选作上下文说明为合法，误述为可选才失败；③ S-adv 增加 `deferred/awaiting-prerequisite` 合法座：说清缺口、不伪装结论、不虚构执行、前置满足可续做。禁固定禁词表 |
| fill-keys 读面口径（research facet 折叠 × S1） | P2 | ADR-097 §3 读面行为 | 先拍板 research 节点 stamp 为 facet 后并入 deliverable 卡组是否正确，再决定修 read model 或 S1“同节点原地填充”断言；不得为放绿直接改断言 |
| 分镜发布座接线（`on_row_append`） | P1 | 先与 Film 当前实现对账 | 若仍无调用点，需让分镜独立消息行在长设计回合内直播落地；row.append 与信封 finalizePreview 要有双渲染去重，reconcile 覆盖断流窗口，文档行仍遵守打字机律 |
| film birth prompt 冻结义 | P2 | 先与 Film 当前实现对账 | 无前置挂单时，`PendingPlan.prompt` 应回溯最近的生产意图句，而不是把“ok”等当回合确认文本冻结为求片 prompt；指纹与 Start 兜底语义不得回退 |

### 可选需求

| 需求 | 可以考虑开发的情况 |
|---|---|
| 术语表（固定译法 + 配音发音，约 2 天） | 机构客户对多语言译法一致性、配音发音提出明确要求时 |
| 管理后台最小版（用户 / 用量 / 手动补偿，约 3–5 天） | 上线后运营与客服开始需要后台工具时 |
| 帮助中心内容（约 2–3 天） | 用户自助咨询增多，或机构评估需要产品文档时 |
| 邀请 / 分享回流（约 3–4 天） | 需要启动口碑增长时 |
| 链接导入（Zoom / Drive 持续摄入素材） | 机构客户要求从他们的会议和网盘直接拉素材、不愿手动上传时 |
| YouTube 导入 | 目标用户素材大量在 YouTube 上、且反爬成本评估可控时 |
| 团队协作空间（多成员 / 多人设） | 出现团队型客户、多人协作成为成交条件时 |

### 明确不在本周期（取舍有据）

被外部 agent 调用（MCP）、专业剪辑交接格式、定时发布 / 团队审核 / 发布数据回流、newsletter 集成、欧盟数据驻留。均为已登记项，本周期结束后统一重排。

---

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
