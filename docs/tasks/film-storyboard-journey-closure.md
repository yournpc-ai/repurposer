# Film 分镜旅程闭环（两批次）

> Status: Batch 1（§3 主链路）已落码待验证——compileall / pytest / check_gates / prompt_gate / tsc / 剧本矩阵尚未复跑；Batch 2（§4 质量收紧）已落码待验证——两条红线修复（grounding 近邻 cutoff 0.5 / 旁白 cue 句读切分含拉丁句号）+ CJK 语音单位（旁白容量/字幕 cue 权重）+ 三质量闸（REPEATED_VIEW / EMPTY_CHAPTER / PADDING_SCENE，_MIN_VIEWS 抬至 4）+ markdown 富形态（pages 参数）+ render probe 音频流检查与输出 payload provenance + 能力文案收紧，仪式链同样用户自跑。本文是两批实施合同，不把目标态写成 current code。
> 决策座位 = ADR-129 / ADR-130；chat 行为现行正文 = `CHAT_ARCHITECTURE.md`；渲染字段现行正文 = `RENDERING.md`。本文只写本次待做差异、批次边界与验收。

## 1. 正常路径与修订语义

以下描述**首次制作的正常路径**，不限定对话轮数，也不是固定脚本。用户可以随时提问、修改方向、反复修改分镜或暂停；系统根据当前产物、用户意图与授权决定下一步，不按固定拍数推进。

1. 用户问能力时，普通 `answer` 回答；能力文案来自统一工具注册表，不承诺真人实拍、剧情拍摄或任意运镜。
2. 用户提供网址后，助手先说明将读取网页，再通过 `get_web_page` 打开真实「读取网页」活动；完成后呈现真实 `Worked for …`。
3. 读完网站后，助手说明网站是什么、包含什么，推荐一个方向，并询问是否按该方向设计。此回合不起草分镜、不 dock 方案、不建 run。后台采集可以继续，但不得说成视频制作。
4. 方向可以反复讨论。只有用户明确同意设计、明确委托或直接要求设计分镜时，才进入设计；auto 档不能跳过这个判断。
5. 设计分镜时，界面顺序为 Thinking → 分镜设计活动 → 真实耗时落定 → 完整分镜消息 → 模型后续回复。采集未排干时先诚实等待采集，再切到分镜设计。
6. 首稿（含修订重稿）默认 review hold ON——用户没见过的稿永不开工，呈现即停，只有用户明确要求制作才解除（ADR-134）；同一稿再呈现不重新挂 hold。其余确认行为由全局 ask/auto/credit 规则决定。
7. 只有 start gate 与 `create_run` 都成功后才说开工；只有渲染与文件校验完成后才交付。交付文案必须匹配真实产物，旁白未生成就不得声称有旁白，部分失败必须说成部分失败。

修订规则：

- **分镜可以反复修改**：「第二幕改成……」这类明确修改请求本身就是对应修改的授权，不需要重新问「要不要设计分镜」。
- **解释问题不等于修改**：「为什么这样安排？」只解释当前稿，不重起草、不启动生产。
- **每次修改基于当前稿和反馈**：保留用户未要求改变的内容，产生新版本；不能把支持修订实现成每次从头随机生成一份。
- **制作中修改**：已启动的 run 保持出生时的快照并继续或失败于自身状态；新修改生成后续版本，是否再生产走全局授权流程，不能改写正在执行的版本。
- **交付后修改**：同样基于已交付版本生成后续版本；旧版本与其授权、run、渲染证据保持可追溯。
- 产品层没有「最多修订几轮」。单次工具循环的 `max_iterations` 只是单回合执行预算，不能变成整段对话的修订次数限制。

## 2. 当前测试红线归类

开工前先复跑聚焦测试，红线若已变化以 current HEAD 为准。当前两条失败归类如下：

1. `tests/test_film_storyboard_pure.py::test_grounding_rejection_carries_nearest_manifest_lines`
   - **归类**：实现 bug。当前近似候选提示阈值过宽，给无近邻文本也返回候选噪音。
   - **处置**：Batch 2 修实现，不放松断言。
