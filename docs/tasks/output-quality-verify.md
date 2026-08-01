# output-quality-verify 实施简报——生成产物质量：保真止血 + 打分维度 + 质检节点首期

> Status: 📋 待实施（2026-07-28 评审定范围：方案 A——保真 + 质检节点，视觉产物品牌渲染归下一轮）
> 依据：PROGRESS 需求池"首发推荐分：维度明细"（P1 ❌）与"质检节点"（P2 ❌，本轮提前兑现——单产物质检首期）；AGENT_ARCH §12.3（质检节点形态）/§12.6（Phase 3）；STRATEGY §2.1（品味可见可证伪）/§2.5（L2 质量控制缺口）
> 前置：工作区在飞的 speakers/pending-intent/stepper 改版（GenerationStepper 删除、GenerationOverlay 重写）先落地；本简报的 UI 接线点以落地后的通用 steps 渲染（`workflow_step_to_response` + stepKinds i18n）为准
> 迁移：新增 1 个 alembic 迁移（`outputs.quality` JSONB）；down_revision 跟在飞两个迁移（asset_title / pending_intent）落地后的 head

## 0. Context

原 ROADMAP P0 表已清空（ROADMAP 已并入 PROGRESS，2026-07-31），STRATEGY §2.5 控制深度阶梯的剩余缺口全在 L2（打分门槛 / persona 保真 / 术语表 / 运镜枚举）。本轮兑现 L2 的"质量"半边：先修三个保真缺陷（产物与素材货不对板），再把打分维度落库（可证伪前提），最后在 DAG 上长出 verify 节点承接这一切（质检 = 图里一种 kind，不是外挂流程）。

读码核实的三个保真缺陷：

1. **选段窗口截断**：`clip_agent.j2:179` 只喂 `source_words[:400]`（约前 3 分钟词），却要求 LLM 从全场选段并"照抄精确时间戳"。后果二选一：clips 扎堆开场，或时间戳幻觉——`locate_span` 对数值时间戳静默 snap（`clip_spec.py:76-93`），渲染出的片段与 hook/title 描述的时刻对不上，用户看到"标题讲 A、画面放 B"。
2. **金句可改编却带实名**：`quotes.j2:28` 允许 "using or adapting" 候选金句，产物带 speaker 姓名+场合署名。对学术演讲者 ICP，捏造语录是信任事故。逐字校验用代码做（fuzzy match against transcript）零 LLM 成本。
3. **打分自评且无维度**：`recommendation_score` 由生成 clips 的同一次调用自产自销；prompt 已有四维口径（completeness/opening/representativeness/delivery）但 schema 只存 `{value, reason}`（`node_runners.py:985`），不可证伪。

## 1. 已核实的现状事实（读码确认）

- 打回可走图机原生实现：`claim_ready_node`（`jobs.py:57`）的 ready 语义 = `pending` + 全部 inputs `done`；`execute_step`（`orchestrator.py:374`）逐节点执行，`node.attempt` 每次认领自增。verify 把上游 executor 重置为 pending + 自己回 pending，即被自动重认领，无需改走图机主循环。
- 失败级联：executor 重跑若真失败 → `_cascade_skip` 把 pending 的 verify 标 skipped，run 语义不变（`orchestrator.py:429`）。
- run 收尾：`maybe_finalize_run` 只数非 render 活跃节点；verify 非 render、不在 `GENERATION_NODE_KINDS`（registry `produces_outputs=True` 推导），不打乱"全败才败"的 tally。
- executor 幂等重跑已存在：`run_derivative_gen` 删同类型旧产物（`node_runners.py:1104`）；`run_clips_pipeline` 删旧 clips + 跳过其 pending render 节点（`node_runners.py:899-917`）。打回重跑复用此语义。
- verify 终端无下游：cascade/finalize 均无额外影响；metering 经 `bind_workflow_step` 按次落到各自行——executor 重跑成本落在 executor 节点，诚实。
- 前端 steps 通用渲染：`workflow_step_to_response`（`pipeline/outputs.py:43`）吐 kind/status/summary，前端按 `stepKinds.<kind>` i18n 取标签——新 kind 只需补 i18n，无契约变更。
- `Output.score` 是 JSONB（`tables.py:280`），加 `axes` 键无迁移；旧行无 axes，UI 须容忍。
- `Output` 无质量裁决列——新增 `quality` JSONB nullable（NULL = 未质检：旧行 / verify 之前的 run）。
- 无 langdetect 类依赖（pyproject 全量 21 项）；语言检查用自写微检测器（CJK 字符 + 六种产品语言 en/zh/de/fr/es/it 停用词频率），零新依赖；非产品语言 → 检查 skipped 不判决。
- `source_words` 仅来自 render_source（`node_runners.py:860`）；`asset_texts` 是全量转写文本（150k 字符截窗，`skills/base.py:20`）。

