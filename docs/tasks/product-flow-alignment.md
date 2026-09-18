# Product Flow Alignment — 施工合同（母合同）

> Status: **Active**（2026-09-18 周五滚动拍板，批次注册 = `docs/PROGRESS.md` §0.2）
> 本文是本轮「Upload Staging → 统一工作流相位 → Product Graph 语义与 Layout → 画布出生编排 → E2E」的**唯一施工合同**。批次切分在 §5~§9；架构 invariants 在 §3（Phase 0，动任何代码前先读）；验收 DoD 在 §10；Prohibited Behaviors 在 §11。
> 事实源优先级：`Current code > DB constraints/migrations > tests > ADR > 架构文档 > 历史计划`（PROGRESS §0.4）。本合同中的文件/行号核验于 HEAD `e7d0495`，**行号会漂移——开工前以 current HEAD 重新定位，本合同是导航不是代码事实源**。
> 关联决策：**ADR-086**（拓扑空间权威三律 + Product Canvas ≠ Execution Graph）；吸收需求池行「画布可读性②」（同族链分组 / 长边路由 / 居中随 Batch C 施工）；ADR-057 K5 / ADR-082 / ADR-084 / ADR-085 全部维持不翻案。

---

## 0. 合同使用规则

1. 每个 Batch 开工前做 preflight：读本合同对应节 + 其引用文档 + 核验代码座位（current HEAD）。
2. **一次只做一个 Batch**；不跨 Batch 偷渡；发现合同与 current code 不一致 → 标记 discrepancy 回报，不自行扩大 scope。
3. 验证纪律：纯函数套件 / prompt gate / tsc / 剧本复跑**用户自跑**；Claude 只做代码层分析与 review，报告标「未跑验证」。migration / 状态机 / 并发改动必须有 regression scenario。
4. 每完成一个 Batch：更新本合同该节状态 + PROGRESS §0.2 + commit 号。
5. 行号引用格式 `file:line`；§2 的 root cause 表是本轮全部工作的锚。

---

## 1. 产品目标（从产品需求倒推，不是从代码倒推）

> 用户上传一个视频，希望看到一个清晰的、从原始视频到最终产物的产品工作流，并能在过程中知道系统现在做到哪一步。

技术差距倒推：

```
产品目标
   ├── 选文件后立即上传（Generate 不再等上传）        → Batch A
   ├── 一个统一的工作相位（Chat/Canvas 同源）          → Batch B
   ├── Product Graph ≠ Execution Graph（语义 L→R）     → Batch C
   ├── 工作流状态在节点上原地变化（生长感 = 呈现编排）   → Batch D
   └── 端到端可验收、可回归                            → Batch E
```

**北极星场景**（验收用，§10）：上传 15s 视频 → "Caption my video in Chinese and French — Chinese as bilingual subtitles."

---

## 2. Recon 结论（2026-09-18，三路代码取证；root cause 全表）

### 2.1 Layout：为什么本该在右边的 node 出现在左边

深度-间距律 `x = depth × _PITCH(464)` **只在节点出生时执行一次，既有帧永不移动**（append-only 保序律，`apps/api/app/pipeline/graph_store.py:436-437, 778-779`）。错位五源：

| # | 根因 | 代码座位（HEAD `e7d0495`） | 性质 |
|---|---|---|---|
| L1 | **晚出生的中间节点插到既有节点前面**：翻译/配音两站的 doc 伴侣节点（`{fill_key}#doc`）出生时按新边集定深（x=928），其目标既有装配节点保留旧帧（x=464）→ 边 928→464 向后折返 | `apps/api/app/pipeline/graph_fill.py:922-959, 1085-1086` | 主犯 |
| L2 | **边对账不改帧**：边对账律在既有节点间断开/重连边，帧永不重算，拓扑翻转后列与 DAG 矛盾 | `graph_fill.py:1163-1197` | 主犯 |
| L3 | **pitch 漂移**：迁移脚本重放旧帧用 `_PITCH=436 / _FRESH_COLUMN_RISE=126 / _GAP_CROSS=24`，现行律 464/88/16 → 同一逻辑列被 settled 分支的精确 `frame.x` 分键劈成两列 | migration `e7a9c1d35b28_depth_pitch_frames.py:33-35` vs `graph_store.py:250-285`；消费点 `apps/web/src/components/flow/layout.ts:449-453` | 存量数据 |
| L4 | **空 layout → 原点静默兜底**：`graph_nodes.layout` server_default `'{}'`，前端 `layout.x ?? 0` 静默补成 `{0,0}` 帧 → 钉原点最左 | `apps/web/src/components/flow/ResultsCanvas.tsx:167-172`；第二处 `FlowView.tsx:462`；schema `apps/api/app/models/tables.py:301-302` + migration `d8e9f0a1b2c3:48` | 静默兜底 |
| L5 | **读时合成边**（A3-lite：transcript→consumer text 边）从未参与帧分配 | `apps/api/app/pipeline/routes/projects.py:452-461` | 读面 |

**加重发现（执行正确性，非仅视觉）**：`RunOp` 按 `(layout.x, layout.y)` 排序 run_nodes（`graph_store.py:767-773`），`apps/api/app/pipeline/graph_revise.py:69-73` 注释明示「settled layout 的 x 序就是深度序」——**帧错位可让修订 run 把消费者排在生产者之前执行**。

### 2.2 Upload：Generate 后 1-2 分钟的来源

