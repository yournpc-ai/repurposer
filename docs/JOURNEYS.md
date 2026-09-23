# Journeys — 用户旅程母文档

> Status: 活跃（2026-09-14 建，需求模拟四轮讨论的沉淀；拍板 = ADR-077/078；**2026-09-16 状态翻新**：T2 读工具族 / T3 触发回合+收官 reviewer / T5 decompiler 均已落地，原 🚧 标记按代码现状翻 ✅；残留 🚧 = op 覆盖度与 B4 镜头跟随；**2026-09-22 旅程四收敛**：发现型目标的 Agent 工作循环 11 拍全绿（R1~R26 台账），拍板落档 = ADR-088/089；**同日迭代一落地**：旅程四拍 2~5a 对象层 ✅（探索三族 + 探索写门 + 证据 reads + 画布三卡面 + S23 剧本）；**2026-09-23 迭代二落地并实测全绿**：拍 0 R6 路由 / 拍 2~3 Activity 穿插 / 拍 5 生产座位 / 拍 6 编译器+决策包+快照+R15 停顿全 ✅（合同 `tasks/agent-working-loop-iter-2.md`；LLM 驱动面同日实测 = prompt_gate 四探针 48/48 + S-explore-2 live e2e 全链 PASS）；残留 📋 迭代三 = 拍 4 插话换选 / 拍 8 收官 reviewer / 拍 9 修订回路收口 / 拍 10 记忆；**同日迭代三代码层收口**：拍 4/8/9/10 全 ✅（合同 `tasks/agent-working-loop-iter-3.md`；纯 pytest 625 + check_gates + web vitest 70 + tsc 全绿）——**live 验收待用户六拍走查**（`scratch/iter3-six-beat-walkthrough.md`；全顺后简报归档 + edit_graph 退役小提交，迁移弧进度 = ADR-089 §8 注记））
> 本文是**用户旅程的唯一事实源**：以「用户此刻感知到什么」为骨架的需求模拟。架构文档描述「系统是什么」，本文描述「用户经历什么」——技术评审时倒查：这个改动让哪条旅程的哪一拍变好？
> 治理规则：① 新功能开工先答「你在哪条旅程的哪一拍」；② 缺口从旅程登记进 `PROGRESS.md` 需求池（本文不记排期）；③ 旅程只描述感知与分支，实现细节指针到架构文档；④ 旅程的新增/修订 = 需求模拟讨论的产品产出，修订时全量改写为现在时。

## 旅程一：迷失用户首产（composer / 配方卡 → 第一份产物）

**用户画像**：有素材、不懂自媒体的知识专家；到来即彷徨，每步都要答「下一步是什么」。

| 拍 | 用户感知 | 系统支撑 | 状态 |
|---|---|---|---|
| 0. 入口 | 配方卡（预填模板）或 composer 乱输入；空指令本地拦截 | composer = chat 第一条消息（ADR-051）；配方 = 提示词（ADR-040） | ✅ |
| 1. 接待 | 废话 / 能力询问 / 明确目标 / 带不带文件都被接住；被问时一词可答、可跳过 | intent router 四动作 + ask 一等动作 + default path + 出书门槛 | ✅ |
| 2. 看素材 | 上传素材后 agent **主动说**「我看了——你在讲 X」；转写中有可见的过程叙事 | warm understanding + **触发回合（理解完成）** + 读工具 | ✅ |
| 3. 对齐 | 多轮问答收敛需求；每轮最多一问；不知道答案可安全跳过 | brief 账本 + 合并优先级 + 提问机器 | ✅ |
| 4. 拟书 | 草稿图先上画布（逐节点估价、零消耗）；散文总述意图与产物；cost 可见 | draft 图（ADR-057）+ dock 确认 pill（ADR-070）+ fold 估价 | ✅ |
| 5. 确认施工 | 可纠正 → 多轮 → 确认；手改撤名 | chat 修订恒胜 / WiringProposal / merge_brief | ✅ |
| 6. 施工 | 打勾流动态行 + 节点原地填充 + **镜头跟随当前节点** | DAG 执行核 + SSE + FlowView；**运镜 🚧 B4** | 半 |
| 7. 收官 | 有判断的汇报（做了什么 + 取舍理由）+ 下一步建议 pills | **触发回合（run 完成）+ 收官 reviewer** | ✅ |

