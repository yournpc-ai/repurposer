# Agent 交互架构迁移 — 施工简报（ADR-099）

> Status: **迭代一已收口**——批次 B（`cfb3488`）、C·C+（`05e81ba`+`1cbdad6`）、S（S-int-1..9）落地且验收已跑（批次 S 验收节在册：S-core 9/9 绿、gate 11 探针全绿、legacy 9 红全部归因）；C·C+ 账判软项（承重观察⑥）由用户拍板并入批 D 首批同批修。**迭代二已收口**（用户拍板，GPT 终审吸收）——D（`30174b6` + `2411290`）/ E1 `ddde27f` / E2 `4a226ee` 冻结接受；E3 `58c9449` 经二分归因 revert 落 `70136d8`，该删除面永久关闭不再探；验收单 8 步全跑、红全部归因（无未归因红）；遗留四线独立登记入 PROGRESS 需求池（建议卡发射率 / 发射层方差复测 / 评测语义三修 / fill-keys 读面口径），言语面迁移线冻结——除非出现可复现新反例，不再围绕本批删除做无目标扩展；G 未动工（迭代三前置 = 本收口，已满足）。
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

**批次 D 落地记录**（施工会话交付，单 commit `30174b6`，验证全部未跑）：

- **判软修（承重观察⑥，首批同批）**：定座 = 候选①+②、弃③——两路 answer 契约段（router/chat_intent suggestions 边界句尾）增「本档是开放探索与浏览问的去处；明确点名工作恒收承诺 dock（present_plan / propose_tasks 或修订动词）；散文铺计划不 dock 是本档唯一禁形」+ 两路 answer catalog line 增同义短句。**宪法①条未动**：元律问②（能结构化/契约化吗——能，工具契约即座位）裁定该法不入宪法，判软是档边界问题不是判断权问题。
- **事故②根修**：beat① 「the DELIVERABLE direction you'd take (which output to make first)」→「you recommend making first … the verdict reads as an OFFER the user can accept in one word, never as a decision already made or a go-ahead issued on their behalf」；rejected-alternative 结构、性状否决资格（ADR-094）、one judgment one voice 全保留。beat④「close ON the verdict」→「close ON the offer」（收尾拍 = 同一提议的回落，永不升级为 go-ahead）；介质法全保留（dock 自带问题标题 / 散文永不问号收尾 / 永不预告引出 dock），顺手把引号禁令例（'which direction first?'）抽象化（立法纪律：禁引号示例句，被禁形态用 shape 描述）。run_completed 收尾本已是 offer 质感（offering + default path），未动。
- **事故①根修**：THE RANGE 增一句「The grouping is the answer's skeleton, never its speech: never announce the scheme and never narrate that you are grouping — the labeled groups simply appear」（宪法②执行细节，抽象表述，未引用事故原句）。
- **J6 semantic_roles（仪表非闸门）**：五对角色合一维度（推荐=提议非指令 / 提问=邀请非命令 / 默认值=可改非被迫 / 选项=可选非已决 / 观察=有据非断言；0=任一塌禁态 1=边缘 2=出现的全守位、未出现不扣分），覆盖 S-cap 全族 + S-adv + S-warm；RUBRIC_VERSION 5→6。**语言矩阵** = S-cap 六格（prompt 语言 × Accept-Language 地板；dict 序 = 风险加权序 en→zh/mixed→zh 先行、zh→zh/en→en 基线、zh→en/mixed→en 末位，默认场景清单同序）；地板经 per-request Accept-Language 注入（mirror 律下地板只在无语言信号时生效，mixed prompt 是地板有权重之座）；D2/J5 的 S-cap 适用面同批扩为全族。基线纪律提醒：v6 后旧基线只比共有维度，批 D 施工前基线需以 v6 重存。
- **事故①②回归场景入座**：S-int-10（空项目能力问 ×2 语言——终态 answer + 散文落地 + 极窄机器词负形「归类 / group by the / group these by」+ 零 run）；S-int-11（seed_keynote_project + 进程内 `run_trigger_turn(TRIGGER_UNDERSTANDING)` 确定性点火——无 pending plan 必开口 / 散文非空且永不以 `?`/`？` 收尾（介质法形状锁）/ check_suggestion_block 全谱：1-3 项、id 语法、recommended ≤1、source_turn 自锚、source_state 快照、label ≤40、载荷负形 lint）。断言面分工按施工点 5 定死：场景零措辞正则，推荐 vs 指令判定归 J6。
- **probe I 入座**：gate 第 12 探针——plan 路素材在库（material_excerpt 同 D）+ recent 轮次已建推荐格局 + browse 问（"anything else you'd recommend?"）→ 终态 answer 且 args 带 1-3 suggestions，present_plan/ask_user 零调用（D 族 NEVER-called 断言式；stub 默认接受 answer，无需新护栏）。阈值 8 随 D/E/F/G 先例，**首读数待测**（注释在册：recalibrate from readings, never to excuse）。点选/stale 不入座（跨回合 provenance 归剧本 S-int-6/7，docstring 注明）。
- **must_not_touch 对账**：schema / tool 语义零改动（turn_tools 只动 answer 描述句 = 判软修点名座位）；payload 条款零改动（grounding hierarchy / beat anchor 表格 / suggestions 三件套 / disclosure / run_completed 交付事实纪律逐字未动）；S 场景零改动（S-int-10/11 为纯新增）；混合段纪律——beat①/④ 只抽 speech 质感句，rejected-alternative 与 speaker-form payload 句原位保留。
- **未跑验证（用户清单）**：① 触发回合剧本（S-int-11 为首）+ 事故①②场景转绿（S-int-10/11）；② `reply_quality_probe.py` 轮替（round-robin，J6 + 语言矩阵——先存 v6 新基线再对账）；③ **判软修双向断言**（GPT 评审吸收）：S5/S10 复跑 = clips 类点名工作回收 present_plan（正向），S-int-4 不回退 + S-int-2/5 两跑判读 = answer+suggestions 档不得被压回（反向——answer 不得变成"逢工作词就出 plan"的吸尘器）；④ prompt_gate 全量 12 探针（probe I 首读数入 THRESHOLDS 注释——首读 = 建测量带，不是定义产品真理；failure tag 拆分读数同记）；⑤ chat_scenarios 全量（既有债四族不在本批账——A 白名单 / B 探索族 / C S22 时序 / S16 flake）；⑥ 纯 pytest（零 schema 改动，预期 906 绿 + 既有债 11 红，清单外新红 = 异常）；⑦ py_compile / import 冒烟（scripts 三件套本批改动面）；⑧ **四终态边界目检**（GPT 评审吸收）：answer / answer+suggestions / ask_user / present_plan 谱系读数 vs 批次 S 验收读数——D 不得把谱系推歪（事故①②之外无边界漂移）。**验收时点（用户拍板）：①~⑧ 不单独先跑，与 E 二分协议合并为迭代二收口验收单一次战役（批次 E 节目落 = 现行法）。**