2. `tests/test_film_storyboard_pure.py::test_build_spec_projects_narration_audio_and_caption_cues`
   - **归类**：实现缺口。ADR-130 要求旁白 cue 按句读/从句切分，当前实现仍把整段压成一个 cue。
   - **处置**：Batch 2 修实现，不放松断言。

## 3. Batch 1 — 可验证主链路

### 3.1 范围

- 保持方向确认独立：URL 回合只读网页并给方向问题；只有明确设计授权才起草。
- `design_storyboard` 改非终态：checkpoint 先说设计方向；execute 起草、发布分镜并返回 `ToolObservation`；模型随后 `answer` 或进入方案工具。
- 活动顺序：capture wait / storyboard design 标签真实区分；设计活动先落定真实耗时，再发布分镜消息，再回复。
- `PendingPlan` 增加读容忍的版本化分镜状态与执行快照：版本、参数、内容 digest、页面/音乐/时序输入、设计授权消息、呈现消息、review hold、draft token。旧字段读容忍升级，无 SQL migration。
- 方案 dock 全座位只读当前版本并重写 `launch_film` 参数；`specific_instruction` 非空也绝不触发 dock 期重起草。
- 新 draft 开始即让旧 film 确认失效；不删无关任务、素材、消息、图节点或 run 历史。
- review hold 跨回合持续，只有明确制作请求解除；分镜已展示但无方案时，「按这版开始」先补方案，再接全局授权。
- ask / auto / typed chat / Start 钮共用 `answer_question`；auto 记录设置快照；Start 钮改 typed answer transport。
- start gate 校验 active draft、review hold、版本、content/execution digest、任务参数。
- `LaunchFilm.run` 严格消费出生时的分镜与执行快照；漂移即失败并请求重新设计，不静默重编排。
- reveal 黑场使用真实 beat interval；renderer 删除把 `fps * 0.5` 当一拍的硬编码。音乐缺节奏信息时先复用现有分析/补齐路径，仍无法获得才失败。
- Start 钮 transport 改动必须带一条非 film 回归，证明普通工具确认不受影响。

### 3.2 明确不做

- 不做重复网页镜头、空章节、padding 场景的新质量判定。
- 不做旁白/字幕策略的广泛重构。
- 不新增确认偏好控件、审批端点、聊天 loop、工作流系统。
- 不把分镜专属批准字段作为 auto 档永久闸门。

### 3.3 验收

至少拿到：

- ask 档真实对话：URL → 方向问题 → 同意设计 → 分镜 → dock → typed/Start 确认 → run → 可播放成片。
- auto 档真实对话：方向确认不跳过；分镜呈现后按全局规则继续。
- 「只看分镜」→ 后续无关问答不解除 hold → 明确「按这版开始」→ 补方案并开工。
- 分镜修改基于当前稿产生新版本，未要求改变的内容保留，旧 Start 失效，新 Start 只启动新版本。
- 分镜超时/模型失败：活动与 draft marker 都诚实收束，无永久等待。
- 一条真实可播放成片，且呈现稿 digest = run context digest = render spec digest。
- Start 钮 typed answer 的 film 与非 film 回归各一条。

## 4. Batch 2 — 质量收紧

### 4.1 范围

- 修两条已归类测试红线：grounding 近邻提示阈值；旁白 cue 按句读/从句切分。
- 字幕策略：CJK-aware 切分；设计期优先在既定窗口内放下旁白；放不下则设计期打回并产生新版本。worker/render 期发现不再适配时明确失败或请求修改，永不偷偷重写已批准分镜。
- 重复网页镜头、空章节、padding 场景校验。
- 分镜 markdown 可读性收紧：场景行必须说明章节/页面、用户看到什么、相机/文字动作、来源、时长/帧/拍、旁白；禁止只剩 `ui / shot 0 / camera 2s`。
- 来源展示区分页面/章节，避免重复域名充当来源。
- validator / skill / prompt / markdown 的时长与场景边界同步为同一法；保留代码现行 70–118s，不引入硬编码「14 幕」要求。
- render probe 在既有视频形状校验外补音频存在性与分镜/执行 digest provenance。
- capability / SKILL 文案只承诺真实 renderer 能力：motion text、brand hero、网页截图相机、章节卡、数字证据卡、reveal/end card、音乐、旁白、字幕。

