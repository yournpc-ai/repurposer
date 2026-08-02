# agent-loop-upgrade 实施简报——recipe 合并代数 + 提案信道硬化 + 壳/核归拢

> Status: ✅ 已落地（2026-08-02 当日立项当日完成）：W1–W5 全部代码 + 文档归位；e2e 已验 13 条——HTTP 场景 5 条（未改模板回归 de/fr/es / 改中文 zh 生效 / 顺手加文章加性存活 / 未点名语言默认兜底 / 422 矩阵）+ 机制 8 条（fork 参数流入 mode② spec、_run_origin 派生、记账+undo 回滚、remove_filler op、瞬时重试 attempt 1/2 复位 pending、预算耗尽 failed+级联跳过、确定性失败快速失败）。**留周五验收**：真实媒体全跑（chat "再来一版" fork 出派生行 + morph 覆盖 + 前端 undo 按钮）；provider 级瞬时故障注入为可选项。
> 依据：ADR-033（能力层/适配层）；ADR-032（Operation Model 写纪律）；`docs/tasks/recipe-mention.md` §2.3；Agno/Mastra 对照（2026-08-02）
> 用户裁决（2026-08-02）：① remix 后改提示词参数必须生效（recipe 参数默认值化）；② agent 升级项与 recipe 语义并成**一期迭代**；③ **禁**针对 MiniMax 的 tool-call 特判——原生 tool-call 信道等 provider 抽象落地（多模型方向）
> 迁移：**零表迁移**——重试复用既有 `workflow_steps.attempt` 列；run 来源派生自 `messages.workflow_run_id` 反链

## 0. Context

三条问题线一次收拢：

1. **remix 改参数被踩**：dub 卡 Remix 后用户把模板文案"德语、法语和西语"改成"中文"，意图 agent 已识别 `dub_languages=["zh"]`，但 `projects.py:354` 的无条件覆盖把它踩回配方默认——"看得见的可改 + 改了不生效"。
2. **chat morph 双重缺口**：chat 追加配音是 morph（覆盖目标行，"加一版"变"换一版"）；且 morph runner 裸写 `render_spec`，绕过 ADR-032 写纪律（不可撤销、hash 断链靠 D7 自愈兜底、语义信号丢失）。
3. **Agno/Mastra 对照出的硬化项**：step 级重试座位（`SkillEntry.retries`，注释本就写着 "Mastra step-level retry seat"）未接线；提案提示词只注入参数名不注入文档；原生 tool-call 信道（本期**不实施**，见 §2.6）。

## 1. 已核实的现状事实（读码确认，2026-08-02）

- `merge_explicit_slots` 是**加性**的（以全部推断槽位为底，钉只替换同 key 项）——"@dub + 顺便写篇文章"的 article 槽位今天就能存活；recipe-mention 简报 §2.3"不与同句其他意图合并"的表述**已过时**。
- `intent.py:116`：LLM 只在用户要求配音时产出 `dub_languages`，否则空数组——**"非空 = 用户显式指定"的信号现成**，无需新字段。
- `clients/minimax.py`：`generate` / `generate_image` / `generate_music` 均已有 tenacity 3 次指数退避——step 级重试只补**非 provider** 瞬时故障（TOS 上传 / ffmpeg / 未走 client 的 voice 调用）。
- `execute_step`（orchestrator.py:555）失败即 `failed` + `_cascade_skip`；`attempt` 每次执行自增（:570）；worker 每 tick `create_task(execute_step)` 驱动——**reset pending 即重试，worker tick 即天然退避**。
- 裸写 `render_spec` 现场 4 处：`node_runners.py:1628`（remove_filler）/`:1706`（add_music）/`:1765`（translate_clip）/`:1839`（dub morph 分支）。
- `DubClipParams` 无 `fork`；mode② `_compile_task_list` 的 `spec = params.model_dump()`——**params 加字段自动流入 `spec.fork`，runner 已在读（:1795），零 runner 改动**。
- `WorkflowRun` 无 origin 列；`messages.workflow_run_id` 是 message→run 的反链（morph 派发路径的天然来源判据）。
- 编辑器端点（outputs.py）已示范正确姿势：`apply_precomputed(source="editor")` 记账；`SOURCE_REGISTRY = {editor, chat, mcp, system}` 座位齐全。

## 2. 设计论证

### 2.1 W1：recipe 合并代数三规则（remix 参数默认值化）

| 规则 | 字段 | 语义 |
|---|---|---|
| ① 承诺钉死 | `recipe.outputs` | 卡片承诺的产物类型，pin 优先（`merge_explicit_slots`） |
| ② 参数默认 | `dub_languages` | **用户点名的赢；没点名才用配方默认**（`if not intent.dub_languages: fill`） |
| ③ 额外放行 | 其他推断槽位 | 加性合并原样存活（现状，本简报追认） |

`RecipeEntry` 字段加注策略注释（outputs=PROMISE / dub_languages=DEFAULT）；第三个可调参数出现时再升格声明式结构（YAGNI，缝留名）。意图提示词硬化一行：用户要求配音但未点名语言 → 空数组（防 LLM 猜语言制造假显式信号）。recipe-mention 简报 §2.3 的"不合并"边界改写为三规则。

### 2.2 W2：提案提示词参数文档注入

`params_model` 字段补 `Field(description=...)`；`intent.py` 的 `skill_lines` 从只列参数名升级为"参数名: 描述"。provider-neutral（Pydantic 层），提案质量直接受益。范围只到 SKILL params（op 参数名自解释 + op description 已含单位说明，不动）。