## 2. 设计论证（评审沉淀区）

### 2.1 期 1：保真止血

**锚点转写（anchored transcript）替代 400 词 JSON。** 新纯函数 `app/tools/transcript.py::build_anchored_transcript(words)`：把全量词按线索化（句末标点 `.?!。！？;；` / 词间停顿 > 0.8s / 单行 ≥ 25 词 三先触发）分组，输出紧凑行：

```
[12.3-18.7] And that is why the pricing model had to change
[19.0-26.4] We tested it with three hundred teams across Europe
```

- 全量覆盖，硬上限 12,000 词（≈90 分钟演讲），超限截断且**末行必须显式标注** `[truncated: timeline beyond 90min not shown]`——不留静默窗口。
- token 反而更省：旧 JSON 每词 ≈15 token（`{"word":…,"start":…,"end":…}`），新格式每词 ≈1.3 token + 行锚。
- clip_agent.j2 的 `## Source Word-Level Timestamps` 整节替换为 `## Timestamped Transcript`；指令改为"时间戳从行锚照抄（粗粒度即可，代码会 snap 到词边界）"。`locate_span` 数值 snap 路径不动——输入从幻觉变成有据。
- **`source_text` 语义修正**：它是定位锚 + 保真基准，必须**源语言逐字**（现行 prompt 要求它用 target_language，既自相矛盾又让跨语言时保真校验失去基准）。Output Language 节加豁免：`source_text` / `start_marker` / `end_marker` 保持源语言逐字，其余 copy 一律 target_language。

**保真度纯函数**（`app/pipeline/quality.py`，零 LLM）：

| 函数 | 逻辑 | 阈值 |
|---|---|---|
| `span_fidelity(source_text, span_words)` | token F1（源文本 vs 时间窗内词流） | ≥ 0.5 pass |
| `quote_verbatim(quote, source_texts)` | 归一化后 difflib 最佳句窗比对 | ratio ≥ 0.85 pass；语言不符 → skipped |
| `language_match(text, target)` | CJK 字符比 + 六语言停用词频率 | 最高分 == target pass；非产品语言 → skipped |
| `avoid_words(text, speaker)` | 子串命中（CJK/英文统一归一化） | 0 命中 pass |
| `length_in_bounds(text, kind)` | post 100–500 词 / article 400–1600 词 | 界内 pass |
| `slide_count` / `count_match` | carousel slides 数 == slot count（±0）；quotes 数 == slot count | 相等 pass |

**prompt 修正（顺手）**：`post.j2` "500–1500 English words" → 150–350 词（LinkedIn 长文有效区间；中文 300–800 字不动）；`quotes.j2` 删 "or adapting"、长度改 "≤ 25 词或 ≤ 80 CJK 字符"、同语言必须逐字；`director_understand.j2` 加下限（5–12 论点、6–12 金句，防下游断粮）。

### 2.2 期 2：打分维度明细

- schema：`ScoreAxes(BaseModel)` = `{completeness, opening, representativeness, delivery}`（各 1–100，四轴名沿用 prompt 现有口径）；`ClipPlan.score_axes: ScoreAxes | None`。
- 落库：`Output.score = {value, reason, axes}`；reviser 不动（修订不改选段内容，沿用旧 axes 诚实）。
- prompt：clip_agent.j2 的 Recommendation Score 节要求逐轴打分 + overall + reason（reason 仍一句、点名驱动轴）。
- UI：ClipDetailModal 增四轴条（值 + 轴名 i18n：`scoreAxes.completeness/opening/representativeness/delivery` en/zh）；ClipCard 徽章不动；旧行无 axes 时详情只显示总分。

### 2.3 期 3：verify 质检节点首期

**拓扑（compile_graph）**：每个 generation executor 后追加一个 verify——

