# Chat Architecture — Agent Interface 层

> Status: ✅ v1 backend 已实现（2026-07-26）；chat UI / 打勾流 / composer UI 归下轮
> 上游决策：ADR-028（RunPlan）/ ADR-029（plan 级 dispatch）/ ADR-030（产物统一）
> 命名遵循：`docs/NAMING.md`；模块归属：`docs/MODULE_ARCHITECTURE.md`（Agent Interface：conversations/messages）
> 前置重构：`docs/tasks/backend-module-restructure.md`（chat/ 包是本文的代码家）
> 实施简报：`docs/tasks/chat-loop-v1.md`
>
> v1 落地偏离点（相对本文设计稿）：
> - §5 的 `ports` 未吸收，拓扑约束用 `requires`（输入校验）+ `after`（顺序约束）表达。
> - `dub_clip` / `synthesize_talk_video` 已登记未实装（runner=None 座位，不可派发）。
> - UI 冻结：chat UI / 打勾流 / @picker 未做；mentions 仅落契约与列。
> - SSE 只接 results 页 loading（GenerationStepper 数据源从 2.5s 轮询换推送）；
>   step 状态枚举加 `waiting` 座位（HITL/suspend-resume 预留）。
> - mentions 的 type 取 `workflow_step`（本文原写 plan node——N-15 改名后全栈同名）。

## 1. 定位与三条原则

Agent Interface 是六层模块图里"意图 → 执行"的唯一入口。用户的三张脸——composer pills、composer 自由 prompt、chat 对话——在它这里汇成**一条机制**：

```
task list（LLM 提议）→ compile_graph 校验/排序/补默认（代码裁决）→ workflow_steps（施工图）
```

1. **LLM 提议，代码裁决**。LLM 只出"干什么"（task list），拓扑正确性（skill 是否存在、顺序是否合法、参数默认值）全部归 `compile_graph`。LLM 永不直接写 node spec。
2. **轮内一次调用，轮间才是循环**。每条用户消息 = intent agent 单次 tool-calling 调用 → task list → 编译 → 跑。不做 ReAct 式多步推理；"循环"只发生在对话轮次之间。
3. **composer = chat 的第一条消息**。数据模型早已如此（`/generate` 建 project-scoped ChatSession 并存 prompt）：pills 是 task list 的结构化快捷方式，自由 prompt 是 task list 的自然语言入口，无指令 = 输入组合推导默认 task list（compile_graph 模式①，现有 presence-gating）。

## 2. 一次对话指令的完整生命

```
用户: "去掉口头禅，剪 3 条高光，加个音乐"
 │
 ▼
chat/service.py ──► intent agent（LLM 单次 tool calling，带 §6 上下文）
 │                   输出 task list（提议，无执行权）:
 │                   [{skill:"remove_filler"}, {skill:"select_clips",params:{count:3}}, {skill:"add_music"}]
 ▼
pipeline/registry.py   校验：skill 已注册？参数过 schema？
pipeline/orchestrator  compile_graph 模式②：拓扑排序（配乐殿后）+ 补默认值
 ▼
workflow_steps（动态 DAG，3 步骤 + render fan-out）── worker 认领（SKIP LOCKED）
 │
 ▼ 执行中
node.spec.summary = "Removed 12 fillers · 3 repeated takes"（量化摘要，§7）
 │  经 SSE 推送（§8）
 ▼
打勾流逐行亮起 → outputs（render_status=PENDING）→ Remotion → MP4
 │
 ▼
Done · 3 clips · 12 fillers removed · 1 score ── [Open in editor]（outputs 链接）
 │
 ▼（下一轮：改现有产物而非跑新任务）
"第二条再短一点" ──► intent ──► edit ops ──► Operation Model（📋，§9 边界）
```

## 3. Task List 契约

intent agent 的轮内输出二态，JSON schema 强校验：

```jsonc
// A. 跑新任务（→ compile_graph 模式② → 新 WorkflowRun）
{
  "type": "task_list",
  "tasks": [
    { "skill": "remove_filler", "params": {} },
    { "skill": "select_clips", "params": { "count": 3 } },
    { "skill": "add_music", "params": { "mood": "calm" } }
  ],
  "summary": "去口头禅、剪 3 条高光、加舒缓配乐"   // 给用户看的一句话
}

// B. 改现有产物（→ Operation Model，v2）
{
  "type": "edit_ops",
  "target_output_id": "uuid",
  "ops": [{ "op": "trim_segment", "target": "seg_03", "params": { "end_delta": -2.0 } }],
  "summary": "把第二段结尾剪掉 2 秒"
}
```

