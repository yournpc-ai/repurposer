# Agent 交互架构迁移 — 施工简报（ADR-099）

> Status: **迭代一已收口**——批次 B（`cfb3488`）、C·C+（`05e81ba`+`1cbdad6`）、S（S-int-1..9）落地且验收已跑（批次 S 验收节在册：S-core 9/9 绿、gate 11 探针全绿、legacy 9 红全部归因）；C·C+ 账判软项（承重观察⑥）由用户拍板并入批 D 首批同批修。**迭代二（D/E）开工**，交接提示词 = `apps/api/scratch/handoff-iter2-speech.md`；G 未动工。
> 架构母法 = ADR-099。**验证纪律：一切 pytest / prompt_gate / 剧本 / live 复跑由用户自跑**；施工会话只做代码层分析与 review，未跑项在批次 Status 在册。

## 冻结事项（本简报全程不再议）

四档终态交互形态；宪法六条；禁模型自报状态（无 mode/commitment/blocking 字段）；suggestions 非承诺语义；provenance 永不覆盖用户原话；DeferredFrames 基本方向（乐观缓冲，非悲观串行）；禁 token 级安全段分类器；禁 NLP 解析散文对账；禁 browse lane；禁独立 Decision Contract 层；不建全局世界版本系统（source_state = 定向校验，ADR-099 §4）；不清洗在途会话历史。

## 批次总序与承重论证

```
B → C·C+ → S → D → E → G1 → G2
```

- **门禁单调律（最高施工约束）**：任一批次的 gating test 只依赖**已落地**能力。由此 S 只含 C·C+ 后即可转绿的场景；事故①②回归场景随 D 入座、事故③回归场景随 G1/G2 入座——剧本集是累积的，每批带自己的场景来。
- **E 必须在 C·C+ 与 S 之后**：谱系不就位时浏览问无档可去，删 lane 探针必红——红因是工具缺失不是文本承重；且 ablation 只在新架构 suite 上有意义（旧 suite 为旧车道行为验收，green/red 均不可解释）。
- **C 与 C+ 一个 release unit**：谱系改变工具面（catalog 进 prompt），C 单独基线在 C+ 落地时必然失效——两个 commit、一次发布、唯一基线。
- **B 合并验证后才动 C·C+ 与 G**：三批同触 `plan_turn.py`/`propose_turn.py`/`service.py`，交叉 diff 无法归因。
- **归因隔离律**：G1（说错了）与 G2（什么时候说错了）严格分批——出问题必须能区分是措辞还是时序。

---

## 批次 B：caption gate 拆除

| 字段 | 内容 |
|---|---|
| **scope** | 杀"用户还没选方向、字幕闸先问"的阻塞机械。仅此而已。 |
| **files** | `plan_turn.py:823`、`propose_turn.py:513`（删调用+dock 组装）；`service.py:688`/`:828`（删 `_needs_caption_mode_question`/`_replay_stashed_caption_intent`，先全仓 grep 确认无其他消费方）；`intent.py`（stash 链如专属随删）；`intent_router_system.j2`（caption_mode 参数文档改写）；前端方案卡 derived preview 字幕模式事实行 + i18n en/zh |
| **depends_on** | 无（独立批，完整验证合并后才允许 C·C+/G 开工） |
| **must_not_touch** | suggestions 一切；streaming/DeferredFrames；宪法；其他参数系统（**不升级为参数架构重构**）；FRAMING（批H 需求池行，不随批）；repair 文案 |
| **acceptance** | 复用既有设施，不新造：`Literal["bilingual","source_only","target_only"]` 校验（schemas.py:673）与 `_caption_choice_is_meaningful` 推导保留；漏斗 = 用户原话 > 暂存 > source_only；Start 经 Confirmed Scope 读**当前卡面值**（非旧 InferredIntent 副本）；手改骑既有 prior_intent 通道。① 无字幕关键词走金句卡配方 → 无 dock 问、卡面见默认行；② 用户原话"双语" → 模型 set 值优先；③ 一句话手改 → 重 dock 生效 |
| **rollback** | 单 commit git revert；探针红 = 恢复被删闸门并登记承重发现 |

**批次 B 落地记录**（施工会话交付，验证全部未跑）：