```
full:     … → clips_pipeline(10) → verify(20, spec.for=clips)
          … → post_gen(11)       → verify(21, spec.for=post)   …以此类推
targeted: [understand → plan → X_gen → verify]
mode②:   generation skill 节点后各挂 verify；modifier（remove_filler/add_music/
          translate/dub/script）与 scope hook/clip/render 不挂
```

- kind 统一 `verify`（AGENT_ARCH §12.3 预定词汇："verify = plan_nodes 一种 kind"），`spec.for` 区分产物类型。**不进 SKILL_REGISTRY**（非 LLM 可提议 skill，内部节点同 preprocess/director）；summary 用 `_set_summary` 直写。
- STEP_RUNNERS 注册 `run_verify`。

**run_verify 逻辑**（纯确定性，零 LLM 调用）：

1. 上游 executor 节点 = `node.inputs[0]` → 其 `output_refs` → Output 行。
2. 装检查上下文：source texts（`collect_asset_texts`）、render_source 词表、speaker（avoid_words）、任务书（target_language / slot count）。
3. 按 `spec.for` 跑 §2.1 检查表：clips 逐 clip 查 span_fidelity/duration_bounds/score_axes_present；quotes 逐条查 verbatim/attribution_present/count_match；post/article 查 language_match/avoid_words/length_in_bounds；carousel 查 language_match/slide_count/avoid_words。
4. 裁决写 `Output.quality = {status, checks: [{id, ok|null, detail}], attempt, checked_at}`：
   - 全过（skipped 不算败）→ `status="passed"`，节点 done，summary="Passed {n}/{n} checks"。
   - 有败且 `node.attempt < 3` → raise `QualityBounce(feedback)`。
   - 有败且 attempt 用尽 → `status="needs_human"`，节点 done，summary="Needs human · {f} checks failing"（**不阻塞**）。

**打回（QualityBounce）**：`orchestrator.execute_step` 在通用 except 之前捕获——

- 上游 executor：`status="pending"`，`spec = {**spec, "feedback": feedback}`（新 dict 赋值，SQLAlchemy 可检）；error 清空。
- verify 自身：`status="pending"`（attempt 随认领续增，打回预算 = attempt ≤ 2，即 executor 最多跑 3 次：初跑 + 2 打回，`§12.3 "打回 ≤2 次"`）。
- 不标 failed、不 cascade、run 保持打开（`maybe_finalize_run` 见 pending 不收尾）。
- feedback 结构：`{failed: [{check, detail, excerpt}], round: n}`——executor runner 启动时读出并**从 spec 弹出**（防后续定向重生成吃到陈 feedback），传入 agent；五个 executor j2 增 `{% if feedback %}## Revision Required` 节（列失败项 + 证据摘录 + "只修这些，其余保持一致"）。
- executor 重跑真失败 → 走原 failed + cascade（verify skipped），run 语义不变。

**UI**：

- i18n：`stepKinds.verify` = "Checking quality…" / "质检中…"（en/zh）。
- 产物卡：`output.quality.status === "needs_human"` 时显 Badge（`rounded-md`，i18n `results.qualityNeedsReview`），Tooltip 列失败检查项；`passed` 静默不显（成功安静，同 toast 纪律）。
- 前端 `Output` 类型加 `quality` 字段（`pipeline/outputs.py` 响应带出）。

### 2.4 明确不做（本期）

- 全片质检（跨产物撞车）——coverage 维持"报告不是门禁"（§12.2 纪律）。
- LLM judge（persona 保真、质量打分）——首期零 LLM 质检；judge 可靠性需单独评审。
- 视觉产物品牌渲染（quote card 弃 image-01 烘文字 / carousel PDF）——下一轮，单独技术路线。
- storyboard/coverage 门禁化、modifier 节点的质检、reviser 的 axes。
- 术语表（PROGRESS 可选需求，独立线）。

### 2.5 评审附项（2026-07-28 二轮评审纳入）

**响度归一（归期 1）**。现状：渲染全链路无响度处理（`apps/render/src/render.ts` 无 loudnorm/volume/gain），安静源视频 → 安静 clip，-18dB 配乐雪上加霜。方案：render 服务产 MP4 后加 ffmpeg `loudnorm` 后处理（`I=-16, TP=-1.5, LRA=11`，视频流 copy 只重编码音频）——双向归一，配乐混音有基准。**零 clip-spec 变更、零 Python 变更**，黑盒内部消化（ADR-016 纪律不破）。