---

## 批次 E：言语法逐簇去重（零假设探针）

| 字段 | 内容 |
|---|---|
| **scope** | E1 收尾问句簇 / E2 FREE PHRASING 簇 / E3 ask_user 形态簇，逐簇 stash 探针删除（router 为主、chat_intent 镜像） |
| **files** | `intent_router_system.j2`、`chat_intent_system.j2` |
| **depends_on** | D 收口（suite 已含事故①②回归） |
| **must_not_touch** | schema / catalog / 契约段；payload 条款（grounding hierarchy / disclosure / DISCOVERY GOALS / 任务组成规则 / rejection 协议 / partials）；S 场景；混合段纪律同 D |
| **acceptance** | **验收时点用户拍板：不随簇跑探针，整批（D+E1+E2+E3）施工完成后统一验收**（收口验收单见本节目落）；归因机制 = commit 序逆序二分——红 → `git revert --no-commit` 逆序（E3→E2→E1→D）定点重放红座，绿 = 归因该簇，承重簇 revert 成 commit + 登记「观察到删除导致回归；该簇暂保留」（恢复转绿只证删除改变了行为，不证该文本语义不可替代）；一次 green 不证冗余；**ablation 只判"删文本是否行为回归"，不判"旧 lane 是否仍存在"** |
| **rollback** | 逐簇 revert commit（拍板后留痕）；承重簇恢复后永不再探 |

**批次 E 施工协议（现行法，用户拍板后版本）**：三簇 = 三个独立 commit（D → E1 → E2 → E3 线性序），施工会话逐簇 `git apply --check` → `git apply` → commit → 简报登记，**全程零探针零剧本**；apply 漂移 = 停下报告，禁手工硬缝后静默继续。统一验收时若全绿 = 迭代二收口；红 = 按上表 acceptance 行二分，每步 revert 只对红座定点重放（不重跑全量），归因确认后 revert 落成 commit。

**批次 E 施工包**（施工会话已备）：`apps/api/scratch/iter2-e1-closing-question.patch` / `iter2-e2-free-phrasing.patch` / `iter2-e3-ask-user-form.patch`——累计序列（e1 → e1+e2 → e1+e2+e3），repo 根 `git apply` 入座、`git apply -R` 恢复，apply/revert 全往返已验证（未跑任何行为探针）。逐簇边界：

- **E1**：router present_plan ③ 收尾段（删 "phrased your own way, answerable with a single word" + 两处引号示例，契约全留）/ router propose_plans 收尾收缩为宪法①引用 / chat_intent propose_tasks·edit_graph 行删 magic-word 引号示例（本 prompt 的定义座留全式）/ chat_intent propose_plans 收尾收缩为 propose_tasks 同拍引用。per-prompt 各留一处完整定义座（router=present_plan、chat_intent=propose_tasks 行）——两 prompt 互不可见，收缩不得跨 prompt 引用。
- **E2**：router 三处（present_plan FREE PHRASING 尾句 + "never reuse a line from an earlier turn" / ask_user 尾句 / start_run FREE PHRASING 尾句）+ chat_intent ask_user 尾句，全部落宪法⑥+直给。partials 零触碰（_capability_answer rule 4 同族句按 must_not_touch 保留）。
- **E3**：两路 ask_user 长段各收缩为契约一行（prose=判断 card=决定 + `question`/`default_path` 参数座 + recommended_id 同声 + 宪法①④引用）——候选删除面 = 介质法三禁（问号收尾/列举选项/复述理由行）、"say it plainly" 句；参数契约（`question` = bare question, no default-path tail）保留在收缩行内。

**判读要点（施工会话预登记 + GPT 评审翻案）**：**E1 升级为并列最高危**（GPT 翻案原登记）——E1 与批 D 同坐收尾语义面（D 刚把 trigger 收尾从 verdict 改成 offer，E1 再删两路 prompt 的收尾法），删除窗口紧邻形态变更窗口，假绿形态具体：事故②表面不回来，但正常回合开始不收尾 / 收尾退成开放闲聊 / 卡与散文重新错拍。**E1 定点重放座 = 四终态全谱**（answer=S-int-1 / answer+suggestions=S-int-2·5 / ask_user=S-int-3·S1·S3 / present_plan=S-int-4·S5·S10）+ trigger=S-int-11·S19，不只是事故①②同形座。E2 疑似承重不变——「never reuse a line」是 anti-parroting 的唯一言语法座位（宪法六条无同义条；S-int-9 锁旧腔 verbatim 负形靠它喂），探针红即恢复不意外；E3 的介质法三禁在 partials 无镜像（_asking_strategy 只载选项策略），删除后 prose 问号收尾可能回归——两簇探针的必看座 = S-int-9 / S1 / S3 / S-int-3 + ask_user 全族（S-int-6/7 的 ask 分支）。E1 判软面随删随张开：S5/S10/S-int-4 同 E 每簇必看。**登记语言纪律（GPT 吸收）**：探针红恢复后登记写「观察到删除导致回归；该簇暂保留」——恢复转绿只证删除改变了行为，不证该文本语义不可替代，永不写"证明唯一承重原因"。