### 2.3 W3：step 级瞬时重试（TransientNodeError）

- 新异常类型 `TransientNodeError`（node_runners.py）：runner 把已知瞬时调用（TOS 上传 / voice clone / TTS / ffmpeg）包成它；确定性失败（"No clips could be dubbed"）保持原样快速失败。
- `execute_step` except 分支：`isinstance(e, TransientNodeError)` 且 `attempt <= retries`（`SKILL_REGISTRY` 按 `node_kind` 反查，dub_clip / translate_clip 设 `retries=2`）→ **reset pending + error 记录，不 cascade**；worker 下一 tick 重新认领 = 退避。
- LLM HTTP 层既有 tenacity 不动（双层不叠加：client 重试单调用，step 重试整节点）。
- runner 纪律：凡 `retries>0` 的 runner 必须幂等（dub/translate morph 重写 spec + 重渲染，幂等成立；voice clone 有 meta 缓存）。

### 2.4 W4：morph 记账归拢（壳/核同账）

4 处裸写一律改 `apply_precomputed`（op 映射：dub→`set_dub`、translate→`translate_captions`、add_music→`set_music`、remove_filler→**新增 precomputed op `remove_filler`**，params 空模型）。`source` 派生：run 被 `messages.workflow_run_id` 反链 → `"chat"`，否则 `"system"`；`user_id = project.user_id`。fork 分支不动（派生新行自带 baseline 账）。收益：chat morph 可撤销、hash 链不断、校准回流吃到语义 params。

### 2.5 W5：chat dub fork 参数（"加一版"不再覆盖原版）

`DubClipParams.fork: bool = False` + 引导描述（"再来一版/加一版/另一版/要求保留原版 → true"）。mode② `spec = params.model_dump()` 自动携带；`run_dub_clip` 已在读 `spec.fork`。**零 runner 改动**。

### 2.6 W6：原生 tool-call 信道——本期不实施（设计记录）

方向：四态提案建模为 provider 的 native tools schema，信道从"约定"升"协议"。**触发条件 = provider 抽象落地**（多模型方向，用户裁决 2026-08-02）；届时 capability 探测（provider 支持 tools → 原生信道，否则 JSON 提示词兜底）。本期禁任何 MiniMax 特判。

## 3. 改动点

| 文件 | 改动 |
|---|---|
| `app/pipeline/routes/projects.py` | W1：dub_languages 覆盖 → 默认填充（3 行） |
| `app/chat/intent.py` | W1：dub_languages 硬化行；W2：skill_lines 注入参数描述 |
| `app/pipeline/recipes.py` | W1：RecipeEntry 字段策略注释 |
| `app/pipeline/registry.py` | W2：params_model 字段 `Field(description=...)`；W3：dub_clip/translate_clip `retries=2`；W5：`DubClipParams.fork` |
| `app/pipeline/orchestrator.py` | W3：execute_step 瞬时重试分支 |
| `app/pipeline/node_runners.py` | W3：`TransientNodeError`；W4：4 处裸写 → `apply_precomputed` + `_run_origin` |
| `app/operations/registry.py` | W4：新增 precomputed op `remove_filler` |
| `app/tools/dubbing.py`（及 voice/TOS 调用点） | W3：瞬时调用包 `TransientNodeError` |
| `docs/tasks/recipe-mention.md` | W1：§2.3"不合并"边界 → 合并代数三规则 |
| `docs/PROGRESS.md` | 本期迭代入需求池/本周行 |

## 4. 命名审计

- `TransientNodeError`（瞬时节点错误）/ `fork`（派生分叉，沿用 spec.fork 既有词）/ op `remove_filler`（与 skill 同名同义，跨注册表对齐 NAMING §1）——入 NAMING §2 词汇表。
- 无新表、无新包、无黑名单后缀；"能力层/适配层"沿用 ADR-033 词汇。

## 5. 验收（e2e 真实链路，无测试套件纪律）

| # | 场景 | 期望 |
|---|---|---|
| 1 | dub 卡 Remix 原文发送 | clips + de/fr/es 三 fork（回归不变） |
| 2 | Remix 改"中文"发送 | 面板 clips + zh → run 出 1 个 zh fork |
| 3 | @dub + "顺便写篇文章" | 面板 clips + article + 3 dub（规则③） |
| 4 | 留 chip 删掉语言描述 | 默认 de/fr/es 兜底（规则②） |
| 5 | chat "再来一版中文配音" | fork 派生新行，原版保留；operations 账有 `set_dub(source=chat)`；undo 可回滚 |
| 6 | chat morph（"把这条配成中文"） | 覆盖目标行 + 账 + undo 可回滚 |
| 7 | 注入瞬时故障（voice/TOS 调用打点） | step 自动重试成功，`attempt=2`，error 记录 transient 字样，下游不 cascade |
| 8 | 多配方 / reserved 卡 | 422 矩阵回归不变 |

## 6. Prohibited Behaviors

1. **禁**针对 MiniMax 的 tool-call 特判（W6 触发条件 = provider 抽象落地）。
2. **禁** LLM 解释 recipe 提及；**禁**单 run 多配方（不变）。
3. **禁** morph runner 裸写 `render_spec`——一律 `apply_precomputed`（ADR-032 写纪律补齐）。
4. **禁**新表/新列（origin 反链派生；重试复用 attempt）。
5. **禁**拓扑变更——fork 走既有 `spec.fork` 通道，不动 `compile_graph`。
6. **禁**确定性失败重试——只有 `TransientNodeError` 进重试分支；"No clips to dub" 类必须快速失败。