## 旅程二：案例仿制（终极旅程——「把原视频做成案例那样子」）

**入口一句话**：「你能帮我把我的原视频做成案例视频这样子吗？」（两个视频 + 一句话）。本条旅程是 ADR-077 否决收窄与 ADR-078 decompiler 的立项依据——全旅程只需三个新概念即被撑住。

| 拍 | 用户感知 | 系统支撑 | 状态 |
|---|---|---|---|
| 0. 到达 | 两视频 staging chips → 上传 → 建项目 | 现成 | ✅ |
| 0a. 角色消歧 | 「哪个是你的原视频？」（选项 = 文件名，一词可答）；@mention 指认则免问 | **资产角色（source / reference）** + 提问机器 | ✅ |
| 1. 看 | agent 看两个视频：素材 → understand；案例 → **decompiler**（video → clip-spec 骨架）；看完主动说话（「案例是 45 秒快节奏 5 段混剪…」） | warm + **decompiler 节点** + 触发回合 | ✅ |
| 1a. 案例无语音 | 纯画面混剪走视觉通道（帧采样 + 视觉锚点 + M3 视觉） | decompile 关键帧通路（无转写时 judgment 纯走帧） | ✅ |
| 1b. 无录像素材 | 文字稿+照片 → stills 链 | align_stills 先例 | ✅ |
| 2. 拟书 | 链 = understand → plan（吃骨架）→ select_clips → captions → add_music → render；参数 **exemplar-derived**（代码从骨架映射） | ADR-078 判词⑤ + draft 图 + fold 估价 | ✅ |
| 2a. 素材撑不起结构 | 「案例 5 段，你的素材只找到 3 个亮点——做 3 段版？」 | ask（一词可答） | ✅ 机制 |
| 2b. 案例有做不到的 | 「动图形我做不到——用结构+节奏+字幕逼近，行么？」 | **契约即能力边界**（分解时无座位的字段 = 做不到清单）+ 带理由纠偏 | ✅ |
| 2c. 画幅不匹配 | reframe 或留黑 | reframe 已注册 | ✅ |
| 3. 施工 / 4. 收官 | 同旅程一 ⑥⑦；收官建议 pill 例：「和你的案例摆在一起对比看？」（reference 常驻可回读） | 同旅程一 | 🚧 B4 |
| 5. 后续更改 | 旅程三全集 + 案例特有：「节奏再快点」（改 exemplar 参数 → edit_prompt → run 子图）；「字幕再像案例一点」（preset op）；「案例 13 秒那个转场我也要」（能力缺口 → 诚实纠偏 + 需求池）；「用案例本身也剪一条」（角色反转） | 修订三扇门 + ADR-078 判词④ | 半 |

## 旅程三：后续更改服务（首产之后的主战场）

**定性**：第一版产物落地 = 服务的开始。三班岗 = 接待员（旅程一）→ 施工队（DAG）→ **服务员**（本旅程）。修订三扇门永不变：edit ops（参数精确）/ wiring ops（重生成·派生）/ ask（拿不准）；**感知 loop（有界只读）是服务员的眼睛**。