**迭代二收口验收单（现行法——D+E 整批施工完成后用户自跑，一次战役）**：

1. `uv run python scripts/chat_scenarios.py --only S-int-10,S-int-11`（事故①②回归场景转绿）
2. `uv run python scripts/reply_quality_probe.py --save-baseline iter2-final`（v6 基线 = J6 + 语言矩阵首读建带——此跑是建测量尺度，不是审判；读数入简报）
3. `uv run python scripts/chat_scenarios.py --only S5,S10,S-int-4,S-int-2,S-int-5`（判软修双向：S5/S10 回收 present_plan = 正向；S-int-4 不回退 + S-int-2/5 两跑判读 = 反向——answer 不得变成"逢工作词就出 plan"的吸尘器；发射率波动面红了重跑一次再判）
4. `uv run python scripts/chat_scenarios.py --only S-int-1,S-int-3,S1,S3,S19,S-int-9`（E 假绿面 + 承重疑似座：四终态谱系 / ask_user 全族 / E2 anti-parroting 座 / S19 trigger 准入）
5. `uv run python scripts/prompt_gate.py`（全量 12 探针——probe I 首读数 + failure tag 拆分读数入 THRESHOLDS 注释；红了按铁律先重跑一次排 provider 漂移）
6. `uv run python scripts/chat_scenarios.py`（全量——既有债四族 A 白名单 / B 探索族 / C S22 时序 / S16 flake 不在账，红了先对批次 S 验收节归因表）
7. `uv run --extra dev python -m pytest tests/ -q`（预期 906 绿 + 既有债 11 红，清单外新红 = 异常）
8. `uv run python -m py_compile scripts/prompt_gate.py scripts/reply_quality_probe.py scripts/chat_scenarios.py`（冒烟）

红 → 二分（逆 commit 序）：`git revert --no-commit <E3>` → 红座定点重放 → 绿 = 归因 E3；仍红 → 叠加 revert E2 → 重放 → …→ D。归因确认：revert 落成 commit + 简报登记「观察到删除导致回归；该簇暂保留」；探针红永不回调阈值。全绿 = 迭代二收口：删除总量与承重清单写进本简报批次 E 验收节（迭代三收尾时 CHAT_ARCHITECTURE.md 写现行法的素材）。

**批次 E 落地记录**（施工会话交付，三 commit 线性落座，验证全部未跑）：

- **E1 `ddde27f`**：`git apply --check` 一次过，零手工缝合；只触两 prompt 文件。删除量 = 4 处改写（router present_plan ③ 收尾段 / router propose_plans 收尾 / chat_intent propose_tasks·edit_output·edit_graph 行 / chat_intent propose_plans 收尾），删 4681 字符 / 增 4366 字符（净删 ~315）。per-prompt 定义座留位与设计一致：router = present_plan ③ 全式，chat_intent = propose_tasks 行全式。
- **E2 `4a226ee`**：`git apply --check` 一次过，零手工缝合；只触两 prompt 文件。删除量 = 4 处改写（router present_plan FREE PHRASING 尾句 / router ask_user 尾句 / router start_run FREE PHRASING 尾句 / chat_intent ask_user 尾句），删 4833 字符 / 增 4450 字符（净删 ~383）。partials 零触碰（`_capability_answer` rule 4 同族句原位保留）。
- **E3 `58c9449`**：`git apply --check` 一次过，零手工缝合；只触两 prompt 文件。删除量 = 2 处改写（router ask_user 段 / chat_intent ask_user 段），删 1649 字符 / 增 975 字符（净删 ~674）。参数座（router `question` no-default-path-tail + `default_path` param / chat_intent `question` bare）保留在收缩行内。
- **三簇合计**：10 处改写，删 11163 字符 / 增 9791 字符（净删 ~1372）。
- **收口验收单一致性核对（施工会话对账）**：验收单 8 条命令行与代码终态一致——chat_scenarios.py 含 S-int-1..11 / S1 / S3 / S5 / S10 / S19 全部场景号；prompt_gate THRESHOLDS 恰 12 探针（A..I 含 H2/H3/H4），probe I 注释「first reading pending」在册；reply_quality_probe.py 存在且 RUBRIC_VERSION=6（批 D 已升）。无漂移。

**批次 E 验收记录**（用户授权施工会话代跑收口验收单，一次战役）：