- 删除面：plan_turn / propose_turn 的 caption 闸门 + dock 组装；service.py 的 `_needs_caption_mode_question` / `_build_caption_mode_question` / `_recover_caption_mode_from_answer` / `_has_resolved_caption_mode` / `_is_caption_mode_question` / `_replay_stashed_caption_intent` / answer fast path / SOURCE_ONLY·TARGET_ONLY 关键词表。grep 结论：stash/replay 无 caption 以外消费方（stash 只经两座 `_dock_question(intent=…)` 写入、answer fast path 唯一消费）；intent.py 无 caption 链（零引用，未动）。
- 漏斗落代码：`_derive_chat_caption_mode` 为唯一推导座（registry-native DerivativeWriterNode 链检查内联）——关键词 > 前 dock 值（`_resolved_caption_mode`）> source_only；**source_only 仅在 `_caption_choice_is_meaningful` 为真时盖戳**（该推导件的新座位 = 默认可见性：有独立第二语言才有可选的事实行；无则零戳、卡面静默，runtime narrowing 在 dispatch 自收窄 bilingual → source_only）。
- 模型面文档双座同法同批：intent_router_system.j2 参数行 + schemas.py `PresentPlanArgs.caption_mode` Field 描述（后者是 tool spec 参数文档本体，"None = chat should ask the user" 不改即成谎——简报只点名 j2，schema 座为同法补齐）。
- 前端方案卡 derived 区增字幕模式事实行（`captionModeRow`：链含 captionMode 标记工具且 intent.caption_mode 有值时渲染；TOOL_META 增注册式标记；i18n `derive.captions`/`source_only`/`target_only` en/zh 双写）。桌面端不渲染计划卡（既有律），事实行座位 = 移动端卡。
- 场景座同座换法（非迁就）：`s7_caption_mode_gate` → `s7_caption_mode_default`（A 无关键词→无问+source_only 端到端 / B 原话双语→bilingual 端到端 / C 设定→追问→面板 Start 继承）；`answer_caption_gate` 助手 + `caption_gate` terminal 判别式随删（9 调用点）；S22 竞态座换驱动（caption 答复 → 用户次轮回合 dock 计划，确定性论证同形）。
- Start 链路证据（当前卡面值，非旧副本）：dock 时 plan_turn 以漏斗结果建 InferredIntent → PendingPlan.intent + task_book 行 intent 列 → 前端 normalizeIntent 原样往返 caption_mode（chatProtocol.ts）→ Start `intent = (data.intent or pending.intent)`（面板当前值优先）→ 缺字段时从 stored pending 继承 → `TaskSpec.caption_mode` → run.context。stash/replay 删除后全链只剩这一条 intent 血统。
- **未跑验证（用户清单）**：① pytest（含新增 `test_caption_mode_funnel_pure.py` 漏斗锁）；② prompt_gate（caption 参数文档改写为全局扰动面）；③ chat_scenarios 全量（重点 S7 新三拍 / S19 / S20A·B / S22）；④ web tsc + 构建；⑤ live：无字幕关键词走金句卡配方（无 dock 问、卡面见默认行）/ 原话"双语"（set 优先）/ 一句话手改（重 dock 生效）。
- **承重观察**：S22 未 seed understanding——触发回合若因世界不足而无话可说，`review is None` 会呈空洞绿（既有形态，非本批引入）；recipe 卡 quote-cards 模板自带 "bilingual" 字样，走模板原文 = 用户原话命中关键词，默认吸收只覆盖用户自拟无关键词的通路。

---

## 批次 C·C+：交互宪法 + 形态谱系（一个 release unit，唯一基线）

