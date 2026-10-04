# 素材待命场景重写 — 施工简报（ADR-101）

> Status: **W1 已落地**（验证全部未跑，用户清单见末节——验证绿后 W2）。架构母法 = ADR-101（回合内有界等待 + 承诺机器退役 + 复读禁止律与 consumed 谓词）。**验证纪律：一切 pytest / prompt_gate / 剧本 / live 复跑由用户自跑**；施工会话只做代码层分析与 review，未跑项在批次 Status 在册。

## 冻结事项（本简报全程不再议）

回合内有界等待（`get_understanding` 行为升级，无新工具名）；等待上限 = configs `chat.material_wait_secs` 默认 120s；承诺机器（marker/stamp/verdict/drop 道）整台退役不修补；复读红线 = 内容重复永禁（不是「review 发不发」）；**复读防守零 prompt——戳/谓词/去重全机械代码路径，prompt 只承载散文内容法（说什么）与工具使用引导（什么时候读），任何「在 prompt 里叮嘱别复读」= 翻案本律**；超时地板 = 宣告等待 + 宣告接力、零内容，review 必达；正文全打字机（G2 + drain 终态，ADR-099 §7 不重开）；trigger 礼貌窗 300s 不动；H3 薄残留（寒暄盖戳吃首读）接受在册。

## W0 彻查清单（W1 施工已逐条回填验证结论）

| # | 隐患 | 结论 |
|---|---|---|
| H1 | 等待上限 ≥ trigger 礼貌窗（300s）→ defer-out 丢沉默 | ✅ 落地：`chat.material_wait_secs` 注册表 desc 钉死 HARD UPPER BOUND 240s（configs.py） |
| H2 | plan assemble 注入 digest → plan echo 复读 | ✅ 落地：写口②（plan_turn assemble：digest 注入即置旗，落行盖戳） |
| H3 | 寒暄盖戳吃首读 | 接受在册（不动，承重观察①） |
| H4 | 戳与 assistant 行不同事务 → 复读竞态 | ✅ 验证通过：`turn_state="settled"` 与 assistant 行同一 commit（service.py:2266-2271）；戳骑 assistant 行 intent → 原子可见先于空闲清除 |
| H5 | 戳 ref 与发火 ref 不同源 | ✅ 验证通过：发火 = `fire_trigger(project_id, TRIGGER_UNDERSTANDING, digest)`（node_runners.py:445）；戳 = `asset_digest(assets)` 同一函数同一资产集 |
| H6 | 120s 工具执行期 SSE 零帧 | ✅ 验证通过：心跳注释在（chat/routes.py:371 `yield ": heartbeat\n\n"`）+ 素材相位 asset 驱动 + inspecting 活动帧 |
| H7 | 等待轮询持长事务占池 | ✅ 落地：每轮 poll 独立短 session（AsyncSessionLocal），回合 session 的未提交写零触碰 |
| H8 | 全 FAILED 空等到上限 | ✅ 落地：`material_wait_verdict` 的 settled_unreadable 早退（纯测试锁） |
| H9 | 等待期客户端只显示冻词 Thinking | ⏳ 未动代码——live 验证项（素材相位应优先于 thinking 行），挂验收清单 live 场景①观察 |
| H10 | 戳载体渲染空泡 | ✅ 落地（首选方案）：戳骑 assistant 行自身 intent，零额外行零渲染面 |

## 拆除面盘点（施工前 grep 复核，以代码为准）

| 面 | 拆除 | 新建/改写 |
|---|---|---|
| schema | `PlanAnswerArgs.material_pending` / `ChatAnswerArgs.material_pending`（schemas.py，含 tolerate_null_keys 条目） | — |
| turn | `plan_turn.py` / `propose_turn.py` 的 material_pending stamp（assemble）与 `_answer` 压制门（plan_turn ~:1605 / propose_turn :1560-1588）；`material_pending_stamped` | `plan_turn.py`：assemble 记录 digest 注入旗 → 落行盖 consumed 戳（写口②）；`_create_message` 加 consumed ref 参数 |
| service | `chat/service.py` 的 `pending_commitment_verdict`（纯核） | — |
| pipeline | `step_context.py` 的 `material_beat_landed` 压制消费面（无其他消费者则连函数删）；`lifecycle.py` / `chat/intent.py` 的 material_pending 引用（以 grep 为准） | — |
| prompt | `_material_pending.j2` 全删 + 两处 include 改写（`chat/intent_router_system.j2` / `chat_intent_system.j2`；`prompts/intent_router.j2` 引用以 grep 为准）；Material status line 承诺法措辞 | 新法一句：「答案依赖内容 → 调 get_understanding，它会把读等出来（有界）；等不到就诚实宣告等待与接力，零内容」；`perception/__init__.py:101` 工具描述补等待语义 |
| configs | — | `platform/configs.py` 注册 `chat.material_wait_secs`（default=120，int，desc 钉 H1 上界 ≤240s） |
| read 工具 | `get_understanding` 的 pending 分支「立即返回不可读 + you will speak again then」措辞 | 有界等待循环（H7/H8）+ 超时返回「仍在处理」事实文本 + 成功返回 digest 时置 consumed 旗（写口①） |
| 测试 | `test_material_pending_pure.py` 退役；`test_lifecycle_pure.py` / `test_suggestion_provenance_pure.py` 收窄（以 grep 为准） | consumed 谓词纯测试（戳写入/去重命中/超时不盖戳） |

