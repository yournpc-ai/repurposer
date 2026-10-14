# Film 分镜核对与参数行（E1）+ 配音/BGM（E2）+ 画幅变体（E3）

> Status: **E1 施工中**。母法 = ADR-120（短式）；拍板 = 2026-10-14 用户（A 变体：分镜表坐消息流，不进确认 dock；多轮核对全程 chat，口头「可以，就这样吧」开工）。
>
> 起源：launch-film skill 内化（MG 批 D1~D4）后与原 skill 效果的三处差距——时长（20–40s vs 75–120s）、无配音/BGM、无画幅变体；真实用户对话取证（项目 e9f60236）显示核对物（时长/文案/分镜）无处呈现。

## 1. 目标形态

贴链接做「官网介绍短片」的多轮核对旅程（全程消息流）：

```
用户贴链接 → agent 一问（用途，一词可答）→ 计划呈现（参数行）
→ 【分镜表消息块】（幕 × 形式 × 时长 × 屏上文案，逐版留痕）
→ 用户 chat 说改（时长/文案/画幅）→ 分镜表新版
→ 用户说「可以，就这样吧」→ 口头 yes 开工（confirmed_storyboard 入 run.context）
→ launch_film 吃已确认分镜直渲（跳过二次编排）
```

## 2. E1 施工切分（本批）

| # | 件 | 座位 |
|---|---|---|
| W1 | 编排环提取一座：`orchestrate_storyboard()`（agent 调用 + validator + 有界打回），node 与计划期共享 | `tools/film/storyboard.py` |
| W2 | 计划期分镜起草：`_present_plan` 检出 film 链（task.tool == launch_film）→ 起草 → 分镜表消息行落库（`intent.type="storyboard"`，candidates_log 先例）+ SSE `assistant.storyboard` 帧 | `chat/plan_turn.py` / `chat/routes.py` |
| W3 | 修订复用同一座位：re-draft 每次 dock 触发（修订回合的 echo/specific_instruction 入 assemble），version = 会话内分镜行数 + 1 | 同 W2 |
| W4 | 确认分镜入 run：`_create_run_from_tasks` 成功后 stamp `run.context.confirmed_storyboard`（最新分镜行）；`LaunchFilm.run` 防御性 validate → 通过则跳过编排直渲，失效则重编排并 log | `chat/service.py` / `tools/film/storyboard.py` |
| W5 | web 渲染：`StoryboardTable` 消息块组件（幕/形式/时长/屏上内容四列），旧版折叠 chip（PlanVersionChip 同律）；historyReplay 投影 + SSE 活体 | `components/chat/` |
| W6 | prompt 面：capability menu「介绍短片」品类措辞 + 核对引导（dock 后等用户拍，不催开工） | `tools/__init__.py` / prompts |

**计费边界**：计划期编排 = conversation 层计量不收费（B3 台账）；渲染仍走 hold→capture→release。守卫线不变——高价片恒带价问一次。

**Prohibited Behaviors**:
1. 分镜表永不进确认 dock（auto 档无确认钮，dock 不承重核对物）。
2. 禁第二条编排链——计划期起草复用 `film_storyboarder` agent + validator 一座。
3. 分镜行不锁 LLM 文案断言（剧本只锁形态）。
4. 修订禁整片重跑——E1 的修订对象是分镜草案，不是产物。
5. 画幅/配音/配乐参数行在 E2/E3 落地前永不上 UI（不卖未建能力）。

## 3. E2（配音 + BGM，后续批）

- storyboard schema 加 per-scene `narration`（配音词进分镜表核对——和屏上文案同族「要确认的言语」）
- film 链 audio 节点：T2A 逐幕合成（`tools/dub` 引擎现货）+ `tools/music` mood 选曲
- 渲染侧混音（Remotion `<Audio>` 轨；render.ts「no audio bed」翻案）；配音长度回写帧分配（先简式：配音跟随场景时长；beat 对齐挂账）
- 参数行增补：配音开关 / 配乐 mood

## 4. E3（画幅变体，后续批）

- film-spec 加 `aspect`（16:9 / 1:1 / 9:16），渲染家族 variant 构图常数（字号/留白/栅格分档）
- 采集按画幅分视口（竖屏版移动视口重采——桌面截图塞 9:16 先天别扭）
- 画幅 = 计划参数行 + chat 可改（修订道换画幅重渲）
- demo 货架填架：横屏 ×2 / 方形 ×1 / 竖屏 ×2（每片 = 全链真跑，产出入 demo/ 内容寻址树）

## 5. 验收

- E1：贴链接 → 分镜表呈现 → 两轮修订（时长压缩 + 文案替换）→ 口头 yes → run 直渲（`confirmed_storyboard_source=confirmed` 日志）→ 产物 probe 闸过；刷新回放分镜表各版在流。
- 仪式链：pytest + check_gates + prompt_gate（W6 触 prompt 面）+ S11 复跑 + tsc/vitest。