- composer 选文件 = 纯内存 `File[]`，零网络（`apps/web/src/components/home/HomeComposer.tsx:148, 192-199`；输入座 `AssetsPanel.tsx:38-44`）。
- 上传三连（presign → PUT → asset 行）全部在 `useProjectLaunch.launch()` 内、`POST /projects` 成功**之后**（`apps/web/src/lib/useProjectLaunch.ts:75-135`）；Generate 钮只有 spinner 无进度（`HomeComposer.tsx:582-586`）。
- **对比**：chat dock attach 选文件即传（`apps/web/src/components/chat/ChatDock.tsx:2269-2280`，`uploadStaged` 2217-2267，× 删走 `DELETE /assets/{id}` 2285-2293）——两路结构性不对称。
- 服务端障碍（硬的）：① `Asset` CheckConstraint——project_id/persona_id 必居其一且互斥（`apps/api/app/models/tables.py:150-159`），无主 staging asset DB 层不可能；② presign key 命名空间 `{user_id}/uploads/projects/{project_id}`（`apps/api/app/providers/storage.py:92-94, 112-114`），`create_asset_from_key` 硬拒项目前缀外的 key（`apps/api/app/pipeline/routes/assets.py:126-131`）；③ 无 upload session / 无 attach 端点 / PUT 成功但 asset 行未建的孤儿对象无人回收（`projects.py:696-713` 只在显式删除时清理）。

### 2.3 Chat 生命周期：相位帧已有，三个真缝

- server 相位帧 5 个：`drafting / creating_run / repairing / inspecting(+key) / composing`（`apps/api/app/chat/service.py:2164-2191`）；`understanding` 标签系**故意退役**（service.py:2166-2169 注释）。
- **缝①**：未命名窗口（router 推理 / 首 token 前 / quiet 迭代）回落客户端静态 `chat.thinking`（`ChatDock.tsx:4329-4343`）。
- **缝②**：**相位标签从不自我清除**——只被下一个带标签帧或回合结束覆盖，"Putting it together…" 可比其活动活得久（`ChatDock.tsx:2735-2743`，清除点 2566-2567/3147-3148/3219-3220）。
- **缝③**：`home.generating`（en.ts `home.generating`）= launch 段纯客户端静态文案，随 Batch A 大部分消亡。
- 可见性门 `chatBusy && !proseActive` 为客户端推导（`ChatDock.tsx:4329` + `lib/typewriter.ts:21, 36-42`，IDLE_GRACE 400ms）——**符合已拍板设计**（打字机律），不动。
- streaming/settled 渲染**已统一**（`AssistantText` → Streamdown streaming/static，`ChatDock.tsx:994-1009`）——顾问 Batch E 关闭，仅 Batch E 回归确认。

### 2.4 Canvas 生长：整链 stamp 是设计（K5），「突然出现」另有放大器

- `stamp_draft_graph` 在计划 dock 回合内同步干跑编译，全链 add_node+connect **一个批次**落地（`graph_fill.py:1203-1204`）；run 把同 id 节点原地填充（`stamp_run_graph` 961-1007；`sync_graph_node_for_step` 1428-1534）——run 期零新节点，**这是 ADR-057 K5 图先展示后运行，维持不动**。
- 放大器①：基线帧零动画铁律（`ResultsCanvas.tsx:254-256`）——draft 链到达常与基线就绪同帧 → 整链瞬染。
- 放大器②：基线已立时全部 draft 节点一次 refetch 成批「出生」，120ms stagger 是批次重放不是生长（`ResultsCanvas.tsx:252-265` bornIds；`FlowView.tsx:448-456` bornRanks；`layout.ts:467-472` revealOrder + `BIRTH_STAGGER_MS=120`）。
- 已有的生前移：asset 节点上传落行即出生（`graph_fill.py:234-286`，调用点 `assets.py:157-160`）；transcript 节点同机制（319-367）。
- 节点状态通道：无图级 SSE；`step.updated` → 全量 `GET /graph` refetch（`projects.$id.index.tsx:279-283`；CHAT_ARCH §8 认可模式，**不引事件总线**）。

### 2.5 对账：顾问简报 vs 现状（避免重复施工）

| 简报要求 | 现状判定 | 去向 |
|---|---|---|
| Upload Staging | 真缺口，服务端无 staging 概念 | Batch A |
| 统一 Chat 生命周期 | 大部分已在（5 相位帧 + StatusLine 一座两行 + ADR-084/085 09-17 落地）；残余 = 缝①②③ + readiness gate | Batch B（收窄） |
| Canvas 动态生长 | K5 整链 stamp 维持；node 状态已 server 驱动；真缺口 = 出生编排 | Batch D（呈现层） |
| 语义 layout 修正 | 真缺口 L1-L5 + RunOp 执行序污染 | Batch C |
| streaming/settled Markdown | **已落地** | 关闭，Batch E 回归确认 |
| Product Canvas ≠ Execution Graph | **代码层面已大体成立**（task_book B1-lite 读面隐藏 / B4-lite modifier 收编 / workflow_steps 永不上画布）——本轮 = **追认为 invariant + 锁准入闸**，不是重建 | §3 I-PFA-01 + Batch C-0 |

---

## 3. Phase 0 — 架构 Invariants（动任何代码前先立；违反 = 验收不通过）

> 用户拍板（2026-09-18）的三原则 + 本轮派生律。ADR-086 是其决策层落档。