| 字段 | 内容 |
|---|---|
| **scope** | 交互宪法六条+准入闸落地；answer 增 suggestions 非承诺档；点选 provenance；唯一基线测量 |
| **files** | commit 1（暗置）：`schemas.py`（`ChatAnswerArgs`:828 / `PlanAnswerArgs`:699 增 `suggestions: list[SuggestionItem]`，复用 :997 契约，validator 抽共享）；消息 JSONB 交互块持久化；`trigger_turn.py`（trigger 建议切同一块，修既有缺口）；点选 `suggestion_ref` 发送路径（复用 mentions 模式）；落地时刻定向 stale 校验。commit 2（启用）：新增 `_interaction_constitution.j2`；三 system prompt 各一行 include；`turn_tools.py` answer catalog line；router/chat_intent answer 契约段 suggestions 边界；`interaction_policy_version` 戳 |
| **depends_on** | B 已合并验证 |
| **must_not_touch** | 不删任何旧 lane 文本（D/E 的事）；不动执行面（create_run/编译/队列）；不动 DeferredFrames；不动 repair 文案与 activity 措辞；不动其他终态工具语义 |
| **acceptance** | **两 commit 合法性**：commit 1 独立编译完整、行为零 diff（catalog 不广告 = 模型永不可发射 = 无半成品协议用户可见，**catalog 即开关，不需 feature flag**）；commit 2 = 行为翻转隔离。两 commit 可分别 revert——不为 git 好看而拆，若做不到零 diff 则合并为单 commit。**唯一基线**（两 commit 都落地后）：prompt_gate + 全量 chat_scenarios 对 B 后基线漂移≈零；翻剧本 → 调措辞，不前进、不回调阈值。live 事故④复跑：浏览问 → answer+建议卡，无 present_plan、无字幕问；点选 → 下回合带 suggestion_ref 编译；stale 点选 → 具名标注不静默采用；用户手改原话恒压过候选载荷 |
| **rollback** | revert commit 2 = 回到谱系前行为（commit 1 暗置码留库无害）；需全回滚时按 2→1 序 revert |

**suggestions 载荷边界（schema 硬约束优先，不靠 prompt 自觉）**：携带 = 方向 + 一句理由 + 证据来源（如 beat anchor 区间）；禁止 = 语言/字幕模式/时长/画幅/条数/成本/具体 recipe/任何可直接组成 present_plan 的执行承诺。实现 = `SuggestionItem` 既有 ≤40 字符 label 校验 + 探测期内容 lint 断言；**不新建大 validator framework**。

**source_state（ADR-099 §4）**：零计数器——stale ⟺ ① 依据素材已删除/失败 ② source_turn 后有新素材理解落地 ③ source_turn 后有方案 dock 或 run 开工；点选时刻定向查询，全部由已持久化字段驱动。

**批次 C·C+ 落地记录**（施工会话交付，两 commit `05e81ba`+`1cbdad6`，验证全部未跑）：