`summary` 字段必填——它是打勾流的标题文案，也是消息记录里"这轮干了什么"的人话存档。

## 4. Skill Registry 初集

`pipeline/registry.py`：Python dict + Pydantic schema，不上框架。每条登记：

```jsonc
{
  "name": "remove_filler",
  "kind": "skill",                    // skill=LLM 决策单元 / tool=确定性执行单元
  "behavior": "deterministic",        // deterministic 可缓存 / probabilistic 每次计价
  "params_schema": { ... },           // Pydantic
  "summary_template": "Removed {filler_count} fillers · {repeat_count} repeated takes",
  "cost_hint": "cheap",               // 成本量级，供未来 quote
  "runner": "pipeline.node_runners:run_remove_filler"
}
```

**准入纪律：skill 总数十几个封顶。** 新 skill 准入 = 过 NAMING §7 同款评审（用户会用自然语言说到它吗？现有 skill 组合能表达吗？），通过即登记（§8 词汇表）。

### 4.1 已在（反向抽象登记）

| skill | 实现 | summary_template 示例 |
|---|---|---|
| `select_clips` | `skills/clip_agent.py` | "Selected {n} clips · {total_seconds}s total" |
| `write_post` / `write_quotes` / `write_carousel` / `write_article` | `skills/post·quotes·carousel·article.py` | "Wrote a LinkedIn post · {word_count} words" |
| `revise_script` | `skills/reviser.py` | "Revised hook · {reason}" |
| `dub_clip` | dub 端点 → `tools/voice.py` | "Dubbed with cloned voice" |
| `add_music` | clip-spec music 槽 + mood 库 + `tools/music.py` | "Scored · {mood} bed" |

### 4.2 新增（按价值排序，独立排期）

| skill | 状态 | 说明 |
|---|---|---|
| `synthesize_talk_video` | 📋 任务简报 `docs/tasks/synthetic-talk-video.md` | 文字稿+照片+声纹 → 合成发言视频（生成端 v1） |
| `remove_filler` | 📋 chat 线 hello world | 词级时间戳 + filler 检测 → 标 hidden（非破坏）→ 重渲染 |
| `make_hook` | 📋 半新 | ≈ `revise_script(scope=hook)` 的独立入口 |

### 4.3 不登记

- **管线内部节点**：`preprocess` / `persona_bootstrap` / `director_plan`——拓扑的组成部分，不是用户可选技能。
- **`infer_intent`**：它是 loop 的入口，不是 loop 可调用的一项。
- **edit ops**：Operation Model 的词汇（§9），产出 clip-spec diff 而非 run——两个家族分开登记。
- **judge/verify**：Phase 3 节点 kind，非用户技能。
- **缓议**：`adapt_to_platform`（等 Distribution 回流数据）、`insert_broll` / `motion_graphics`（talking-head 知识内容价值低）、`avatar_gen`（v2，ADR-029 已定框架）。

## 5. compile_graph 模式②：任务列表物化

现有 `compile_graph`（模式①，presence-gating）之外新增模式②：

1. **校验**：task list 每个 skill 必须在 registry；params 过 schema；不认识的 skill → 拒收并让 intent 修复一次（retry 1 次），仍败 → 回复用户"这个我还不会"。
2. **拓扑排序**：registry 声明 `ports`（in/out 类型）与 `after` 约束（如 `add_music` 必须在渲染相关节点之后）；编译期校验类型边。
3. **补默认值**：`select_clips.count` 缺省 = 项目默认 / brand 默认 music 等，全部由代码补，不信 LLM 的缺省判断。
4. **落图**：产物是标准 `workflow_steps`——之后走图、认领、计量、打勾流与模式①完全同构。**动态化只发生在编译前，编译后零差异。**

## 6. 对话上下文（context 组装）

确定性代码组装，不是塞聊天历史。每轮 intent 调用带四部分：