- **I-PFA-01｜Product Canvas ≠ Execution Graph**：画布节点 = **用户拥有、消费、验证或可能修改的产品对象**（user-meaningful product object——**含最终产物与可编辑中间工作产品**：transcript / 翻译文档 / 分镜表 / 字幕文档 / 渲染视频等；媒介五值 + asset/document 读面，ADR-072 词表 v3 为词汇基线），永不是纯执行步骤。`task_book / preprocess / understand / plan / materialize / render / verify / checkpoint / worker / queue / retry` 类概念永不上画布。现行 read-face 过滤（B1-lite / B4-lite / `_read_face`）追认为本 invariant 的执行机制；**准入闸：新图节点类型 / 新 spec.tool 必须声明 product visibility，默认隐藏**。「不是最终产物」永不是隐藏理由——分镜表回答「为什么是这三条」，是合法 Product Canvas node（ADR-072 先例）。
- **I-PFA-02｜拓扑/语义 rank 是唯一空间权威，frame 是呈现 projection**：一切用户可见位置推导的上游 = Product DAG 拓扑（rank = 拓扑深度）。`graph_nodes.layout` 帧收窄为 **y 座位 / w·h 预留 / 稳定锚**三职；**x 的显示值 = rank 的投影**，服务端出生帧的 x 不再是显示依据。append-only 保序律对 y/稳定锚不变。
- **I-PFA-02a｜rank 的输入边界**：rank **只消费当前 Product DAG 中表达生产/消费关系的语义边**（semantic production/dependency edges——含读时合成边中表达真实物料流的 A3-lite transcript→consumer 边）；**历史血缘、跨 run 关系、纯呈现关系的边（lineage / historical / presentation-only）不得参与 rank 计算**，永不改变当前图的水平排位。ADR-036 的 lineage/dependency 区分是本法的历史母体——施工时 `rank = topological_depth(all_edges)` 这类全边消费写法 = 合同级缺陷。
- **I-PFA-03｜方向不变量**：一切用户可见 edge 满足 `rank(target) > rank(source)`；渲染满足 `x(target) > x(source) + MIN_GAP`（MIN_GAP 随施工定，初值 = `_PITCH`）。sibling 序稳定（同 rank 列内 y 序确定性）。**不依赖 node birth order。** 校验 = 纯函数 invariant 测试（layout 投影层）+ dev 显式失败 / prod graceful fallback（见 L4 处置）。
- **I-PFA-04｜Run order = DAG topology，永不读 layout.x**：`RunOp` 排序改读图边拓扑深度；`graph_revise.py` 的「x 序 = 深度序」假设随修随删。执行顺序与视觉坐标解耦——二者可共享同一 Product DAG，**视觉坐标永不做执行依据**。
- **I-PFA-05｜生长 = 呈现编排，节点语义一次 stamp**：ADR-057 K5 不翻案（计划确认前用户看到完整链 + 逐节点估价 = fold 报价前提）。「动态生长感」由出生编排（reveal 节拍 / loading → ready 原地状态迁移）承载；**loading → ready 是同一个 node 的更新，不是新建 node**；不把内部 execution task 逐个变成画布节点。
- **I-PFA-06｜统一相位，Chat/Canvas 同源，相位显式终结**：用户可见的「现在在干什么」= server 事件/状态驱动的同一事实的两个读面（Chat = StatusLine 相位；Canvas = 节点状态）。UI 不猜系统在干什么。相位标签必须有显式生命周期——**任何相位不得比它的活动活得久**（清除协议随 Batch B 施工定型：下一相位覆盖 / 活动终止帧 / 回合结束三座）。
- **I-PFA-07｜readiness gate**：内容依赖型回答（读素材 / 读转写）面对「素材仍在处理」= **诚实相位叙事 + 等就绪后主动说**（触发回合既有机制），永不产出依赖半成品的假回答，也永不让 LLM 独自面对未就绪世界。「我不能读」类失败回答 = 合同级缺陷。
- **I-PFA-08｜staging 生命周期完备**：staging session 状态机 `created → uploading → uploaded → attached`（+ `failed / expired`）；孤儿 reaper 必选不是可选——任何「上传了但没 attach」的对象有时限回收路径。

---

## 4. 现状架构依据（施工前必读清单）

- `docs/ARCHITECTURE_NORTH_STAR.md` §2.1（内容世界六概念——graph_node vs workflow_step 永分）
- `docs/CHAT_ARCHITECTURE.md` §5（物化/wiring）/ §8（SSE）/ §8.6（相位帧 + 打字机律）/ §8.7（RunTaskList 显示律）
- `docs/DECISIONS.md`：ADR-036（布局自算 + append-only）/ ADR-057（图即产品对象，K5）/ ADR-062（边对账律）/ ADR-067（出锚语义律）/ ADR-082（呈现纪律——判词① 客户端空气压缩 = Batch C 呈现层修法的直接先例）/ ADR-084/085（言语语义管线 + 三层交付）/ **ADR-086（本轮）**
- `apps/api/app/pipeline/graph_store.py` / `graph_fill.py` / `graph_revise.py`；`apps/web/src/components/flow/layout.ts` / `ResultsCanvas.tsx` / `FlowView.tsx`

---

## 5. Batch A — Upload Staging Session