- **确定性面**：pytest 906 绿 + 11 红（既有债逐项命中、零新增）；py_compile 三脚本 OK。
- **事故①②回归**：S-int-10 / S-int-11 双绿。
- **判软修双向**：实质绿——正向 S5 / S-int-4 ✓、反向 S-int-2 / S-int-5 ✓；S10 红 = 既有债 A（活动帧白名单缺 `at` 键，归因表逐项命中，不在账），S10 的 present_plan 回收读数被该债阻挡（场景维护批的事）。
- **E1/E2 承重疑似座**：S3 / S19 / S-int-1 / S-int-3 / S-int-9 全绿——E1 假绿形态（正常回合不收尾/收尾退闲聊/卡与散文错拍）未出现，E2 anti-parroting 座（S-int-9）未回归。
- **E3 归因 revert（`70136d8`）**：S1 解剖①红——ask 散文退化为裸问题复述（判断框架消失），E3 删除态基线 1/6 红、恢复态 0/8 红，红形态与判读要点预登记的 E3 介质法三禁删除面精确吻合；预登记预测 × 形态吻合 × 方向性数据三重同向，按协议逆序二分落 revert commit。登记语言纪律：观察到删除导致回归；该簇暂保留——样本量有限（1/6 vs 0/8 未达统计显著），恢复转绿只证删除改变了行为，不证该文本语义不可替代。E3 承重簇永不再探。
- **新债登记（fill-keys 族，不在本迭代账）**：S1「start 后同节点原地填充」断言在模型把 `research` 组进链时红（删除态 2/6、E3 恢复态 3/8 同率复现）。DB 实证机制 = artifact facet 读面折叠——research 节点 start 后 stamp 为 `facet` 并入 deliverable 卡组（ADR-097 §3 第二层门既有行为，research hoisting 起 2026-09-03 先于批 S），读帧节点数 ≠ draft 节点数，与 prompt 无关。处置 = 场景维护批拍板（断言口径是否计 facet 组），不修场景不回调。
- **E1/E2 保持删除态**：三簇合计原删 11163 字符，E3 恢复 674 字符后，净删除 = E1 ~315 + E2 ~383 ≈ 700 字符 / 8 处改写。
- **prompt_gate 12 探针（终态树）**：11/12 绿——A 12/12、B 11/12、C 12/12、D 11/12、E 11/12、F 9/12（在册摆动带 6↔10 内）、G 12/12、H-H4 满分。**probe I 首读建带：4/12 → 重跑 6/12（铁律重跑排漂移），均低于阈值 8**；failure tag 拆分：terminal=None（bare_reply）为主（6→2→5），suggestions-range 次之（2→3→1），ask_user-called 1 次，**present_plan 劫持零发生（事故④原形态清零 = 批 D 判软修的 gate 实证）**。**归因实验：pre-D prompt 面（`30174b6^` 五文件临时回退）复跑 probe I = 6/12 同带同签名**——bare_reply 发射率弱点先于 D/E 存在，非本迭代回归；probe I 的 8 阈值是沿袭先例非实测，首读建带读数 = 4~6/12。**新账登记：浏览问 answer+suggestions 发射率 ~40-50%（bare_reply 为主，生产有 read-tolerant 散文地板兜底不成错误，但建议卡不发 = 谱系第二档发射弱）**——阈值校准（首读建带是否落地 4 或 6）与发射率改进（prompt 面还是 substrate 面）留用户拍板，铁律：永不回调阈值粉饰回归，但首读建带是测带不是粉饰。
- **S5 波动面**：panel-edit 存活断言首跑红（count 以串方言 `'3'` 落库 vs 断言 int `3`——顺形律 dialect 族，schema/钉参机械未被 D/E 触碰），重跑即绿（判过）；同族 dialect（`'null'` 串）同现在失败详情，既有 1741b17 兼容层覆盖。
- **v6 基线（`baseline-iter2-final.json` 已存，建带非审判）**：S-cap 语言矩阵六格 J5/J6 全 2（事故①仪表全守位）；**S-warm（事故②主战场）J1-J4 全 2**（verdict 带拒绝项 / 剪辑事实 / 负向判断 / 单一收尾），**J6=1 边缘**——收尾句「先把这块打出来」仍带 go-ahead 腔（推荐角色守位边缘，非塌禁态）；D3=0——散文点名的拒绝项（长文）按设计不可点选，rubric 口径与 rejected-alternative 结构的冲突待判读；S-adv（素材处理中问建议）J1/J2/J4=0——模型以承诺制 defer（材料未读不可判定是介质法正形），rubric 是否给 deferral 留座待判读。
- **chat_scenarios 全量（终态树，37 本）**：25 绿 12 红，红全部归因——既有债 A ×4（S6f/S10/S20A/S21A 白名单 `at` 键）、B ×2（S23 NoResultFound / S-explore-2 plansReady 失速）、C ×1（S22 落点拍时序）、S16 族 ×1（warm decompile 未言语，既有债登记的第二失败点）、fill-keys 族 ×1（S1 全量跑为 settle-miss 新形态：模型绕过 pending ask 直接 draft_from_persona 出书——LLM disposition 方差，重跑转绿判过）；**flake 四座重跑**：S1 ✓ / S4 ✓（material_pending 误读一次性）/ S-int-5 ✓（发射率波动，批 S 先例同判）/ **S5 ✘（第三形态：模型把计划 JSON 直接铺进散文的 bare reply——发射层畸形，provider 族，与 D/E 文本面无映射）**。S5 今日五跑 2 绿 3 红（dialect ×2 + 散文计划 ×1），三形态全在发射层，rate 偏高在册待观察。
- **收口判定（用户拍板，GPT 终审吸收）**：迭代二正式收口——D / E1 / E2 冻结接受（E1 引用式收缩在现有剧本范围零回归，不恢复冗余文本；E2 当前样本未退化）；E3 回退正确，同一删除面永久关闭（schema 只约束载荷不约束散文，介质法三禁 = 跨介质呈现契约，属工具契约合法形态非 lane disease）；判软修措辞不动（双向实质绿在册；「名词提及但未提出工作」反例随后续 golden suite 补，实测误 dock 才收紧，禁扩成场景判别规则簇）。**登记在册的观察项与维护纪律**：① E2 anti-parroting 未覆盖风险——宪法⑥ PLAIN SPEECH 不逻辑蕴含跨回合不复读（固定开场白 / 已确认建议复述 / 能力问答结构性复读三观察面；「不复述无新增信息的旧措辞，已确立术语与已确认事实自由复用」方向是否入宪法须过准入闸，不预先立规则）；② 宪法①语义微调候选（「closable with one word」→「a complete offer the user can accept or decline in one word」方向——可接受性要求而非句法约束）挂下次宪法维护，不阻塞；③ 引用式收缩维护纪律——引用目标须在同一模型实际消费的 prompt 内可见（partial 单独被消费且无宪法 include 时引用即悬空；改 include 关系时做一次 prompt 展开检查，不立自动检查系统）；④ S-warm J6=1 保留边缘分不立新规则（同类 go-ahead 腔在无 dock 情境反复出现才升级行为问题）。**遗留四线独立登记**（PROGRESS 需求池）：建议卡发射率（probe I 拆双指标，路由安全已通过、发射率未达目标不标通过）/ 发射层方差受控复测（S5 族）/ 评测系统语义三修（J6 开工暗示断言 / D3 拒绝项判读修正 / S-adv deferral 合法座）/ fill-keys 读面口径（先拍产品语义再定修面）。判词：剩余工作不是继续删 prompt，而是把测量口径与模型发射稳定性分开——「没回归」≠「已达标」。

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