| 用户话术族 | 体验规格 | 系统支撑 | 状态 |
|---|---|---|---|
| 「字幕调小一点，改成黄色」（相对量） | 礼貌 echo → **读当前 spec** → op → 重渲染 → 收官报量化 | 读工具 + edit ops ✅；**size/color 自由版式 = L3 铁律域拒绝**（永不开放，回环给枚举可答形态——精确编辑迭代定调） | ✅（枚举族） |
| 「有什么其他字幕样式吗？」（推荐） | 「稍等我翻翻样式库」（**工具调用 = 相位帧碎碎念**）→ 读注册表 → options 提问 → 点选 → 换 | 读工具 + ask_user 选项 + set_caption_style（preset 枚举已通） | ✅ |
| 「声音小一点不？」 | 判断对象（人声/配乐）→ 读 spec 确认 → op（gain_db 已在）→ 报告量化结果 | 读工具 + set_music | ✅ |
| 「加个 bgm，有推荐的吗？」 | 读曲库 + 读理解摘要（氛围匹配）→ 推荐 2-3 首作选项 → 点选 → 画布**长出新节点 + 连线**，镜头游走 | 读工具 + wiring add_node/connect/run（出生地不变）；**镜头游走 🚧 B4** | 🚧 B4 |
| 「另外做一个法语版」 | echo → 派生分支 → 子图跑 → 收官带下一步（「字幕也来一版法语？」） | WiringProposal + graph_revise 桥（今日最完整的一支） | ✅ 主体 |
| 「这条剪得不好，重新剪」 | 变体并行（不覆盖原版） | ADR-061 + regenerate | ✅ |
| 「第二句字幕错了」/ 划选 | @output chip / 选区引用钉住指认 | mentions 注册表 + ADR-069 | ✅（文本族） |
| 「把开头那句删掉 / 再短 3 秒 / 字幕换 karaoke / 标题改成 X」（精确编辑四族） | agent 预告 → **quote→range 解算**（置信谱：精确 > 唯一 > 多义/未命中 = 域拒绝回环）→ op 落账 → 重渲染 → **回声事实句带区间**（「我把 0.0–4.2s 这段去掉了」） | `edit_output` 受控终态工具（ADR-090：enum 四件，原始 ops 永不进 LLM 词表）+ R20 双通道指认 + 归档不变量（重跑不销毁历史，ADR-091） | ✅ 精确编辑迭代（2026-09-24；live 走查待用户） |
| 「算了，还是之前的好」 | 撤销 / 版本换回 | operations undo（ADR-032）+ 换态 `POST /outputs/{id}/restore`（ADR-091 §2，同 work 至多一 active） | ✅ |
| 「以后都用这个样式」 | 偏好沉淀 persona | **挂定位大迭代**（ADR-042，运营端批次） | 📋 |

## 旅程四：从素材到精选（发现型目标的 Agent 工作循环）

**定性**：发现型目标（「把这场里关于定价最好的回答做成 3 条短视频」）的完整工作循环——本旅程是 ADR-088/089 的立项依据。与旅程一~三的关系：一~三描述「首产与后续更改的接待形态」，本条描述 **Agent 在 Project World 中连续工作的主循环**——Agent 的主循环不是 Run，而是围绕 User Goal 持续生产、验证、修订用户可理解的项目产物；Run 是其中一个受授权的执行阶段。**北极星**：Agent continuously produces and refines user-meaningful project artifacts; it does not compile or directly execute workflow internals. Paid execution begins only at the confirmed scope boundary.

**入口一句话**：「把这场 60 分钟 webinar 里关于定价最好的回答做成 3 条短视频，配 LinkedIn 文案，法语版。」
**参照系**：OriginCut（项目状态连续 + 证据/精选中间层）与 Claude Code（一句绿灯 → 连续可见工作 → 只在需要用户时停）——「正在自主工作」本身是产品体验；确认拍的位置两者与我们一致（付费边界），差异从来只在过程可见性。