> **状态：代码已落（2026-09-18，验证归用户自跑）**。落地座位：服务端 = `apps/api/app/pipeline/routes/staging.py`（presign + × 删）/ `assets.py` `create_asset_from_staging`（attach，两扇窄门）/ `app/pipeline/staging.py`（reaper，TTL 24h）/ `worker.py` 小时级节流；前端 = `lib/stagingUploads.ts`（会话 + XHR 真实进度）/ `useProjectLaunch.ts`（launch = 建项目 + attach + 导航；未竟上传阻塞 toast）/ `HomeComposer` / `AssetChips` / `AssetsPanel` / `RecipeInspectOverlay`。**零 migration**（预期兑现）。tsc 两处报错为 HEAD 基线既有（`ChatDock.tsx:2626` / `layout.ts:459`，ADR-082/085 批残留，本批未触）——验收时一并核。

**Problem**：选文件零网络；Generate 后串行承担 建项目 + presign + 全量 PUT + 建行 + 导航（1-2 min 黑窗）；dock 与 composer 上传时序结构性不对称；孤儿对象无回收。

**Current behavior**：§2.2 全表。

**Desired behavior**：

```
file selected → staging upload 立即开始（真实进度 %）
             → uploaded ✓（chip 生命周期 = dock 既有解剖）
用户继续编辑 prompt
Generate → create project → attach staged（秒级）→ 导航 → 首条 /chat
```

**Data/state flow**：staging key 命名空间 `{user_id}/uploads/staging/{session_id}/{file}`（session_id 客户端生成 uuid，所有权证明 = key 前缀的 user_id）；attach = asset 行直接引用 staging key（**零服务端拷贝**——delete 语义按 key 删，与对象住哪无关）；reaper 跳过被 asset 行引用的 key。

**Implementation steps**（施工时以 current HEAD 核验）：
1. 服务端：项目外 presign 端点（`POST /uploads/staging/upload-url`；auth 同既有；key 前缀锁 `{user_id}/uploads/staging/`）。
2. 服务端：attach 端点（`POST /projects/{id}/assets/from-staging`）——校验 key 属本用户 staging 前缀 + 对象存在 → 走既有 asset 落行 + `stamp_asset_node` 路径；**不放松** `create_asset_from_key` 的项目前缀校验（新端点新前缀，两个门各自收窄）。
3. 服务端：staging reaper（TTL 扫描 staging 前缀、未被 asset 引用的对象 → 删；座位随 worker 既有扫描族）。
4. 前端：`useProjectLaunch` 改造——upload 上提至 pick 时刻（composer chips 生命周期解剖复用 dock `StagedUpload` 模式：uploading → done/error，× 删 staging 对象 best-effort）；`launch()` = 建项目 + attach + 导航；recipe overlay 同路径（共用 hook 现状不变）。
5. DB：**预期零 migration**（asset.project_id 在 attach 时落，CheckConstraint 天然满足）；若施工发现必须加列 → 走 Alembic 流程并在此登记。
6. 失败语义：上传失败 chip 可重试；Generate 时仍有未竟上传 = 阻塞 + toast（同 dock `handleSend` 闸）；prompt-only 发送零 asset 路径不变。

**Acceptance**：选文件即见真实进度；Generate 不再等待上传（秒级到项目页）；attach 后 asset 行 + 画布 asset 节点与现行一致；失败可重试；多文件；× 删除；孤儿对象有 reaper 覆盖（含「PUT 成功未 attach」窗口）。

**Prohibited**：Generate 后才开始上传；静默建 project 当 staging；服务端整对象拷贝当 attach；新上传抽象大厦（最大复用现有 3-step / chip 解剖）。

---

## 6. Batch B — 统一相位 / Chat 生命周期（收窄版 + readiness gate）

> **状态：代码已落（2026-09-18，commit `308c7a7`，验证归用户自跑）**。
> **缝①+缝②（相位清除协议，I-PFA-06 定型——覆盖律 / 清除帧 / 终帧律，全文 = CHAT_ARCH §8.6 末段）**：无相位映射的调用名（ask_user / answer / start_run）一成为已知，server 发显式清除帧 `{"phase": null}`（发射座 = `apps/api/app/chat/routes.py:_make_tool_hooks.on_tool_call` else 分支）；client `"phase" in payload` 区分清除帧与裸 keepalive（`apps/web/src/lib/chat-stream.ts` 类型 + `ChatDock.tsx` 两处 onThinking）；sendChat 补上信封/失败路径的归零 parity（终帧律，与 streamAnswer 同座）。零新相位名、零新 i18n key、打字机律两牙与 `chatBusy && !proseActive` 可见性门未动；静态 `chat.thinking` 回落只剩真黑窗（首帧前）。
> **readiness gate（I-PFA-07）**：就绪事实改为代码盖章——plan path assemble 计算 processing/failed 文件数，盖 `material_pending_line` 进上下文（`plan_turn.py` assemble → `intent.py:_assemble_plan_turn` → `intent_router.j2` 渲染块；`material_state` 三值枚举不动——它是根判断的存在性语义，就绪事实走独立 context line）；grounding 两态诚实推广到 answer 路径（`chat_intent_system.j2` Rules 新增 Material readiness 条款 + `intent_router_system.j2` 条款认知 Material status 行）；「我不能读」类路径消灭 = `executes.py:get_understanding` 的 pending/failed 拆分（failed 不再被说成 "still processing"，删掉诱导编造的 "answer from what you know"）+ `get_asset` 的 failed 分行。就绪后主动说 = 既有 `understanding_warmed` trigger（ADR-080 座位不动；pending task_book 时按单一叙事者律合法静默）。
> **缝③**：`home.generating` 在 Batch A 后已是零消费死 key（launch 窗 = 秒级，send 钮 spinner 即全部 UI）——en/zh 两 locale 的死 key 已删，不新增状态机、不新增文案（launch 窗诚实形态 = spinner 本身）。
> prompt 面改动（`intent_router.j2` / `intent_router_system.j2` / `chat_intent_system.j2` + `executes.py` observation 文本）**必须过 prompt gate 才算完工**（用户自跑）。