**批次 G1 落地记录**（施工会话交付，验证全部未跑）：

- **座位选择（判定树的实施座 = 发射座 + 文案座，两座各取最小）**：文案座单独做不了「静默」（copy 无法让行消失）；发射座单独做则变化/失败两终态仍念旧自白词。故：发射座（`activity.py`）裁可见性（判定树），文案座（i18n 两键原位改写，零新增零删除）供给无自白终态词。repair span 开启不再发射 active 帧（静默开启——重试窗 = 普通 LLM 窗，think 行/StatusLine 覆盖；修复机械自叙述 = 宪法②），span 内部状态照track（T16 双不变量内部成立：`has_active()` 重试窗内仍真）。终态判定树：① read 收口（含探索 observation 族）→ 静默（读行自叙当下工作，转向断言为时过早）；② 终态同形收口（接受名 ∈ 被拒名集）→ 静默（未被公开承诺的东西无需交代）；③ 终态转向收口（被拒名全已知且接受名 ∉）→ 恰一 born-terminal completed 帧（key=`chat.activity.repairDone`，带真实 span 耗时——重试是真 server 工作）；④ 不可证（任一被拒名 None=truncation）→ 静默（无依据则不言）；⑤ LoopExhausted / 失败回合 sweep → 恰一 born-terminal failed 帧（key=`chat.activity.repair`，诚实失败证据，persist）；⑥ completed 回合 sweep（bare reply 收官）→ 静默（答复即终形）。静默 span 零发射零 persist。
- **i18n 文案修宪（en/zh 同步，键名不动）**：`repair` = 失败终态专用（zh「这次没能完成」/ en "Couldn't get it done this time"）；`repairDone` = 转向终态专用（zh「换了个方式」/ en "Changed approach"）。键名复用红利：存量 failed 帧（旧律 repair 键）回放读新词恰合失败语义；存量 repairDone 行回放自白 retroactively 消失。禁句静态锁入纯测试（`test_repair_copy_keys_carry_no_self_confession`：两键 × 两语言正则负形）。
- **rejection 取证（落库座 = kernel 事件事实 + projector 台账 + activity_log 行，两 turn 文件零改动）**：`ToolRejected` 扩三事实字段（`iteration` 0-based 迭代序 / `detail` 拒因 verbatim 截 200 字（validation error / guardrail feedback；unknown_tool 的 detail=None——名字即全部事实）/ `duration_ms` 被拒尝试自身墙钟（kernel 每迭代顶打点，monotonic））——kernel 只说发生了什么，冰冻边界不破。projector 新增 `_rejections` 台账（每 ToolRejected 一记 {tool_name, kind, iteration, detail, duration_ms, at}，at=ISO UTC），`rejected_calls()` 访问器；持久化 = `record_activity_log` 增 `rejections` kwarg 落 intent.rejections（回放只读 frames，取证行不渲染；frames 或 rejections 任一非空即落行）。**对话内回注行为零改动**（`_loop_echo` 链未触碰）。「耗时」口径实证：被拒尝试的迭代墙钟（kernel 实测）+ repair span 总耗时（终态帧 duration_ms）双层。取证查询示例（验收用）：
  ```sql
  SELECT intent->'rejections' AS rejections
  FROM messages
  WHERE intent->>'type' = 'activity_log'
    AND intent->'rejections' IS NOT NULL
  ORDER BY created_at DESC
  LIMIT 5;
  ```
- **事故③ wording 回归场景 = S-int-12**：空项目直点 media 工作（出书门槛拒 → 护栏转向），最多 2 个全新项目等到真拒绝证据（cancelled 帧 = 拒绝唯一 wire 证据座），均无 = 硬红（防空洞绿，S-int-3 同口径）。断言三件套：① 零 repair active 帧；② repair 帧 ≤1 且只以终态出现、键落新词表；③ DB 台账形状 + 交叉一致（台账被拒名 × 信封终态 ⇔ 转向帧有无——同形零帧、转向恰一 completed 帧）。harness 维护同批：`_work_evidence` 的 had_repair 改检 cancelled/repair 帧（静默开启后拒绝的 wire 证据 = 半开调用的 cancelled 帧——check_stream_law / check_read_silent_stream 的 replaced-speech 跳过律语义不变）。
- **纯测试同步改写（新发射律的锁，非迁就）**：test_activity_pure 的 T3/T4/T5/T9/T10/T13/T15/T16b/settled_frames/探索族/route-seam 全部按判定树重写 + 新增六条（转向单帧 / read 收口静默 / 同形静默 / 不可证静默 / 跨 span 名单隔离 / 台账形状与拷贝语义）+ i18n 静态禁句锁；test_tool_loop_pure 四处事件断言改字段级（duration_ms 为真实墙钟，锁类型不锁值）。
- **场景面已知相互作用（在册不处理）**：`check_activity_shape` 的「每活动首帧必为 active」律与 born-terminal 帧（repair 终态帧 + 既有 milestone 帧）不兼容——该 checker 本就在既有债 A（白名单漂移）账上，场景维护批需同批补 born-terminal carve-out；S-int-12 不调用它，G2 新断言亦不调用。
- **must_not_touch 对账**：deferred_frames.py 零改动；stream semantics / 帧序 / 缓冲零改动；prompt 文本零改动；plan_turn.py / propose_turn.py 零改动（取证流经共享 projector，两 turn 天然喂同一事件通道）。
- **未跑验证（用户清单）**：① `uv run --extra dev python -m pytest tests/test_activity_pure.py tests/test_tool_loop_pure.py -q`（新律锁 + 既有债 11 红不算账）；② 全量 pytest（清单外新红 = 异常）；③ `uv run python scripts/chat_scenarios.py --only S-int-12`（事故③ wording 场景转绿）；④ 全量剧本（重点：调 check_stream_law / check_read_silent_stream 的场景——_work_evidence 语义等值性；S10 等 check_activity_shape 调用点仍在既有债 A 账）；⑤ rejection 取证查询（上 SQL 示例，真跑一个被拒回合后查）；⑥ web tsc（i18n 键改动不触 TS 面，预期零新增）。
- **承重观察（在册不处理）**：① 台账 detail 含 validation error / guardrail feedback 原文（内部取证文本），随消息行 intent 上 wire 不渲染——取证座既定，若日后要脱敏另开批；② 静默开启后重试窗的 now-line = think 行「Thinking…」——T16-A 盲窗由状态行/散文半边覆盖（该不变量本就声明是组合不变量），若实测觉得盲窗偏长，补救座是 StatusLine 相位叙事（G2 死寂覆盖施工点同座），不是恢复 repair 行；③ 转向帧 copy「换了个方式」不带具体去向（projector 无参数面，宪法② 边界）——去向由紧随的 dock/答复自证。

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