**易踩边界**：`DeferredFrames.drop()` 是通用原语**保留**——死的只是两 turn 压制门里的素材待命 drop 调用；`material_beat_landed` 若有压制外消费者（以 grep 为准）只删压制面；G2 缓冲/打字机/pending plan 礼貌谓词（trigger_turn.py:430）一律不动。

## 批次总序

```
W1（行为翻转）→ W2（死码清扫 + harness 改靶）→ W3（文档现行法收尾）
```

- W1 落地后行为整体翻转：等待可用 + 承诺结构性不可发射（schema 字段与 prompt 法同步删除）+ 复读谓词生效。单 commit 可整体 revert。
- W2 零运行时行为变化（死码 + 测试面），与 W1 分开 commit 保归因隔离。
- W3 只在 W1/W2 验收绿后做。

---

## 批次 W1：行为翻转（单 commit）

| 字段 | 内容 |
|---|---|
| **scope** | 等待机制 + consumed 谓词 + 承诺机器运行面拆除（schema/prompt/turn 门），四面同 commit。 |
| **files** | `app/platform/configs.py`（`chat.material_wait_secs` 注册，desc 钉 H1 上界）；`app/chat/perception/executes.py`（`get_understanding` pending 分支 → 有界等待循环：2-3s 短事务轮询 digest 行，落地即返回 digest + 置 consumed 旗；超时返回「仍在处理」事实文本——零「you will speak again」承诺措辞；H8 失败早退）；`app/chat/perception/__init__.py`（工具描述补等待语义）；`app/models/schemas.py`（删两 material_pending 字段）；`app/chat/plan_turn.py`（删 stamp + 压制门；assemble 记 digest 注入旗，落 assistant 行经 `_create_message` 盖 consumed 戳——写口②）；`app/chat/propose_turn.py`（删 stamp + 压制门）；`app/chat/service.py`（`_create_message` 加 consumed ref 参数；`pending_commitment_verdict` 调用面随门删除）；`app/prompts/chat/_material_pending.j2` 删除 + 两处 include 改写 Material status line 新法；`app/prompts/intent_router.j2`（以 grep 为准同步）；consumed 谓词纯测试新建 |
| **depends_on** | 无（独立批） |
| **must_not_touch** | G2/DeferredFrames 本体；打字机/drain；trigger 礼貌窗数值与 pending plan 谓词；`material_beat_landed` 定义（W2 处置）；SSE/相位前端（H6/H9 只验证不改，除非验证红） |
| **acceptance** | ① 素材处理中提问 → 单回合 grounded 答复（等待 narrate + 内容落地），无 review 复读；② 等待超时 → 宣告行零内容 + review 接力必达；③ plan echo 叙述内容后 review 零发射；④ 静默上传 review 照常；⑤ schema 无字段 + prompt 无法 + turn 无门，三面同 commit；⑥ H1-H10 验证结论回填 W0 表 |
| **rollback** | 单 commit git revert |

**W1 落地记录**（施工会话交付，验证全部未跑）：

- **stale-shape 行不盖戳**（施工新抓的边界）：`_render_understanding` 返回 None 表 stale（内容未真正落地）→ 观察文本照旧、digest 返回 None——review 席位留给再生行，与「consumed = 内容消费」谓词严格一致。
- **写口②的精确条件**：assemble 注入 `understanding_lines` 非空才置旗（空 stub 行 = 无内容可叙述 → 不盖戳）。
- **propose_turn 的 processing_count 块整段删除**（只喂 stamp）；`is_pending_plan` import 随门退役（plan_turn 仍用，保留）；`AssetStatus` import 随块退役。
- **测试面 W1 最小手术**：`test_material_pending_pure.py` 删 wire-contract 类（schema 锁随字段消亡），verdict 真值表留到 W2 随函数退役；`test_suggestion_provenance_pure.py` 的 defaults 锁同步；新锁入 `test_material_wait_pure.py`（verdict 真值表 / 形态翻案锁 / 戳骑行三锁 / unready 文本形态）。
- **INTERACTION_POLICY_VERSION → v2**（承诺车道退役 = 交互策略变更）；`ChatResponse` None 注释改写（压制路径消亡）。
- **harness 面未动（W2 改靶）**：S18 / prompt_gate 的 material-pending 合法终态断言在 W1 后行为红 = 本批归因，W2 修。
- **未跑验证（用户清单）**：见末节全量；H9 挂 live 场景①观察。