**Problem**：相位标签无显式生命周期（缝②：stale phase 比活动长寿）；未命名窗口回落客户端静态 "Thinking…"（缝①）；内容依赖回答面对未就绪素材的 race（「video still processing」类回答）；launch 段静态文案（缝③，Batch A 后重估）。

**Desired behavior**：I-PFA-06 / I-PFA-07。`home.generating` 窗口随 Batch A 缩到「建项目 + 导航」秒级后，剩余缝逐个关闭。

**Implementation steps**：
1. 相位清除协议定型并施工（候选：工具完成/活动终止时 server 发清除帧 or 下一相位帧协议化覆盖；**首选最小协议**，不动打字机律与 `chatBusy && !proseActive` 可见性门）。
2. fallback 窗口收窄：`chat.thinking` 静态回落仅存于「首 token 前 + 无任何相位」真黑窗；其余窗口必须有名。
3. readiness gate：plan path / answer path 面对 `material_state=attached ∧ understanding 未就绪`——诚实相位叙事 + 就绪触发回合主动说（复用 ADR-080/084 既有座位：trigger 白名单「理解完成」+ grounding 两态诚实判词③ 推广到 answer 路径）；盘点并消灭「我不能读」类回答路径。
4. 缝③：launch 段文案随 Batch A 重估——保留则为诚实单相（"Creating your project…"），不新增状态机。

**Acceptance**：一个用户回合 = 一个连贯的 server 驱动相位序列；无 stale 相位；processing 未完前无依赖 transcript 的假回答；Chat 相位与 Canvas 节点状态同拍（同一 step.updated / 同一事实源）。

**Prohibited**：为相位再建一套客户端状态机；给 LLM 加「等一等再答」的 prompt 补丁当 gate（gate 是代码的不是言语的）；动 ADR-084/085 已落机制（read 静默律 / checkpoint 路由）；动打字机律两牙。

---

## 7. Batch C — Product Graph 语义模型（C-0）+ Layout 修正（核心技术批）

### C-0  Product Graph schema 定义（先于一切 layout 改动）

> **状态：收口（2026-09-18）——代码 commit `e31503e` + `0308589`；canonical fixture 13/13 绿（同日实跑）；Post-Compact Forensic Audit = PASS WITH DEBT（只读归档，零修改）**。Debt 挂账：F1/F2（谓词对 legacy materialize 行非 read-face 不变 / modifier 无条件 hidden vs B4-lite 认领闸）→ 消解规则随 C-1 开工第一句落档（read-frame = 既有行 membership 权威，谓词 = 新类型准入闸，rank 在 read-frame 边集上算）；F3（ctx 边仍在 graph_fill.py:1072 出生 vs ADR-072「ctx 退役」字面漂移）→ 待裁决是否登 §12。
> **契约模块 = `apps/api/app/pipeline/product_graph.py`**（pure，no DB / no ORM——duck-typed 行同吃 ORM 与 A3-lite 合成 dict）：四层分离前两层的唯一定义家——Product DAG membership（`is_product_node` / `is_rank_edge`）+ rank/拓扑序（`product_ranks` / `topological_order`，longest-path + cycle guard，二者同一事实源——C-2 的 RunOp 排序消费点）+ 投影原语（`project_x` / `sibling_order` / `validate_product_graph`，C-1 呈现层消费点）。**「layout 是 Product Graph 的投影，而不是 Product Graph 本身」已写入契约 docstring**（用户拍板原话入档）。
> **product edge 全集（I-PFA-02a 输入边界）**：`RANK_EDGE_TYPES = {video, audio, text}`——`ctx` 引用流（task_book → 消费者）永不参与 rank；当前图不存在 lineage / presentation-only 边词（版本血缘住节点 `spec.output_ids`，从不是边），未来出生同样不入。A3-lite 合成边中表达真实物料流的 transcript→consumer 边是 rank 的合法输入（L5 根修口径）。
> **准入闸 = 等效机制（合同本条款明允「注册属性或等效机制」）**：visibility 声明在 **type 层**（ADR-076 的 type 轴本来就是产品对象轴——媒介五值出生即可见），例外走两个显式枚举（`HIDDEN_ROLES = {task_book}` = B1-lite 的声明式形态；`LEVER_TOOLS = {reframe_clip, add_music, remove_filler}` = B4-lite 的声明式形态；读路径的产物认领安全闸留在读面不复制）；`TRANSITIONAL_TYPES = {modifier, materialize}` 过渡词隐藏；`LEGACY_VISIBLE_TYPES`（asset / document / generator / processor / agent）读容忍可见；**未知 type default-deny**——新图节点类型不登记就不上画布。NodeBase registry 未动（visibility 是 type 层谓词，不是 per-kind 注册属性，不建平行映射表）。
> **Canonical fixture = `apps/api/tests/test_product_graph_pure.py`**：北极星六节点（Source→Transcript→CN/FR subtitles→CN/FR video，含 asset→asm 的真实 video 边——rank 由最长路径决定 asm=3 层而非 1 层）+ 三 decoy（task_book / modifier / 未知 type），五断言（membership / edge membership / rank 0·1·2·2·3·3 / x 方向 / sibling 序插入序无关）+ 三负例（丢 Transcript 层 rank 必变 / 反向边必被 `validate_product_graph` 点名 / decoy 永不可见）。
> compileall + 冷导入已过；fixture 13/13 绿（2026-09-18 实跑）。