**批次 G2 落地记录 · 施工前座位裁决**（动手前登记，implement 后补施工记录）：

- **武装条件推广 = SSE 道全武装（`on_delta is not None` 即武装），素材戳条件拆除**。实证依据：流式只发生在迭代 0（`tool_loop.py` `streaming = on_delta is not None and iteration == 0`），泄漏窗 = 迭代 0 全程；四种拒径中 schema_truncation / unknown_tool / params_validation 根本不到 execute 座（事故③ 的 present_plan 参数拒绝与素材戳无关照样泄）。武装判定只能挂传输道不能挂内容（禁 token 级分类器 / self-tag / NLP 散文解析——无条件武装是这三禁下的唯一形）。重试迭代本就非流式（quiet），其散文只经信封释放——「被拒迭代零痕迹 + 重试只见最终信封」由循环结构天然保证。
- **终态调用武装清单（两 turn 文件终态分发实证，逐个裁决）**：
  - plan path（intent_router = PLAN_TOOLS + exploration terminal）：`present_plan`（链裁决 / 出书门槛 / transform targets——**首座，事故③ 座**）/ `ask_user` / `start_run`（paid boundary 校验）/ `answer`（空散文拒 + 素材待命 suppress 座）/ `propose_plans` / `revise_plan` / `revise_selects`（ExplorationRejected 门拒）。
  - chat path（chat_intent_agent = CHAT_TOOLS + exploration terminal）：`propose_tasks`（caption gate）/ `edit_graph`（wiring 裁决）/ `revise_output` / `edit_output`（目标解算拒）/ `ask_user` / `answer` / `propose_plans` / `revise_plan` / `revise_selects`。
  - **裁决：全部入武装**——每个终态 execute 都有 guardrail 拒径，且全部共享 loop 级三拒径；无条件武装下逐个裁决是登记「为什么没有一个例外」，不是选择子集。
  - **非终态（不入终态裁决，stay armed 不清不冲）**：PERCEPTION_TOOLS reads + `propose_candidates` / `propose_selects`（ToolObservation 返回）——读被接受 = 世界自证，其散文入言语账本最终随信封/flush 释放。
- **四态机 API 演化**：`retract()` = REJECT 座（清陈队列 + 置 rejected 旗 + **stay armed**——RETRY 即再武装，缓冲天然续命，规格明条「RETRY 陈 buffer 必清」）；`flush()` = 按到达序回放 + **stay armed**（中段释放不再解除武装）；`drop()` = 清 + disarm（suppress 座 / rejected 收口座）；`disarm()` = clean 收口后显式解武装（幂等）。`saw_rejection` / `note_rejection` 退役。**拒绝侦测单座 = runner 包 `on_loop_event`**（ToolRejected → retract + 转发）——四种拒径全经此一座；execute 侧 `note_rejection` 调用删除（execute_guardrail 的 ToolRejected 由 loop 在 execute 返回后发射，execute 座冗余）。
- **缓冲通道裁决（三通道分家对账后的修正座）**：缓冲只裹 **delta + tool_ready** 两钩。`on_tool_call` **不入缓冲、保持 live**——它是复合钩（routes.py `_make_tool_hooks`）：① 喂 Activity projector 的 `name_known`（read/repair 工作证据 + G1 cancelled 帧取证座 = 活动流自有 undeferred 通道，loop 事件 ReadAccepted/ToolRejected 本就 live 到达——若 name_known 被缓冲，projector 输入序反转：accept/reject 先于 name_known 到达，read 行永不出现、cancelled 帧取证座消失，S-int-12 硬红）；② SSE phase-clear = 存活性 chrome（thinking 行渲染门 = `chatBusy && !proseActive`，与相位标签无关——死窗覆盖不受影响），非裁决依赖言语。`tool_ready`（question.preview 座）**入缓冲**——被拒 ask/plan 的预览先 dock 再回滚正是事故③ 同族毛刺，裁决依赖的预览服从协议：accept 时随 flush 释放（与信封同刻，权威 re-dock 不变）。零痕迹律不破：活动流取证是 G1 明条豁免，phase-clear 非散文非 dock。
- **拒绝旗的回合语义**：一次被拒 → 全回合收口零帧（接受迭代自身的结构帧亦不回放，信封独说）——与素材待命现行为逐帧一致（post-rejection accept 旧律 drop 全部）；接受迭代结构帧与信封同刻到达，无时序信息损失。即验收清单②「retry→只见最终信封」。
- **checklist ④（SSE 断流重连）座位定案 = 剧本座 S-int-14 + 进程内缓冲纯断言，不扩断流重连脚本座**。理由：提交点在回合尾（caller commits），socket 生命周期与 server 侧状态机本就解耦——断流只是客户端少收帧，复拉 conversation 即「重连」语义的既有面。S-int-14 形：SSE 道收 n 条帧后提前断连 → 断言该回合至多一条 assistant 行（无半截双行）→ 复拉与信封一致 → 后续回合干净无陈帧。纯测试锁「缓冲→回放恰一次」（双 flush 防）。
- **StatusLine 死窗覆盖（实证，零新发射点）**：验证死窗 = 终态 execute 校验期。覆盖链：thinking 行渲染门 `chatBusy && !proseActive`（缓冲期内 proseActive 不亮——delta 未达客户端）→ think 行持续；composing 相位的 clear 帧被缓冲，死窗内相位标签不灭。死寂覆盖 = 既有结构自然成立。
- **素材待命现用法对账（纯测试锁口径 = 外部可观察契约）**：clean accept 按到达序回放（帧序稳定）/ reject 后零帧达钩 / suppress 零帧 / checkpoint flush-first——四条全保。两处帧级演化登记（deviation-with-rationale，验收时拍板）：**D1** 拒绝标记的回合从「accept 时全丢」演化为「拒绝时即清陈 + rejected 旗收口 drop」——线上不可观察等价（帧从未发送），RETRY 清陈是规格明条（清单⑥）；**D2** checkpoint flush-first 后缓冲保持武装（旧律 disarm 直通）——堵旧洞「checkpoint 冲完即裸奔，随后终态被拒则结构帧已 live 泄」；可观察差 = 素材待命回合 checkpoint 之后的 tool_call/tool_ready 结构帧时点（收口批量 vs 即时），散文信封字节一致。