### 4.2 明确不做

- 不把新质量规则提前塞进 Batch 1 阻塞主链路。
- 不开放自由字幕版式；仍受 clip-spec / renderer 可表达能力约束。
- 不为追求通过率放松既有断言。

## 5. 禁止事项

1. 禁新增第二意图入口、第二聊天 loop、独立审批端点或工作流系统。
2. 禁把「后续有用户消息」当作设计或生产授权。
3. 禁伪造用户批准消息；auto 的授权来源只能是设置快照。
4. 禁在 dock / start / worker 阶段重起草分镜；真实修改只能走 `design_storyboard` 并基于当前稿产生新版本。
5. 禁删除无关任务、素材、消息、图节点或 run 历史来让旧 film 计划失效。
6. 禁把 capture wait、分镜设计、生产、渲染统一藏在泛化标签下。
7. 禁假计时阶段；一切 `Worked for …` 必须来自真实活动跨度。
8. 禁把代码生成的长 markdown 当散文逐字打字；散文走打字机，代码拼装内容原子落地。
9. 禁在 render/worker 期因旁白、镜头或页面漂移而悄悄换稿。
10. 禁让「只看分镜」hold 因新回合、刷新或无关问答自动解除。
11. 禁为放行回归调低 prompt gate、剧本或纯测试断言。
12. 禁把文档写成事件史；docs 只写现行法，任务简谱写施工合同。

## 6. 关键文件

- `apps/api/app/models/schemas.py`
- `apps/api/app/tools/film/storyboard.py`
- `apps/api/app/tools/film/narration.py`
- `apps/api/app/chat/turn_tools.py`
- `apps/api/app/chat/plan_turn.py`
- `apps/api/app/chat/propose_turn.py`
- `apps/api/app/chat/service.py`
- `apps/api/app/pipeline/lifecycle.py`
- `apps/api/app/pipeline/scope_compile.py`
- `apps/api/app/pipeline/errors.py`
- `apps/api/app/pipeline/render_probe.py`
- `apps/api/app/prompts/chat/_website_film.j2`
- `apps/api/app/skills/launch-film/SKILL.md`
- `apps/render/src/film/schema.ts`
- `apps/render/src/film/components.tsx`
- `apps/web/src/components/chat/ChatDock.tsx`
- `apps/web/src/components/chat/historyReplay.ts`
- `apps/web/src/lib/chat-stream.ts`
- `apps/api/tests/test_film_*_pure.py` / `test_lifecycle_pure.py` / `test_chat_args_pure.py`
- `apps/api/scripts/chat_scenarios.py`

## 7. 验证仪式链

按仓库纪律，验证由用户自跑；施工会话负责代码层分析、修复与报告「未跑验证」。

建议顺序：

```bash
cd apps/api && uv run --extra dev python -m pytest tests/test_film_storyboard_pure.py tests/test_film_dock_storyboard_pure.py tests/test_lifecycle_pure.py tests/test_chat_args_pure.py -q
cd apps/api && uv run --extra dev python -m pytest tests/ -q
cd apps/api && uv run python scripts/check_gates.py
cd apps/api && uv run python scripts/prompt_gate.py   # 触及 prompt 面时
cd apps/web && npm test
cd apps/api && uv run python scripts/chat_scenarios.py
```

真实验收必须附：完整对话、设计授权消息 id、版本、参数、指纹、content/execution digest、呈现消息 id、生产授权来源、dock quote、run id、`confirmed_scope`、worker `prepared_storyboard_used` 日志、render spec provenance 与可播放成片链接。