1. 定义 **product edge 全集**：经 read-face（B1-lite / B4-lite / `_read_face`）+ A3-lite 合成边后的用户可见图 = Product DAG；明确每类节点/边的 product visibility 声明（I-PFA-01 准入闸落地为注册属性或等效机制）。
2. 定义 **rank**：Product DAG 上的拓扑深度（含合成边参与计算——L5 的根修：合成边不再是「读时补丁」，而是 rank 计算的合法输入）。北极星场景的目标形态（验证 rank 定义用，**不是硬编码模板**）：
   ```
   🎥 Source(rank0) → 📄 Transcript(rank1) → 🇨🇳 CN subtitles(rank2) → 🇨🇳 CN video(rank3)
                                          ↘ 🇫🇷 FR subtitles(rank2) → 🇫🇷 FR video(rank3)
   ```
   「bilingual」= 产物/节点属性，不为此造执行节点（I-PFA-01）。
3. 定义 **layout projection**：`x = rank × PITCH + sibling 序稳定`；y = 既有服务端帧 y + ADR-082 判词① 空气压缩（不动）；w/h 预留与 `DOCUMENT_MAX_H` 两镜像律不动。**edge routing（贝塞尔 / 端口法则 / 出入锚）一行不动。**
4. **Canonical fixture（防「几何绿、语义错」假绿，验收必带）**：北极星场景的最小产品图 fixture，同时断言五件事——① node membership（恰好这些产品节点，无执行节点）；② edge membership（Source→Transcript、Transcript→CN/FR、CN/FR→各自 Video，无多无缺）；③ rank（0/1/2/3 四层）；④ x 方向（每条 product edge `x(target) > x(source) + MIN_GAP`）；⑤ sibling 序（同 rank 列内确定性 y 序）。几何 invariant 单独绿不算绿——图本身错（如 Source 直挂 CN/FR 丢了 Transcript 层）时 fixture 必须红。

### C-1  呈现层投影改造（L1/L2/L3/L5 的视觉根修）

> **状态：代码已落（2026-09-18，commit `5056e18`；vitest 9/9 + C-0 fixture 13/13 + tsc baseline 2 错不增，Claude 已跑；视觉 e2e 归用户）**。
> **服务端 rank 上线**：`get_project_graph` 在 read-frame 最终形态（B1/B4 过滤后 + A3-lite 合成边后，projects.py 注入点）调 `product_ranks(nodes, edges)`——节点此时携带 storage 词（legacy materialize 行 = generator 等 → 谓词判可见 → 拿 rank，F1 由注入点结构性消解）；`GraphNodeResponse.rank: int | None`（schemas.py，注释钉约束❶ = read-time projection，非持久态非独立权威）；B4 闸存活 modifier 孤儿行得 `None`（约束❷ 唯一合法来源）。
> **Canvas settled 投影**：`layout.ts` 新增导出纯函数 `projectSettledFrames(nodes, edges)`——列分键 = rank（不再读精确 `frame.x`，436-pitch 旧帧天然消化）；x = rank × PITCH（PITCH=464 三镜像互引）；ranked 节点永不读 `frame.x`；rank-null 节点回退 `frame.x` 兼容显示**且**其 product edge 必入 `violations`（兼容显示 ≠ 合法拓扑）；y = ADR-082 空气压缩不动；`revealOrder` = rank 升序 + 帧 y（Batch D bornRanks 自动吃真深度序）；dev 下 violations `console.error` 可观测（dev-throw/L4 处置归 C-3）。`layoutFlow` 的 frame-less 分支钉界为 **recipe surface 专用**（depthOf 只服务它；draft 节点出生即带帧走 settled/rank 路径——约束❸）。
> **验收套件**：`apps/web/src/components/flow/layout.test.ts` 七例——含旗舰 L1 回归（帧 928/464/100 与拓扑完全脱节 → 投影严格 0/464/928）与 rank-null 违例点名负例。

> **实现边界（2026-09-18 开工拍板，先于一切 C-1 代码）**：
> **F1/F2 消解规则**——① Canvas membership = **read-frame 既有行 membership**（过 B1-lite/B4-lite 闸后发出即可见；C-0 谓词不反向过滤既有行，legacy materialize 行由注入点选在 storage 词层结构性消解）；② C-0 predicate = **新类型/新 tool 的准入闸**，不做存量过滤器；③ rank input = **read-frame 最终边集**（持久生产边 + 合法 A3-lite 合成边），永不在裸 DB 行上算。
> **三条钉死约束**——❶ `GraphNodeResponse.rank` 是 **read-time Product Graph projection**：不持久化、不是 node 自身事实、不是独立 graph authority；❷ **rank-null = 异常兼容态**（唯一合法来源 = B4-lite 安全闸存活的 modifier 孤儿行）——兼容显示 ≠ 合法拓扑，**任何 product edge 任一端点 rank-null 必入 violations**，永不静默；❸ **draft = Product Canvas 的一种 state**（出生即带帧，走 settled/rank 路径）；layout.ts 的 frame-less 分支 = **recipe surface 专用**，不构成第二套 Canvas layout authority。
> **不可妥协验收句**：`layout.ts` 的 settled 图画布路径不得自己推 depth——**视觉正确但 depth 自推 = C-1 未完成**；前端不得重新计算 rank/depth（任何「新 rank helper」= 第二事实源，与 depthOf 同罪）。
> **静态验收链**：`get_project_graph` 注入点 → `GraphNodeResponse.rank` → `GraphNode.rank` → `FlowNode.rank`（ResultsCanvas 透传）→ `projectSettledFrames()` → `frame.x`——任何一段重算 topology 即判不通过。