**批次 G2 落地记录 · 施工**（施工会话交付，验证全部未跑）：

- **deferred_frames.py 全文重写为四态机**：`retract()`（REJECT——清陈 + 置旗 + stay armed）/ `flush()`（回放 + stay armed，每帧恰回放一次）/ `drop()`（清 + disarm）/ `disarm()`（幂等收尾）；`saw_rejection`/`note_rejection` 退役；模块 docstring = 协议现行法（四态 + 素材待命车道骑同一机器 + StatusLine 死窗句）。
- **两 runner（plan_turn/propose_turn 镜像）**：武装条件 `material_pending_stamped and on_delta` → `on_delta is not None`（SSE 道全武装）；缓冲钩集 = delta + tool_ready（on_tool_call 保持 live，理由见上条通道裁决）；新增 `on_loop_event_with_retract` 包装（ToolRejected → `deferred.retract()` + 转发原钩——answer/chat 两 SSE 泵共用 runner，包装天然双生效）。
- **两 execute()**：`isinstance(result, str)` 的 `note_rejection` 分支删除（拒绝侦测单座化——execute_guardrail 的 ToolRejected 由 loop 发射，四座归一）；`_resolve_deferred` 新律 = rejected → `drop()`，clean → `flush()` + `disarm()`。suppress 座 `drop()` 调用不变（新 API 同语义）。
- **D3（施工中发现并裁决的第三处演化，补登记）**：question.preview 从「即发 + 被拒回滚」演化为「缓冲 + accept 释放」——旧律客户端可见「预览先 dock 再回滚」毛刺（事故③ 同族），新律被拒预览永不 commit；S10 ask 回合注释同步改写（"LAST preview authoritative" → "received preview IS authoritative"）。可观察差 = 预览到达时点从「参数校验通过」推迟到「终态接受」（与信封同刻）——preview-dock 的「提前量」功能被协议吸收，权威 re-dock 不变。
- **纯测试（test_material_pending_pure.TestDeferredFrames 全新律锁）**：六条状态机清单映射——①+②+⑤ `test_reject_leaks_zero_and_retry_sees_only_the_envelope`（retract 即清 + rejected 收口 drop + hooks 永空）；③ `test_flush_replays_in_arrival_order`（帧序稳定 + flush stay armed）；④ 进程内半 `test_mid_turn_flush_replays_each_frame_exactly_once`（防双 flush——checkpoint flush-first 后续帧只 fresh）；⑥ `test_retract_marks_and_clears_stale`；外加 suppress 座 `test_drop_discards_unsent` / `test_flush_after_drop_is_a_no_op` / `test_passthrough_after_disarm` / `test_none_hook_wraps_to_none`。
- **场景入座**：**S-int-13**（事故③ leak 回归锁——zh 素材 + 「做成中文配音版」触发 check_transform_targets 同语拒绝，≤2 全新项目等 cancelled 帧证据，硬红口径同 S-int-12）：① 被拒回合 wire deltas 拼接必为空（strict）；② 复拉消息流该回合 content assistant 行恰一且与信封同 id（activity_log/checkpoint 行滤除——它们同骑 role="assistant"）；③ DB 台账含 execute_guardrail 行。**S-int-14**（断流复连座）：harness `chat_stream` 增 `abort_after`（n 帧后断连）→ 轮询 90s 该回合 content assistant 行 0 或 1（永不 2；1 则内容非空）→ follow-up 回合完整走通且流式 ⊆ 信封前缀律。
- **harness 维护同批（新协议下的断言对账，非迁就）**：S10 ask 回合 `len(deltas) > 0` 增 had_repair 跳过（被拒回合帧静默是新律设计行为，check_stream_law 同款 carve-out）；check_stream_law / check_read_silent_stream / check_checkpoint_shape / S21 四条逐一审读——新机器下断言全部依然成立（flush 先于信封、read-silent 检测面不变、checkpoint flush-first 既有序不破），零改动。
- **前端零改动对账**：paceSettledProse 节拍机本就以突发 delta 为设计输入（零 delta 路径同律）；thinking 行渲染门 `chatBusy && !proseActive`——缓冲期 proseActive 不亮，死窗覆盖既有；预览与信封同刻到达 = 既有「预览 + 权威 re-dock」双帧序列的压缩，无新形态。
- **must_not_touch 对账**：prompt 文本 / 契约文案 / i18n / activity 措辞 / 决策路由 / validator 规则零改动；token 级分类器 / self-tag / NLP 散文解析 / 第二套 routing 零引入（武装判定挂传输道，拒绝侦测挂 loop 事件，无一内容判定）；activity.py / tool_loop.py / routes.py / service.py 零改动。
- **未跑验证（用户清单）**：① `uv run --extra dev python -m pytest tests/test_material_pending_pure.py -q`（新四态机锁 + 素材待命车道契约）；② 全量 pytest（既有债 11 红不算账；清单外新红 = 异常）；③ `uv run python scripts/chat_scenarios.py --only S-int-12,S-int-13,S-int-14`（G1 场景在协议推广后不回归 + 两新场景带入）；④ 全量剧本（重点：S10/S21/S23 流式断言面 + check_stream_law/check_read_silent_stream 调用点 + S16 既有 flake 账）；⑤ live 复跑四事故场景的事故③ 同形（被拒回合客户端零散文毛刺）；⑥ web tsc（前端零改动，预期零新增）。
- **承重观察（在册不处理）**：① preview 的「提前 dock」功能被协议吸收后，question.preview 帧实质退化为信封前奏——若日后实测认为预览帧冗余，退役是独立批次（客户端 rollback/re-dock 机先留）；② clean 回合首字延迟 = 全生成 + 校验时长（缓冲整段持有）——定案不优化；若 live 实测首字延迟体感过长，「安全前缀即流」是 ADR 级翻案议题（本批明条停手点），不是调参；③ 被拒回合的 phase-clear 仍 live（name-known 时刻）——thinking 行标签在重试窗回基态「Thinking…」，若实测觉得相位叙事不够，补救座是 StatusLine 相位文案，不是把 tool_call 塞回缓冲。