## 批次 W2：死码清扫 + harness 改靶（单 commit）

| 字段 | 内容 |
|---|---|
| **scope** | W1 留下的死函数/死引用清扫 + 测试面改靶。零运行时行为变化。 |
| **files** | `chat/service.py`（`pending_commitment_verdict` 无消费者连函数删）；`pipeline/step_context.py`（`material_beat_landed` 压制面——无其他消费者连函数删，以 grep 为准）；`chat/intent.py` / `pipeline/lifecycle.py`（material_pending 残留，以 grep 为准）；`tests/test_material_pending_pure.py` 退役；`tests/test_lifecycle_pure.py` / `test_suggestion_provenance_pure.py` 收窄；`scripts/chat_scenarios.py`（S18 改靶 + 新场景四枚：S-wait-1 短素材提问单回合 grounded + 零 review 行；S-wait-2 超时宣告零内容 + review 接力必达；S-wait-3 静默上传 review 回归——现有场景保持；S-wait-4 plan echo consumed 零 review）；`scripts/prompt_gate.py`（S18 相关探针/终态断言改靶，以代码为准——material-pending 合法终态随形态消亡） |
| **depends_on** | W1 验收绿 |
| **must_not_touch** | W0 表外的一切 trigger/相位/打字机面；阈值不降为红而调 |
| **acceptance** | ① 纯 pytest 绿（既有债清单核对先行）；② prompt_gate 全绿（改靶探针在册）；③ 全量剧本绿，红全部归因；④ grep 零残留：`material_pending` / `pending_commitment_verdict` / `material_pending_stamped` 无引用（`material_beat_landed` 视消费者定） |
| **rollback** | 单 commit git revert；改靶红 = 登记读数、不回调阈值 |

## 批次 W3：文档现行法收尾（W2 验收绿后同批）

1. **CHAT_ARCHITECTURE.md**：素材待命/承诺机器/压制面表述收窄为现行法（有界等待 + 复读禁止律 + consumed 谓词 + 地板接力）；trigger 节「家」表述收窄。
2. **NAMING.md**：`material_pending` 族词条删除或改写（以 grep 为准）。
3. **README.md**：单一事实源表行更新（落档批已先加 ADR-101 指针，本批核销「待施工」表述）。
4. **DECISIONS.md**：ADR-101 Status 去「待施工」；如涉及 ADR-099/其他 ADR 的素材待命表述，收窄同步。
5. 本简报 Status 收尾；验收全绿后移 `docs/archive/tasks-done/`（用户执行或授权执行）。
6. **PROGRESS.md**：需求池本批行状态更新；「Turn budget」行核销「诚实降级形态随施工定」挂账（本条已定形）。
7. **commit**：`docs: ADR-101 收口——CHAT_ARCH/NAMING 现行法 + 简报归档`

## 承重观察（在册不处理）

- H3 薄残留（寒暄盖戳吃首读）——若 live 反馈「说了 hi 之后 agent 再也不提素材」，复议谓词加宽度条件（不许 NLP 判宽度的机械方案 = 另案）。
- 等待期 DB 连接占用（H7 处置后的残余）：并发等待回合各持短事务轮询——池水位观察，不预设。
- `chat.material_wait_secs` 调优是运营面：首周 live 读数（等待成功率/超时率）回来后再评默认值。
- consumed 戳不跨项目：理解行内容址跨项目复用（find_reusable_understanding 先例）时，戳仍是 per-conversation——新项目的新会话首读照常，语义正确，仅登记。

## 本批验收（用户自跑清单）

1. `cd apps/api && uv run --extra dev python -m pytest tests/ -q`（既有债清单核对先行——interaction-architecture 简报在册 11 红族，清单外新红 = 异常）
2. `cd apps/api && uv run python scripts/prompt_gate.py`（W2 后改靶探针在册）
3. `cd apps/api && uv run python scripts/chat_scenarios.py` 全量（焦点 S-wait-1/2/3/4 + S18 新靶）
4. live 复跑四场景：① 短素材（<2min 处理）处理中提问 → StatusLine 素材相位 → 单回合真答案，**之后零 review 复读**；② 长素材处理中提问 → 宣告行（零内容）→ beat 后 review 接力必达；③ 静默上传 → review 照常（回归面）；④ 素材就绪后干脆请求 → plan echo 叙述 → 之后零 review