- commit 1（暗置）：schemas 两座 answer args 增 `suggestions`（共享 `dock_worthy_suggestions` 校验——WrapUpArgs 语义零漂移，纯测试锁实证）；`SuggestionRef`/`SuggestionRecord` 契约；messages 表 `suggestions` JSONB 交互块 + `suggestion_ref` 列（migration `p7c2d4e6f8a1`）；纯核模块 `app/chat/suggestions.py`（record 戳 / stale 谓词 / provenance note 三件，零 DB 零 LLM）；`stamp_suggestions` 单座戳块（plan/propose 两座 `_answer` + trigger `_dock_question` 路径，空集 no-op 保零 diff）；`resolve_suggestion_note` 落地解算（plan/propose 两路装配座 weave 进 LLM-facing message，`self.text` 恒为用户原话不进闸门/关键词检测）；trigger provenance 缺口修复 = answer endpoint `_suggestion_ref_for` **代码重构 ref**（被答行 = source_turn、option id = suggestion id）零 wire 变更；前端 OptionDock 卡渲染（散文排干后落，复用三形态机承重结构）+ 回放重建 + 词表门测试同批登记 `suggestionOptions` 键。
- commit 2（启用）：`_interaction_constitution.j2` 单定义三消费（SPEECH 总律之后、各分则之前，渲染实证各烘焙一次）；两路 answer catalog line 增 0-3 非承诺选项语义；两处 answer 契约段增载荷边界（方向+一句理由+证据来源；禁执行参数枚举；recommended = 当前倾向唯语义）；`INTERACTION_POLICY_VERSION = "interaction_constitution.v1"` 戳盖进 assistant 行 intent dump（`_create_message` 单座；装配器不读 intent 入模型面——实证 `context.py` 零 intent 引用）。
- **零 diff 判据的施工裁定（承重，在册）**：params_model 的 JSON schema 全文（含 Field 描述与 SuggestionItem 嵌套描述）直达模型面，commit 1 的 suggestions 字段严格意义上模型可见——「catalog 即开关」成立的经验依据 = 本仓教义（注册表条目扰动 = prompt 扰动，catalog/契约段才是行为驱动主面）；未被 catalog 与 prompt 契约广告的孤立可选参数不驱动发射。仲裁 = 唯一基线（prompt_gate + 全量剧本）；若漂移归因于自发发射，退路 = Field 描述移至 commit 2 或并 commit。且即便自发发射，commit 1 全链（持久化+渲染）已备，表现为功能提前生效而非破碎。
- **B 验证状态的实证补丁**：纯 pytest 在 HEAD `cfb3488`（B 后、本批前）即 11 红（stash 零假设实证，与本批零交集）——test_decompile（display_name）、test_graph_wiring 六项（524==464 布局族 + transcript queued 族 + read_face exploration 族）、test_import_direction（pipeline→chat import）、test_wire_tiers（reasoning_split vs think_block）。**B 验证状态未知，C·C+ 带此债开工**（交接提示词 §一 已在册）；本批交付时 906 绿 + 同 11 红，零新增。
- **越名单确认结论**：`PresentPlanArgs.caption_mode` Field 描述（B 同法补齐座）与本批一致——"Set it only when the user's own words already name the mode; when omitted, the system derives the default and the plan card shows it as a visible fact the user can change with one sentence"，无 "None = chat should ask the user" 残留；suggestions 边界明确禁字幕模式参数入载荷，两座无冲突。
- **未跑验证（用户清单）**：① 全量 pytest（本批新文件 17/17 绿已跑；全量 906 绿 + 11 红 stash 实证既有）；② prompt_gate（catalog 全局扰动面——先重跑一次排除 provider 漂移再判红；翻剧本 → 调宪法措辞或契约边界句，不回调阈值）；③ chat_scenarios 全量（重点 S7 新三拍 / S19 / S20A·B / S22——S22 空洞绿形态已知勿报新 bug）；④ web tsc + 构建（tsc 已跑：仅 flow/FlowNodeCard、flow/layout.test 两处 stash 实证既有债）；⑤ live 事故④复跑（浏览问 → answer+建议卡无 present_plan 无字幕 dock；点选 → 下回合带 suggestion_ref 编译；stale 点选 → 具名标注；label 无执行参数目检）。
- **承重观察（在册不处理）**：① 前端 suggestion 点选沿用 legacy pill 姿态（无乐观用户气泡、无 rollback 注册）——既有 pill 同形，未随批升级；② trigger 路径的 suggestion_ref 是 answer endpoint 侧代码重构的瞬态件（用于落地解算与 note），未持久化进 answer payload——取证可经 option id + 被答行回join；③ i18n 零新增键——建议卡复用 `questionDock.recommended`，卡面其余文案全来自模型载荷（label/description），符合「展示文案二源律」；④ 版本戳座位 = intent dump（无 metadata 列），material beat / activity log 等直建 Message 的系统行不盖戳（非交互政策产物）。
- NAMING.md §2 五词行（终态交互形态 / 交互宪法 / 言语提交协议 / suggestion_ref / source_state）已随批登记。


---

## 批次 S：新架构 golden suite（S-core）

| 字段 | 内容 |
|---|---|
| **scope** | 只建"C·C+ 后即可转绿"的核心场景；两层分离——Legacy Regression（旧功能不破）与 New Interaction Contract（新架构行为正确），ablation 只在后者上度量 |
| **files** | `chat_scenarios.py` 或同族剧本面（纯新增场景，不改生产代码） |
| **depends_on** | C·C+ 唯一基线已建 |
| **must_not_touch** | 生产代码（发现 bug 另开批修，**禁改场景迁就实现**）；G 族场景（repair 静默 / 被拒言语零泄漏 = G1/G2 带入座，S 不含——它们的能力尚未落地） |
| **acceptance** | **Control**（四形态各一：answer / answer+suggestions / ask_user / present_plan）；**New behavior**（浏览问→answer+suggestions；建议点选→下回合编译；stale 建议→具名不静默；无字幕参数→默认吸收；旧 lane 历史 × 新政策→不出现旧车道腔）；全绿 = E 开工许可 |
| **rollback** | 纯剧本文件，删场景即回滚；suite 本身无生产面 |