| 拍 | 用户感知 | 系统支撑 | 状态 |
|---|---|---|---|
| 0. 目标抵达 | agent 复述目标后**直接开始干活**（「我先看看素材和内容」）——无 dock、无任务清单复述 | 意图路由识别**发现型目标**（R6：实现空间未定 → 探索链；范围清晰的干脆请求走既有短路径） | ✅ 迭代二（R6 生产接线：EXPLORATION_TOOLS 入 intent_router 工具集 + 判定段 prompt + prompt_gate 探针 D，2026-09-23；live 复跑待配额） |
| 1. 理解/索引 | 转写节点出生即 loading → done | understand 链，内容寻址复用 | ✅ 既有 |
| 2. 搜索候选 | Activity「Searching… / Found 14 relevant sections」→ 画布长**候选合集节点**（默认折叠，展开 = 14 段时间区间 + 一句话摘录） | `search_transcript`（确定性检索 read）+ `get_segment` 精读 → 终态 `propose_candidates`（探索写门）；**R1 合集律**：可见粒度服务「用户纠正 Agent」，不铺 14 张独立卡 | ✅ 迭代一（reads + 写门 + 合集卡，2026-09-22）+ 迭代二（Activity = `chat.explore.searching`/`searchingDone` + `candidatesReady` 里程碑带 count，R6 路由，2026-09-23） |
| 3. 评估 | Activity「Comparing 14 candidates…」 | LLM 逐段判完整性（时长/边界 = 代码算）；**R3：理由 = artifact 属性**（结论 + 证据指针），reasoning 永不持久化 | ✅ 迭代一（写门证据校验三牙）+ 迭代二（`selectsReady` 里程碑，2026-09-23） |
| 4. 精选 | 画布长 3 个精选节点（各带一句理由）；**用户可随时插话换选**（「第 2 个换第 5 个」——免费、秒级、零仪式） | 终态 `propose_selects`（探索写门）；**R7：Select = 证据引用**，不复制源 | ✅ 迭代一（写门 + 精选卡）+ 迭代三代码层（插话换选 = `revise_selects` 三金钱态：dock 前零仪式 / dock 后原地更新同确认座 / run 后迷你包重确认，2026-09-23；live 待用户走查） |
| 5. 结构化方案 | 3 个方案节点（draft 虚线）：区间 + 字幕样式 + 语言版本 + 文案草稿 | 终态 `propose_plans`；**R9：persona/默认在 Structure 注入**，不参与选段；**R8：Content Plan ≠ Task** | ✅ 迭代一（写门 + 方案卡 draft 虚线）+ 迭代二（生产座位 = `_propose_plans`：预检编译 → 写门 → 决策包 dock，`plansReady` 里程碑，2026-09-23） |
| 5a. 方案自检 | Activity「Verifying the 3 plans… ✓」 | 确定性完整性检查（区间/语言/产出类型/字幕/文案/必填输入）；artifact state `draft → ready` | ✅ 迭代一（写门内完整性自检，2026-09-22） |
| 6. 编译·报价·确认 | 散文收官（3 方案的产品语言 + 总价 + 费用语义）→ **停**——dock pill 或回「开工」，同一座 | **R12 编译移出 LLM**：Content Plan → 确定性编译器 → draft 执行链（ADR-057 K5 形态零改）→ quote=fold → **决策包**（R16）；**R15 停顿定律首次触发** | ✅ 迭代二（2026-09-23）：编译器 `scope_compile` 纯函数 + R14 双门预检（不可编译包零写入）+ 决策包 dock（plans 阅读层 + 编译链证据 + quote）+ R20 Confirmed Scope Snapshot（`run.context.confirmed_scope` 五字段，销 P0-①）+ R15 停顿（propose_plans/revise_plan 终态） |
| 7. 付费执行 | 节点状态周期 + 打勾流动态行（既有零改）；**R18 同框纪律**：探索族退背景（合集自动折叠可审计）、执行族独占运动，plan 节点永不镜像 running | create_run 唯一出生地 + Start 四合取 + hold→capture（全部既有） | ✅ 既有；迭代二加固 = 确认即快照（confirmed_scope 盖戳在出生地成功之后，拒收的 Start 永不留快照） |
| 8. 收官验证 | reviewer 散文 verdict + 建议 pills；scope 内问题自治修，scope 外只提建议 | trigger turn（run 完成白名单，ADR-077 §3 既有）；**B7 结案（R21）**：自检 = 确定性 verify + plan 意图比对，「够不够精彩」归用户纠正；**R22：pill = expansion 提案唯一出口** | ✅ 迭代三代码层（2026-09-23）：`run_review` 兑现审计纯核（confirmed_scope × landed × 实扣对账，缺口保守裁决）+ 触发回合事实注入 + 主观零字 prompt 律；自治修 = P2 挂账；live 待用户走查 |
| 9. 修订 | 「plan 2 的字幕太长了」→ agent 说产品语义（不见 UUID/wiring），自治重渲染零仪式；「plan 2 改德语」→ 新决策包（只含变化 + 价差）→ 重确认 | **R19 修订两分律**：唯一判据 = 结果执行范围 ⊆ 已批准范围（scope classifier 裁决，agent 永不自封 continuation）；**R20：Confirmed Scope Snapshot = 修订路由器** | ✅ 迭代三代码层（2026-09-23）：`revise_output` chat 专用终态（continuation 零仪式 / expansion 迷你包重确认，classifier 唯一裁判原样）+ R20 路由器消费（plan_task_map + @output 双通道，legacy 诚实降级）；live 待用户走查 |
| 10. 新主题 | 「再挑两条关于募资的，照上次的样子」→ 主链原样重跑；上次的候选/精选/方案/产物可回查 | **R23 记忆分层**（事实可复用 / 判断不迁移）；**R26 前作 exemplar**（ADR-078 第四参数源座位）；**R25 反专断**：纠正 = 事实非偏好，升格需显式授权 | ✅ 迭代三代码层（2026-09-23）：Past journeys 有界块（cap 3）+ exemplar 事实行注入（reference-only 永不代码覆写）+ `get_artifact` 读洞销账；R25 升格窄门按 E6 砍出本批；live 待用户走查 |