**批次 G2 验收裁决落地**（用户裁决 2026-10-03，验证调整随批）：

- **三项关键裁决全部接受**：终态全武装（边界：武装 = 必经安全检查 ≠ 都应被执行；总收尾文档必须写明「为什么没有例外」的裁决理据，不只留名单——防未来新终态工具把清单误读成封闭枚举）；不扩断流重连脚本座（适用范围前提 = 回合提交正确性不依赖客户端完整接收活动流；若未来发现断流致重复提交/错误确认/状态不可恢复，另立连接恢复测试座）；三通道分家为本轮核心架构收敛（活动流/存活性 chrome live 不承担裁决证据完整性；散文通道到达 ≠ 结构化裁决完成；预览缓冲是协议正确性的一部分而非 UI 优化——缓冲必须保留足以恢复语义顺序的信息，否则只是把竞态从 projector 前移到缓冲释放点）。
- **D3 验收两命题分离**（已落 S-int-13）：① 客户端零预览零散文（deltas strict empty + previews 随 retract 清）；② 服务端零提交零残留（S-int-13 ④：present_plan → pending_brief echo == 信封；ask_user → pending question 与信封同 id；其余终态 → 无 dock 残留）——前者不替代后者。
- **原始事件序列留存**（验收裁决）：StreamTurn 增 `raw_events`（{event, data} 按到达序——跨类型顺序正是本轮问题面，分型列表丢失它）；`dump_raw_events()` 落盘 `scratch/speech_commit/*.jsonl`；S-int-12/13/14 全覆盖（事故③ live 复跑同要求：浏览器侧保存事件序列，不只 pass/fail）。
- **cancelled 帧三核对**（验收裁决「不能只检查帧是否存在」）：`check_cancelled_provenance()` = ① 来源（同 activity_id 先行 active 帧，无生而 cancelled 的鬼帧）② 顺序（active→cancelled 对先于 turn.completed）③ 对应（台账被拒名 `kind_for_tool` 映射覆盖 cancelled kind——裁决结果与工作证据描述同一次调用）；S-int-12/13 同座调用（G1 场景证据强化 = 验证调整，不属归因隔离禁项）。
- **S10 had_repair 跳过边界写明**（验收裁决「只豁免预期修复路径，不吞真正的流式失败」）：had_repair 唯一来源 = 活动通道 cancelled/repair 帧（拒绝 wire 证据座），豁免恰好覆盖「本回合发生过拒绝」；被拒回合的严格零泄漏在 S-int-13（迭代 0 拒绝 = deltas 必空）；S10 不能 blanket 断空——迭代 0 言语先经 checkpoint flush-first 合法释放、后续迭代才被拒时 deltas 非空是协议内形态。
- **验证执行顺序（用户定）**：① 四态机纯测试（失败先修状态机，不进集成）→ ② 全量 pytest（清单外新红暂停归因）→ ③ S-int-12/13/14 定向（核 cancelled 帧来源/顺序/对应）→ ④ 全量剧本（S10/S21/S23 流式断言全立方证未以牺牲既有流式语义换 G2）→ ⑤ 事故③ live 同形复跑（D3 关键证据 + 事件序列留存）→ ⑥ web tsc（完整性检查）。总收尾铁律：文档反映已验证的实现，不提前把施工假设写成现行法；G2 绿 + 六项无新增异常 + 原始事件证据可复核 + 文档与代码一致 = 收口标准；此前不扩展新场景、不把本轮发现泛化成新的全局流式规则。

---

## 总收尾

- 全部批次绿后：`CHAT_ARCHITECTURE.md` 一次性写现行法（谱系表 / 宪法座位 / 言语提交协议 / provenance 契约）；README 信息类型表行转正；NAMING.md §2 词汇行（终态交互形态 / 交互宪法 / 言语提交协议 / suggestion_ref / source_state）随批 C·C+ 登记。
- live 复跑四事故场景（项目 `6b42bd6b` 同形），全绿 = 简报归档 `archive/tasks-done/`。
- 需求池已登记：FRAMING 默认参化（批H 候选，批B 验证同构性后评估）。