**批次 S 落地记录**（施工会话交付，纯剧本新增零生产代码，验证全部未跑）：

- 场景座：`chat_scenarios.py` 尾部 New Interaction Contract 组，9 场景注册为 `S-int-1`..`S-int-9`（命名键随 `S-explore-2`/`S-edit` 先例）；上方 Legacy Regression 零改动；模块 docstring 场景清单同批补行。
- Control ×4：纯信息问→answer 无卡无 dock（空项目两问，suggestions 空穴来风即硬红）/ 带素材探索→answer+suggestions（含交互块持久化断言：source_turn 自锚 + source_state 快照点名依据素材）/ rootless wish→ask_user（措辞随 S1 实证面，新项目重试防历史带偏，present_plan 硬红）/ 点名工作→present_plan（S7 同构只锁形态，bail 收尾零 run）。
- New ×5：浏览问事故④回归锁（先建推荐格局再发"还有其他推荐吗"族自定义措辞，present_plan/字幕闸/ask_user 三硬红）；建议点选 fresh 编译（用户行 suggestion_ref 持久化 + 可见文本恒为 label + 预算内落到计划 dock 或决定性闸门 + 收方向永不跳过确认起 run）；stale 点选三谓词全谱（A 理解落地走 `record_material_beat` 本座 / B run 开工走 run 行种子 / C 依据素材删除——世界改造全走真实座位，零手工注入）；无字幕参数金句卡默认吸收（批次 B 行为锁轻量版，不 Start）；旧 lane 历史 × 新政策（DB 直插旧车道腔 assistant 行，锁 verbatim 鹦鹉 + schema/工具 token 漏出两负形）。
- 断言面三件套：终态信封形状 + messages 行持久化事实 + 代码组装文本。provenance note 不持久化不上 wire，唯一诚实观察座 = 进程内重放 `resolve_suggestion_note` 本座（真 DB 状态）——fresh/stale 形态与具名理由串是代码强制文本（提醒尾同例可锁），剧本永不手工拼 note 冒充解算。
- 辅助件：`check_suggestion_block`（载荷边界负形 lint——label 全档/description 收窄档，证据句合法引数不误伤）/ `elicit_suggestions_turn`（方差口径：无卡措辞重试，present_plan/ask_user 错档硬红）/ `seed_keynote_project` / `resolve_note_in_process` / `_stale_pick_round`。
- **承重观察（在册不处理）**：① `elicit_suggestions_turn` 对 ask_user/present_plan 的硬红是本组最脆断言——探索问被模型判成阻塞问或承诺 dock 时红 = 谱系档选择未立（回调 C·C+ 措辞或批 D 的事），非场景松劲；② "不静默采用"的行为面锁到 `run_id is None` 为止——stale 后如何重新锚定是散文高熵面，确定性强锁不可能；③ S-int-9 只锁 verbatim 与 token 负形，旧腔「质感」传染（推荐 vs 指令语气）超出确定性判定面；④ S-int-8 与 S7-A 前半同构（本组自持行为锁的轻量版），参数链端到端仍是 S7 座位。
- **未跑验证（用户清单）**：① 全量 pytest（本批零 pytest 面改动，§既有债 11 红不算本批账）；② prompt_gate（唯一基线：对 B 后基线漂移≈零——本批纯剧本，翻剧本 ≠ 本批引起，先重跑排除 provider 漂移）；③ chat_scenarios 全量（重点 S-int-1..9 + S7/S19/S20A·B/S22——S22 空洞绿形态已知勿报新 bug；**S-int 9 场景全绿 = 迭代一收口 = 迭代二开工许可**）；④ web tsc + 构建（本批零前端改动，§既有债两处除外）；⑤ live 事故④全链复跑（浏览问 → answer+建议卡 → 点选 → 下回合编译；stale 点选 → 具名标注；label 无执行参数目检）。

**批次 S 验收结果**（用户授权施工会话代跑，逐项对账完毕）：