**决策台账（R1~R26）**——合同全文 = ADR-088/089，本表只记「从哪拍打出什么」：

| 裁决 | 一句话 | 出处拍 | 合同 |
|---|---|---|---|
| R1 | 候选 = 合集 artifact（折叠可展开），不铺独立节点 | 拍 2 | ADR-088 §2 |
| R2 | 免费探索区默认连续工作——纠正成本对称性决定停顿位置 | 拍 2~5 | ADR-088 §5 |
| R3 | 理由 = artifact 属性（结论 + 证据指针）；reasoning 永不持久化 | 拍 3 | ADR-088 §2 |
| R5 | Activity = work session 连续视图，UX 永不暴露 runtime 回合边界 | 拍 2~8 | ADR-088 §6 |
| R6 | 发现型目标才进探索链；「更智能 = 事事探索」永禁 | 拍 0 | ADR-088 §9 |
| R7 | Select = 证据引用（evidence-backed），不复制源 | 拍 4 | ADR-088 §2 |
| R8 | Content Plan ≠ Task（产品语义 vs 执行表示） | 拍 5 | ADR-088 §2 / ADR-089 §2 |
| R9 | persona / presentation 默认在 Structure 阶段注入 | 拍 5 | ADR-088 §2 |
| R10/R17 | Artifact 与 Execution 双状态机；修订发生在哪层决定哪台变化 | 拍 5/9 | ADR-088 §3 |
| R11 | Observation = 阶段相关的 Project View，非一次性 context dump | 拍 3~5 | ADR-088 §7 |
| R12 | 编译移出 LLM；agent 词表纯产品语义 | 拍 6/9 | ADR-089 §1 |
| R13 | 探索族住 Project Artifact Graph；I-EXPLORE-01 永不进执行拓扑/闭包/报价/边语义 | 拍 6 | ADR-088 §4 |
| R14 | 探索写门 / 执行写门双门两套不变量；编译器 = 确定性翻译器非第三门 | 拍 6 | ADR-088 §4 / ADR-089 §3 |
| R15 | **停顿定律（总纲）**：只在移动金钱 ∨ 需要用户独有信息时停；停必带完整决策包 | 拍 6 | ADR-089 §5 |
| R16 | 确认消费 = 方案语义 + 编译范围 + 费用语义；确认戳盖在决策包上 | 拍 6 | ADR-089 §4 |
| R18 | 两族同框不同状态语义（plan 节点永不镜像 running） | 拍 7 | ADR-088 §3 |
| R19 | 修订两分：唯一判据 = 结果执行范围 ⊆ 已批准范围（classifier 唯一裁判） | 拍 9 | ADR-089 §6 |
| R20 | Confirmed Scope Snapshot = 修订路由器（「plan 2」→ 节点集解析索引） | 拍 9 | ADR-089 §4 |
| R21 | Reviewer 自检 = 确定性 verify + plan 意图兑现比对；主观质量归用户 | 拍 8 | ADR-088 §8 |
| R22 | Reviewer scope 内自治修；scope 外 = 建议 pill 唯一出口 | 拍 8 | ADR-088 §8 |
| R23 | 项目记忆四层 + 永不升格清单 + 读取律（当前旅程全量 / 历史旅程摘要+按需） | 拍 10 | ADR-088 §10 |
| R24 | `journey_id` = 产物归属属性，永不成图边 | 拍 10 | ADR-088 §10 |
| R25 | 偏好升格需显式用户授权；重复 N 次不充分（agent 有提议权无升格权） | 拍 10 | ADR-088 §10 |
| R26 | 前作 exemplar = 参数源（ADR-078 第四源座位），不是新业务对象 | 拍 10 | ADR-088 §10 |

**压力测试摘要**：拍 6 接缝——draft 图 K5 / dock pill 唯一座 / G-1 散文同座 / Start 四合取 / D4 结果范围律 / 打字机律 /「只有合法链才进 dock」（B3）/ merge_prior_slots 修订恒胜，全过零改；拍 9 修订回路验收——R12（agent 全程不见 wiring 词汇）/ R16（快照从审计装饰升格为修订基础设施）/ R17（craft 修订 plan 状态不动）/ R15（预授权内不停、新钱必停）。