**下载格式（归期 2）**。现状：article/carousel 前端拼 Blob 直吐 `.md`。方案：下载变小菜单 `.md` / `.txt`（剥 Markdown 语法）/ 复制到剪贴板（粘进 LinkedIn/newsletter 才是主路径）；post 一并拉齐。`.docx` 引依赖，本轮不做。

**产物数量意图 wiring（归期 1）**。现状：InferredIntent 只有 `clip_count` 一个计数（`intent.py:78`），quotes/carousel 数量由 director_plan 拍默认（3/6）。方案：`InferredIntent` 加 `quotes_count`/`carousel_count`（沿用 `clip_count` 先例，可选整数），任务书透传 → director_plan prompt 优先用显式 count。"给我 8 张金句卡"生效。**注意**：张张出图不做——现在仅 `quotes[0]` 出 AI 图（`node_runners.py:1127`），为 N 张堆 image-01 又贵又将在下轮品牌渲染后全废；N 张卡的零边际成本兑现归下轮。与在飞的 intent/schemas 改动对账后实施。

**carousel 视觉叙事（确认归下一轮）**。用户评审原话："carousel 为什么不是连环叙事而是一堆文字"——当前产物 = slides JSON 文字块 + `.md` 下载，不可交付（LinkedIn 轮播的真实交付物 = 品牌 PDF/PNG 套图）。确认为下一轮（方案 B）主体，与金句卡确定性渲染同棒。

## 3. 后端改动点

1. `app/tools/transcript.py`（新）：`build_anchored_transcript(words, max_words=12000)` 纯函数。
2. `app/pipeline/quality.py`（新）：§2.1 六个纯函数 + `run_checks(for_type, outputs, ctx) -> verdict`。
3. `app/models/schemas.py`：`ScoreAxes`；`ClipPlan.score_axes`；`OutputResponse` 加 `quality`；`InferredIntent` 加 `quotes_count`/`carousel_count`。
4. `app/models/tables.py`：`Output.quality = Column(JSONB, nullable=True)` + alembic 迁移。
5. `app/prompts/clip_agent.j2`：词表节换锚点转写；source_text 源语言豁免；score 节加逐轴；feedback 节。
6. `app/prompts/post.j2/quotes.j2/carousel.j2/article.j2`：长度/逐字修正 + feedback 节。
7. `app/prompts/director_understand.j2`：论点/金句下限。
8. `app/prompts/director_plan.j2`：count 规则改"显式 count 优先，缺省 quotes=3 / carousel=6 / clips=任务书"。
9. `app/skills/*`：五个 executor `generate(...)` 签名加 `feedback: dict | None`；clip_agent 传 anchored transcript（`source_words` 参数语义换builder 输出）。
10. `app/pipeline/node_runners.py`：`run_verify` 注册；clips_pipeline 用 `build_anchored_transcript`；executor runners 读弹 `spec.feedback`；`run_director_plan` 任务书带显式 counts。
11. `app/pipeline/orchestrator.py`：`QualityBounce` 异常 + execute_step 捕获分支；`compile_graph` 三种拓扑挂 verify（mode② 同）。
12. `app/pipeline/outputs.py`：Output 响应带 `quality`。
13. `apps/render/src/render.ts`：renderMedia 后接 loudnorm 后处理（ffmpeg 子进程，音频-only 重编码）。
14. `app/chat/intent.py`：ComposerIntentAgent prompt/schema 识别 per-type count（"8 张金句卡""5 页轮播"）。

## 4. 前端改动点

1. `types.ts`：`Output.quality`。
2. 五个产物卡：needs_human Badge + Tooltip（共享小组件 `QualityBadge.tsx`）；下载菜单 `.md`/`.txt`/复制（article/carousel/post 拉齐）。
3. `ClipDetailModal`：score axes 四条。
4. i18n en/zh：`stepKinds.verify`、`results.qualityNeedsReview`、`scoreAxes.*`、检查项人话标签 `qualityChecks.*`（9 个 id）、下载菜单项。

## 5. 命名审计（NAMING §5 触发）

新名词：`verify`（kind）、`QualityBounce`（打回）、`Output.quality`（裁决：`passed`/`needs_human`）、anchored transcript（锚点转写）/`build_anchored_transcript`、score axes（四轴名沿用 prompt 现有口径，不算新词）、9 个 quality check id。无退役词。判例（拟 N-18）：质检 = 图内 verify 节点，只判不改（修内容归 executor）；`needs_human` 而非 `failed`——非阻塞语义入名。