- **pytest**：906 绿 + 11 红——既有债清单逐项命中、零新增。清单更正：graph_wiring 族实为 **8 项**（524 布局族 ×5 + transcript queued ×2 + read_face exploration ×1），总数 11 不变。
- **web tsc**：既有债两处逐项命中，零新增。
- **prompt_gate**：11 探针全绿。probe F 首跑 6/12 触阈（threshold 8），按铁律重跑 10/12 过——provider 漂移实证（摆动幅度 6↔10 在册）；A/B/C/H-H4 满分，D 10/12、E 11/12、G 11/12。
- **S-core 9/9 绿**（收口判据达标）。S-int-5 首跑红：三硬红（无 plan dock / 无字幕闸 / 无 ask_user）全过但三个浏览措辞均收纯 answer 无卡；按纪律重跑转绿。承重观察⑤：**浏览回合建议卡发射率不稳**——首跑 0/3、重跑即中；档选择本身（不劫持）两跑全胜，发射与否是波动面。
- **Legacy 26 本：17 绿 9 红，归因全部在册**：
  - **既有债 A（活动帧白名单漂移，一根四本）**：S6f/S10/S20A/S21A——`922c301` 写死五键白名单，`228a1d1`（09-23 活动帧时刻/耗时批）给帧加 `at`/`duration_ms` 未回更场景；与本迭代零交集。修法 = 白名单回更现行线契约（场景维护批，非迁就）。
  - **既有债 B（探索族漂移）**：S23 确定性 NoResultFound ×2（candidate_set 节点不生）+ S-explore-2 链失速（两跑两个不同失速点：三族出生 / selectsReady 里程碑）；与既有纯测试债 read_face exploration 族同源——stash 实证 `cfb3488` 即红，先于本迭代。需独立取证批定位断点。
  - **既有债 C（S22 时序假设失效）**：落点拍两跑同红——docstring 自注的"罕见反方向只会误红"已常态化：前缀缓存时代触发 loop 快于剧本的 2s+dock 窗口，竞态假设系统性破裂。场景需重定时（另开批）。
  - **S16 remix flake 未分清**：两跑两个不同失败点（ReadTimeout / warm decompile 未言语），需独立取证批。
  - **本迭代账（C·C+ 扰动候选，承重观察⑥）plan 承诺档判软**：clips 类明确点名工作在 S10 首跑与 S5 重跑同形收在散文 answer（散文自陈 "The plan:" 却不 dock，intent 戳 `interaction_constitution.v1` 在场）；S5 首跑另见修订压面板钉失效一次。quote 类点名（S-int-4 ×2、S7 三拍）不受影响——档软化是 ask 依赖的波动，非档消失。处置 = **不修场景**，按 C·C+ 验收既定路径回调措辞（强化「明确点名工作恒收 present_plan——非承诺档是开放探索的去处，永不替代点名工作的 dock」），建议并入批 D 首批同批修。
- **收口判定**：S-core 全绿达标（S-int-5 一次重跑在纪律内）；gate 全绿；既有账全部归因。**迭代二开工许可由用户拍板**——C·C+ 账判软项建议随批 D 首批处理。

---

## 批次 D：trigger 车道收缩 + RANGE 分组叙述禁

| 字段 | 内容 |
|---|---|
| **scope** | 事故①②根的 prompt 修复：beat① 推荐质感重锚、beat④ 删指令质感留介质法；THE RANGE 增"分组方案永不叙述" |
| **files** | `trigger_system.j2`、`_capability_answer.j2`；`reply_quality_probe.py` 增语义角色维度（recommendation→instruction 居首，EN→ZH/mixed→ZH 优先）；事故①②回归场景入 suite |
| **depends_on** | S-core 全绿 |
| **must_not_touch** | schema / tool 语义 / catalog；payload 条款（grounding hierarchy / beat anchor 表格 / suggestions 三件套 / disclosure）；S 场景（红了修 prompt 不修场景）；**混合段纪律：一段同时含 speech shape + payload 时，只抽 speech 重复，禁整段删** |
| **acceptance** | 触发回合剧本 + reply_quality_probe 轮替：事故①②形态清零且 payload 不回退；带入的回归场景转绿 |
| **rollback** | 单 commit revert；探针红 = 恢复该段并登记承重 |