**挂账**（全部有座）：零探索退化形态（propose_tasks / select_clips 退役弧，PROGRESS 池——select_clips 存留裁决已落 2026-09-23，ADR-089 §8）/ 深度看片复核（PROGRESS 池）/ 常驻自主拨盘（PROGRESS 池）/ Canvas 密度组织学（R24 前提契约已立，PROGRESS 池）。

## 体验规格横切（全旅程通用）

1. **打字机律**（绝对规范）：agent 一切言语打字机节奏，整段瞬移永禁；工具线格式下重述 = 散文走 content 通道、工具调用走相位帧、零 delta 路径 paceSettledProse（CLAUDE.md / CHAT_ARCH §8.6）。
2. **预效果一致性**（ADR-077 判词⑤）：「思路与方向」描述恒从提案对象派生（summary/ops 同体两投影），校验先于庆祝，预览翻案即回滚；不做渲染预览（口头描述与画布一致即可）。
3. **礼仪三件套**：礼貌 echo（认领 + 稍等）+ 过程碎碎念（工具调用叙事）+ 有判断的收官（汇报 + 下一步）。
4. **诚实降级**：做不到 = 带理由 + 替代方案，永不静默排除、永不编造（错误的计划看着像真的，Start 会为它烧一次付费 run——ADR-071 门前判词同义）。
5. **画布 = 展示面**：拖线/连线编辑器永禁（ADR-035）；卡面 prompt 直改与发布/下载是仅有的手势（ADR-058/063）；镜头跟随当前节点（B4）。
6. **活动行 = 回合内穿插的证据行**（2026-09-22 旅程四呈现规格）：散文段与活动/证据行按发生时刻穿插渲染（run 期 `runStreamUnits` 单路径同法的非 run 期套用）；证据行可展开（用户安全摘要 + 耗时），wire 白名单扩字段走 ADR-088 注记（user-safe 纪律不变：永不带 params / raw results / reasoning）；活动流首版不持久化，穿插 = in-session。

## 缺口登记（旅程 → 工程批的映射）

| 缺口 | 旅程拍位 | 工程座位 |
|---|---|---|
| ~~感知 loop（读工具一族）~~ | 一② / 三全表 | ✅ T2（ADR-077 判词②，2026-09-15 落地——perception 七工具） |
| ~~触发回合（主动发声 + 收官 reviewer + 建议 pills）~~ | 一②⑦ / 二①④ | ✅ T3（ADR-077 判词③，2026-09-15 落地——三触发白名单 + wrap_up 校验） |
| 镜头跟随 | 一⑥ / 二③ | B4（纯前端，未做） |
| ~~decompiler + 资产角色 + exemplar 参数源~~ | 二全旅程 | ✅ T5（ADR-078，2026-09-15 落地；残留收口 = R1 B1：remix e2e S16 + run 路径触发回合 + prelude 折叠 + 测试地基复位） |
| op/契约覆盖度（字幕 size·color 等） | 三首行 | PROGRESS 覆盖度池（语料驱动排期） |
| ~~多 provider 线格式三层~~ | 横切 | ✅ T1（ADR-077 判词④） |
| Agent Tools 修复（A-1 程序盲改 + specific_instruction 双哲学对账 + read 洞 d/e） | 四②③横切 | 修复批（审计 `scratch/agent-tools-audit-2026-09-22.md`，2026-09-22 交接） |
| SSE 实流 CoT 审计 | 横切 | 独立取证动作（零代码改动，抓真流验证 reasoning 永不入用户通道） |
| 探索产物族 + 探索写门（候选集 / 精选 / 内容方案） | 四②③④⑤ | 📋 ADR-088 实施批 |
| 能力编译层（Content Plan → Execution Scope + 决策包 + Confirmed Scope Snapshot） | 四⑥⑨ | 📋 ADR-089 实施批 |
| propose_tasks / edit_graph 退役弧（并行 → 证明 → 退役） | 四⑥ | 📋 ADR-089 §8 |
| 活动行呈现升级（散文段穿插 + 可展开证据 + 耗时） | 四全旅程 | Activity 呈现批（横切规格 6；Phase 2 步⑤ 联动） |