**Preflight 纪律（2026-09-18 拍板③）——「零数据迁移」≠「legacy 图一概不碰」**：三族存量各行其道——**旧 frame** → 不迁移，rank projection 显示消化；**旧 edge** → 按 ADR-062 边对账律**正常自愈**（旧编译器产生、现行不再发射的边该 retract 就 retract——对账是既有写口行为，不是数据迁移）；**旧 node** → 按 read-face / 图语义既有规则判断。施工人员不得以「zero migration」为由冻结边对账，否则 L2/L5 永远存在。

- `layout.ts` settled 分支：列分键从「精确 `frame.x`」改为「rank 投影」；`nodes.every(n => n.frame)` 的激活条件随投影改造重审（空帧行不再阻塞投影）。
- 显示推导纯函数化，可测：输入 = Product DAG（nodes + product edges + 既有帧 y/w/h），输出 = 每节点 display frame；invariant 断言内建（I-PFA-03）。
- **服务端帧零改动**（ADR-082 判词① 先例：呈现层合法工具箱）；存量数据（L3 的 436-pitch 帧）无需迁移——投影天然消化。

### C-2  执行序解耦（L1/L2 的执行根修）

> **状态：代码已落（2026-09-18，commit `494490b`；纯函数套件 74/74 绿 Claude 已跑，含 3 个 C-2 回归新例；跨存量错位帧项目的真实修订 run 验证归用户 e2e）**。
> **RunOp 排序键**：`(layout.x, layout.y)` → `(rank, id str)`——`product_ranks(nodes.values(), edges, gated=False)`（graph_store.py RunOp 分支；直索引不兜底，缺 key = 契约违例响亮炸）。**`gated=False` = 执行拓扑消费的合同形态**：visibility 闸是画布准入门（I-PFA-01）不是执行过滤器——morph modifier 对画布隐藏但是可执行步骤，必须排在生产者与消费者之间；边输入边界（物料流三值）两模式一致，只有节点过滤不同（`product_graph.py` docstring 钉死）。
> **「x 序 = 深度序」假设删除**：`graph_revise.py:tasks_for_graph_nodes` docstring 改写为拓扑序事实源；执行面 grep 复核——jobs/orchestrator/propose_turn 零 layout 读取残留。
> **Regression scenario（合同强制）**（`test_graph_wiring_pure.py`）：① 帧与拓扑完全相反（928/464/0）→ run_nodes 仍生产者先于消费者；② canvas-hidden modifier（reframe_clip）排在 producer/consumer 之间；③ 同 rank tiebreak = id str 确定性，永不读 layout；既有 `layout order` 测试改名 topology order（断言不变——帧与拓扑一致时两律同果）。

- `RunOp`（`graph_store.py:767-773`）排序键从 `(layout.x, layout.y)` 改为图边拓扑深度（同 rank 定义，单一事实源）；`graph_revise.py:69-73` 假设删除。
- **这是 R1 执行面改动**：必须带 regression scenario（修订 run 拓扑序 = 生产者先于消费者；跨存量错位帧项目验证）。

### C-3  空帧兜底显式化（L4）

- 出生地保证：`apply_wiring_ops` 唯一写口内，任何落行节点必带合法帧（缺 = 出生地拒绝或补算，二选一施工定）；存量 `'{}'` 行盘点。
- 前端 `layout.x ?? 0` / `?? {x:0,y:0}` 两处静默兜底删除——**dev 显式失败（throw/assert），prod graceful fallback**（fallback = rank 投影，不是原点）。

**Acceptance**：全部用户可见 edge 严格 L→R（invariant 测试绿）；sibling 序稳定；不依赖 birth order；存量错位帧项目渲染正确且**零数据迁移**；修订 run 执行序 = 拓扑序；edge routing 视觉无损（现有柔和曲线 / S curve / 锚点保留）；需求池「画布可读性②」三残留（同族链分组 / 长边路由 / 居中）随本批吸收或明确拆分登记。

**Prohibited**：重写 edge routing / 改直线；用 clamp / 翻转 edge / 固定 x-y hack 掩盖拓扑；为排线新增语义节点或假边（ADR-082 呈现/语义隔离铁律）；迁移存量帧；引 dagre 等外部布局库（ADR-036 判词）；服务端重排帧写 DB。

---

## 8. Batch D — 画布出生编排（生长感，呈现层）

**Problem**：draft 链整批瞬染（放大器①②）；「生长感」缺位。

**Desired behavior**：I-PFA-05。asset/transcript 节点生前移（已有机制）+ draft 链到达 = 深度序 reveal（现成 `revealOrder` + `BIRTH_STAGGER_MS` 消费）；run 期 = 节点原地状态迁移（draft 虚线 → running 擦除 → done 内容自证，现行节点视觉律不动）。

**Implementation steps**：
1. 基线零动画铁律开**一道**例外：draft 链到达（`onDraftGraphChange` 节拍）走 reveal 编排；其余基线路径不动。
2. 批次重放改真深度序：bornRanks 按 rank（C-0 定义）而非 refetch 批次。
3. 护栏：`prefers-reduced-motion` 退化瞬染；相机律 C6 不动（draft 到达 fit 既有）；背景 refetch 永不动相机/不重排。
4. refresh/reconnect 恢复正确 graph（既有 refetch 路径回归）。