## 6. 分期与验收

| 期 | 内容 | 行为变化 |
|---|---|---|
| 1 | 锚点转写 + source_text 语义 + prompt 修正 + quality.py 纯函数 | clips 覆盖全场、选段有据 |
| 2 | ScoreAxes + prompt + UI 四轴 | 打分可证伪 |
| 3 | verify 节点 + QualityBounce + feedback + migration + UI badge | DAG 有质检 |

验收（e2e 为准，CLAUDE.md 无测试套件纪律）：

1. **期 1**：45 分钟视频（>400 词）跑 clips——clip_agent prompt 含全场时间轴（无 `[:400]`）；选段落在后半场的 clip 渲染内容与 hook/title 描述一致（`span_fidelity` ≥ 0.5）；同语言 clip 的 `source_text` 可在原转写中逐字命中。
2. **期 1 quotes**：同语言 run 的金句全过 verbatim；手工捏造一句语录喂 `quote_verbatim` 返回 fail。跨语言（zh 源 → en 产物）verbatim = skipped 不判 fail。
3. **期 2**：新 clips 的 `score.axes` 四键齐；详情弹窗四轴渲染；旧行（无 axes）详情不炸。
4. **期 3 拓扑**：full run 图 = 每个 executor 后跟 verify；RunCard 显示"Checking quality…"；产物带 quality 裁决。
5. **期 3 打回**：speaker 配 avoid_words 后生成 post → post_gen attempt ≥ 2（feedback 进 prompt 日志可见）；连续失败 ≤ 2 次后产物标 needs_human、run 仍 COMPLETED、badge 显示失败项。
6. **期 3 mode②**：chat "写个 post" 的图含 verify；modifier 链（"去口头禅加音乐"）无 verify。
7. **成本**：verify 节点零 LLM 调用（`workflow_steps.cost` 为空）；打回重跑成本落 executor 节点。
8. **附项·响度**：低音量源视频渲染出的 clip 实测响度 -16 LUFS ±1；过大音量同样被压回。测量用 loudnorm 自带测量通道（`print_format=json` 的 `input_i`，同 R128 算法）——Remotion compositor 的裁剪 ffmpeg 构建无 ebur128 滤镜。
9. **附项·下载**：article/carousel/post 下载菜单三项齐（.md/.txt/复制），.txt 无 Markdown 语法残留。
10. **附项·count**：prompt "给我 8 张金句卡" → storyboard quotes 槽 count=8 → 产物 8 条；未提及时默认 3/6 不变。
11. **文档落地**：PROGRESS 需求池两行状态翻 ✅（维度明细 / 质检节点首期，全片质检标注仍 ❌）；AGENT_ARCH §12.6 Phase 3 → 🚧 首期落地；NAMING 词汇表登记 §5 新词。

## 7. 禁止行为（Prohibited Behaviors）

1. **禁** LLM 质检——首期全部确定性检查；judge-LLM 归后续评审。
2. **禁** verify 阻塞 run——needs_human 非终态失败，run 照常 COMPLETED；verify 不进 `GENERATION_NODE_KINDS`。
3. **禁**质检改数据——verify 只读产物 + 写 `quality` 裁决 + 打回，不修内容（修归 executor）。
4. **禁**跨语言判 verbatim fail（只能 skipped）；非产品六语言判 language_match fail（同）。
5. **禁**无反馈打回 / 超 2 次打回——feedback 必带 check id + 证据摘录；attempt 用尽即 needs_human。
6. **禁** `source_text` 翻译——它是定位锚 + 保真基准，源语言逐字。
7. **禁** `[:400]` 式词表截断复活；锚点转写超限必须显式截断标注。
8. **禁** verify 进 SKILL_REGISTRY / 被 LLM 任务列表提议。
9. **禁**全片质检、coverage 门禁化、modifier 质检进本期。
10. **禁** stepper/前端契约变更——只加 kind i18n + `Output.quality` + badge/四轴展示。
11. **禁** `passed` 状态弹 badge/toast——成功安静，只报异常（同 toast 纪律）。
12. **禁**为响度归一改 clip-spec 契约 / 动 Python 侧——渲染黑盒内部消化（ADR-016）。
13. **禁**本轮给每张金句堆 image-01 出图——成本贵且下轮品牌渲染后全废；N 张卡兑现归下轮。
14. **禁** docx 下载——本轮 .md/.txt/复制三件套。