| 部分 | 内容 | 来源 | 预算 |
|---|---|---|---|
| 项目摘要 | 素材清单、当前 outputs 列表（type + 一句话）、run 状态 | DB 确定性生成 | 4k |
| 最近操作 | 近 3 轮的 task list / edit ops 及结果摘要 | messages | 2k |
| mention 清单 | 本会话可 @ 实体（§7） | DB | 1k |
| 早期摘要 | 超窗对话压缩 | LLM 异步生成存 messages | 2k |

## 7. Mentions（@ 实体引用）

多轮对话的模糊指代必须落为确定引用。可 @ 实体四类：**asset / output（某条 clip）/ transcript 段落 / workflow step**。

- 前端输入框 @ 触发选择器，`messages.mentions` JSONB 存 `[{type, id, label}]`；
- intent 收到的 prompt 中 mention 已替换为确定 ID 引用，LLM 解析歧义降一个量级；
- "把第二段高光换掉"无 mention 时，intent 可反问澄清——**反问是合法输出，不是失败**。

## 8. 进度推送：SSE = 推送优化的读

**定位：SSE 是 DB 状态的推送管道，不是事件总线。** 事实源唯一 = `workflow_steps` 表，因此无事件存储、无投递保证、无重放——断线重连 = 重读当前节点状态，天然幂等。

```
GET /api/v1/runs/{id}/events   （chat/routes.py 或 pipeline/routes/）
  async generator：run 非终态期间每 1s tail workflow_steps
  → 有变化才推：event: step.updated / run.updated
  → 15s 心跳防空闲断连
  → run 终态推完最后一帧即关流
```

- **该 SSE 的**：results 页 run 进度、chat 打勾流（用户正盯着一个活 run）。
- **该普通 GET 的**：library / projects 列表等一切非实时读——不为一棵树买一片森林。
- **前端用 fetch-event-source**：原生 EventSource 不能带 Authorization header，这是实际坑。
- **LISTEN/NOTIFY 后置**：内部 1s tail 在单 worker 规模足够；多实例部署再换 PG 通知桥，**客户端契约不变**。

**量化摘要**：`node.spec.summary` 由 runner 按 registry 的 `summary_template` 填充（模板填数字，不是 LLM 润色），随 step.updated 推送——这是打勾流"Removed 12 fillers · 3 repeated takes"的数据来源。run 收尾聚合节点摘要成 "Done · 3 clips · 12 fillers removed"。

## 9. Edit Ops 边界（v2，归 Operation Model）

chat 的另一半是"改现有产物"。边界判定：

- 指令能表达为对某个 output 的 clip-spec diff → **edit ops** → Operation Model（operations 表，📋 ROADMAP §2）；
- 指令需要新的生成 → **task list** → 新 run（本文机制）；
- 拿不准 → intent 反问。

edit ops 初集（Operation Model 动工时评审定稿）：`trim_segment` / `remove_segment` / `reorder_segment` / `set_node_params` / `swap_slot` / `apply_preset` / `regenerate_node` / `restore_version`。本文不定稿，只钉边界。

## 10. 失败语义

- 单节点失败：打 ✗ + 对话内给替代方案（"曲库没有合适的，要上传还是换个风格？"），对话继续，不阻塞。
- skill 拒收（§5.1 修复失败）：回复"这个我还不会"+ 列出相近可用 skill。
- run 全败：沿用 RunPlan 收尾口径，对话里给出失败原因与重试入口。

## 11. 分期

| 期 | 内容 | 依赖 |
|---|---|---|
| v1 | registry 初集（§4.1）+ compile_graph 模式② + intent tool-calling + SSE + 量化摘要 + `remove_filler` 实装（全链路 hello world） | backend-module-restructure |
| v2 | mentions + edit ops（Operation Model 联动）+ `make_hook` | Operation Model 📋 |
| v3 | 成本 quote（probabilistic skill 执行前报价确认）+ context 异步摘要 | metering 扩展 |

## 12. Prohibited Behaviors

- **禁止** ReAct 式多步推理 loop——轮内单次 tool calling。
- **禁止** LLM 直接写 node spec / 自由生成执行代码——一切经 registry + compile_graph。
- **禁止**引入 agent 框架（Agno / LangGraph 等）。
- **禁止**把 SSE 做成事件总线（事件存储 / 投递保证 / 重放）。
- **禁止** chat 绕开 `orchestrator.create_run` 自建 run（零旁路原则不变）。
- **禁止** registry 无评审膨胀——skill 准入必须过 NAMING §7/§8。