**Acceptance**：draft 链按生产顺序逐节点显现（可感知的「搭起来」节拍）；既有节点不跳位；run 期状态原地迁移无整图抖动；reduced-motion 瞬染。

**Prohibited**：改 stamp 语义（K5 不动）；把 execution step 变节点；动画库大引进；为生长感让服务端逐节点 drip-feed。

---

## 9. Batch E — E2E 验收 + 回归收口

1. **北极星场景实跑**（§1）：上传 15s 视频 → CN bilingual + FR 字幕。十二拍全绿（§10）。
2. streaming/settled Markdown 同一渲染器回归确认（顾问 Batch E 的形式关闭）。
3. 纯函数套件新增：layout 投影 invariant（I-PFA-03）+ RunOp 拓扑序；既有套件全绿（用户自跑）。
4. 需求池「画布可读性②」行核销/拆分登记；本合同各 Batch 状态回填；PROGRESS §0.2 更新。

---

## 10. 全局 Definition of Done（不得以「页面看起来好多了」收尾）

**Upload**
- [ ] 选文件/拖入后立即开始上传，有真实进度
- [ ] Generate 不再等待上传
- [ ] staged asset 可 attach 到新 project（asset 行 + 画布节点与现行一致）
- [ ] staging 有过期/孤儿清理（含 PUT 成功未 attach 窗口）
- [ ] 失败可重试；多文件；× 删除

**Workflow / Chat**
- [ ] Chat 与 Canvas 使用同一相位事实源
- [ ] 无 stale 相位（相位不比活动长寿）
- [ ] processing 未完前不产生依赖 transcript 的假回答（readiness gate）
- [ ] 无独立的 Thinking/Putting-it-together 生命周期残留（除真黑窗 fallback）

**Product Graph**
- [ ] Canvas 只展示用户可理解的 artifact（I-PFA-01 准入闸落地）
- [ ] node id 稳定；loading → ready 是同一 node 更新
- [ ] Product DAG / rank / projection 定义落档（C-0）

**Layout**
- [ ] 全部 product edge 严格 L→R：`rank(target) > rank(source)` 且 `x(target) > x(source) + MIN_GAP`（invariant 测试）
- [ ] sibling 序稳定；不依赖 birth order；不依赖旧 frame 判执行序
- [ ] RunOp 使用 topology order（regression scenario 绿）
- [ ] 现有曲线/锚点 routing 视觉无损；存量零迁移

**Dynamic Canvas**
- [ ] draft 链深度序 reveal；状态随 workflow 原地变化
- [ ] 状态更新不导致整图抖动/重排；背景 refetch 不动相机
- [ ] refresh/reconnect 恢复正确 graph

---

## 11. Prohibited Behaviors（本轮全局）

1. 重写 edge routing / 曲线改直线；CSS transform / clamp / 翻转 edge 掩盖错误位置。
2. 为排线新增语义节点、假边、或改执行拓扑（ADR-082 铁律）。
3. 服务端重排帧写 DB / 迁移存量帧；引 dagre 等布局库。
4. 把 execution DAG 任何概念（task_book / preprocess / understand / plan / materialize / render / verify / queue / retry）放上画布。
5. Generate 后才开始上传；静默建 project 当 staging；服务端整对象拷贝当 attach。
6. 为相位/生长再建客户端状态机；SSE 事件总线化（事件存储/投递保证/重放）。
7. 动打字机律两牙；动 ADR-084/085 已落机制；动 ADR-057 K5。
8. 修改 R1 已验收执行 invariants（I-EXEC-01~04）——RunOp 排序修正除外，且必须带 regression scenario。
9. 把 TARGET/PLANNED 写成 CURRENT；用「截图好看了」冒充状态语义修复。
10. 大规模重构不相关模块；registry 无评审膨胀。

---

## 12. Discrepancies 登记（施工中发现即追加）

| # | 描述 | 发现日期 | 处置 |
|---|---|---|---|
| D-PFA-01 | legacy `materialize` type 行的 visibility 张力：I-PFA-01 明列 materialize = 执行概念永不是 product node，C-0 谓词（`TRANSITIONAL_TYPES`）判 hidden；但现行 `_read_face` 对旧 materialize 行的一帧映射使其在画布可见（持有真实产物的旧行）。C-0 不接读面、不动现行行为——谓词与读面在 legacy 行上暂时不一致 | 2026-09-18 | 随历史清理批收编（与 modifier/materialize 过渡词的 formal 收编同批）；本批不动 |

已知落差（Recon 已确认，施工时按合同处置，不算 discrepancy）：
- `tool_loop.py` docstring「三扇写门」枚举滞后（North Star §3.3 已登记，本轮不动）。
- 需求池「画布可读性②」与本 Batch C 的吸收关系在 Batch E 核销。

## 13. 文档同步清单（Batch E 收口时核对）

- [ ] 本合同各 Batch 状态 + commit 号
- [ ] `docs/PROGRESS.md` §0.2 + 需求池「画布可读性②」行
- [ ] ADR-086 Consequences 回填（落地座位）
- [ ] `docs/CHAT_ARCHITECTURE.md` §8.6（相位清除协议若定型）
- [ ] `docs/MODULE_ARCHITECTURE.md`（新端点 / 新表若有——staging 预期零表）