---

## 批次 E：言语法逐簇去重（零假设探针）

| 字段 | 内容 |
|---|---|
| **scope** | E1 收尾问句簇 / E2 FREE PHRASING 簇 / E3 ask_user 形态簇，逐簇 stash 探针删除（router 为主、chat_intent 镜像） |
| **files** | `intent_router_system.j2`、`chat_intent_system.j2` |
| **depends_on** | D 收口（suite 已含事故①②回归） |
| **must_not_touch** | schema / catalog / 契约段；payload 条款（grounding hierarchy / disclosure / DISCOVERY GOALS / 任务组成规则 / rejection 协议 / partials）；S 场景；混合段纪律同 D |
| **acceptance** | 每簇：3 次 smoke（critical 即停）→ 8-12 次关键剧本 → 定点重放（受影响簇+历史事故+邻近边界），baseline/candidate 交错 round-robin；一次 green 不证冗余；红 = 承重恢复 + 登记本简报；**ablation 只判"删文本是否行为回归"，不判"旧 lane 是否仍存在"** |
| **rollback** | 逐簇 revert；承重簇恢复后永不再探 |

---

## 批次 G1：repair 修宪 + rejection 取证

| 字段 | 内容 |
|---|---|
| **scope** | repair 文案修宪（无实质变化=静默/有变化=只说工作变化，永不以自我反思为中心）；被拒调用+feedback 落 activity_log 持久化（现为取证空洞） |
| **files** | `zh.ts:1285` / `en.ts:1368`；`activity.py` / `plan_turn.py` / `propose_turn.py`（rejection 落库）；事故③ wording 回归场景入 suite |
| **depends_on** | E 收口（与 prompt 面改动隔离，防归因混淆） |
| **must_not_touch** | stream semantics / 帧序 / 缓冲 / DeferredFrames（**G2 的地盘**）；prompt 文本 |
| **acceptance** | "已重新整理好"自白形态清零；rejection 事后可取证（调用/原因/迭代序）；带入场景转绿 |
| **rollback** | 单 commit revert |

---

## 批次 G2：言语提交协议一般化（最高施工规格）

| 字段 | 内容 |
|---|---|
| **scope** | DeferredFrames 自然演化为四态机 **OPEN → BUFFERING → ACCEPT→FLUSH / REJECT→DROP→RETRY**（RETRY 陈 buffer 必清），推广到一切可被拒绝的终态调用（`present_plan` echo 首座）；不重写、不建第二套 routing |
| **files** | `deferred_frames.py`、`plan_turn.py`、`propose_turn.py`；事故③ leak 回归场景入 suite |
| **depends_on** | G1 收口（归因隔离：先修"说错"，再修"何时说"） |
| **must_not_touch** | prompt 文本 / 契约文案 / i18n / activity 措辞 / 决策路由 / validator 规则本身；**禁** token 级安全分类器、模型 self-tag、NLP 散文解析、第二套 speech routing |
| **acceptance** | 状态机测试清单全过：reject→零泄漏；retry→只见最终信封；accept→散文/卡帧序稳定（checkpoint 先于 read statements 等既有序不破）；SSE 断连/重连→不重复不丢失；零 delta→paceSettledProse 节拍仍在；两迭代→陈 buffer 清空。方案回合首字延迟 = 校验时长，StatusLine 覆盖死寂（定案，不优化） |
| **rollback** | 单 commit revert；DeferredFrames 素材待命现用法不受 revert 影响（既有能力先于本批存在） |

---

## 总收尾

- 全部批次绿后：`CHAT_ARCHITECTURE.md` 一次性写现行法（谱系表 / 宪法座位 / 言语提交协议 / provenance 契约）；README 信息类型表行转正；NAMING.md §2 词汇行（终态交互形态 / 交互宪法 / 言语提交协议 / suggestion_ref / source_state）随批 C·C+ 登记。
- live 复跑四事故场景（项目 `6b42bd6b` 同形），全绿 = 简报归档 `archive/tasks-done/`。
- 需求池已登记：FRAMING 默认参化（批H 候选，批B 验证同构性后评估）。
