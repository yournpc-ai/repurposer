# Film 分镜核对与参数行（E1）+ 配音/BGM（E2）+ 画幅变体（E3）

> Status: **E1（7d77073）+ E2/E3 主体已落码，全部验证待跑**。母法 = ADR-120（短式）；拍板 = 2026-10-14 用户（A 变体：分镜表坐消息流，不进确认 dock；多轮核对全程 chat，口头「可以，就这样吧」开工）。
>
> E1 待办（接续会话先读这里）：① 用户自跑仪式链——pytest / check_gates / prompt_gate（W6 触 prompt 面必跑）/ chat_scenarios（S11 贴链成片旅程的 dock 行为变了）/ npm test；② 实测验收路径 = §5；③ review 挂账（2026-10-14 自评，未修）：CopyMessageButton Tooltip 改造混入 E1 commit（混批，知情保留）；`StoryboardBlock.instruction` 持久化但全栈无人读（删或补消费场景）；`StoryboardBlock.pages` 实为 hosts 命名失真（改 `page_hosts` 需全栈批）；routes.py `on_storyboard` hook 两处逐字复制（应提 `_make_storyboard_hook` 工厂）；`STORYBOARD_BLOCK_TYPE` 住 schemas.py 而 `CANDIDATES_LOG_TYPE` 住 service.py（同物种常量座位不一）；live 帧 payload 走私 `message_id` + 漏带 policy stamp（无害）；ChatDock live-rows 机械已第二份拷贝（第三块类型出现时必须抽象）。④ 移交：locales 里 recipe demo 预填词（`launch-film-linear/zymix`）仍写 "short launch film"——home 会话 WIP 文件，归他们那批改口。
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

## 3. E2（配音 + BGM）— 已落码待验证

- storyboard schema 加 per-scene `narration`（六变体同加；配音词进分镜表核对——Mic 图标行）。**narration 不做逐字 grounding**（配音 = 言语复述页面事实，设计如此），只挂 sanity cap（`max(60, seconds×20)` chars）；合成期 T2A 窗口拟合（超速 ≤1.35× 重合成，dub 链同款律）
- 合成座位 = `tools/film/narration.py`：逐幕 T2A（`providers/voice.synthesize` 现货），声线 = 人设 voice 块（cloned voice_id / stock_id）→ 兜底 `presenter_male` 系统音色（STOCK_VOICES 注册表仍是缓做项）；每幕一个 storage 对象 `{output_id}_narr_{i}.mp3`；tts_chars 计量同 dub 律
- 配乐：LaunchFilm.run 内解析（mood → 人设 brand musicId/musicMood → "calm"，AddMusic 同一解析序）；显式 mood 无法解析 = 步骤失败（CHAT_ARCH §10），默认链恒落种子库；spec `music: {url, gain_db:-20}`
- 渲染侧：film-spec zod 加 per-scene `audio` + 顶层 `music`；Film.tsx 根级 `<Audio loop>` 床 + 幕内 `<Audio>`（Sequence 边界诚实截断）；film/render.ts 复用 clip 的 loudnorm 后处理（`normalizeLoudness` 导出共享）；staging 同 cache
- 参数行：LaunchFilmParams 加 `voiceover` / `music_mood`（+ E3 的 `aspect`），骑 slot 编译投影（orchestrator 白名单 + IntentSlot 字段）；分镜表头 chips = 核对面（画幅恒显 / 无配音才显 / mood 点名才显）
- 计价：estimate 加 `tts_chars`（14 chars/s × ESTIMATE_FILM_SECONDS）

## 4. E3（画幅变体）— 主体落码待验证，两件挂账

已落码：
- film-spec `aspect`（16:9 / 1:1 / 9:16）全链：params → slot 投影 → spec → Root.tsx `FILM_DIMENSIONS`（calculateMetadata 出宽高）→ payload.aspect 真值 → render_probe 按 aspect 判分辨率 → 画幅框卡预测读 slot
- 构图 = **统一缩放律**：组件一切绝对 px × `s = width/1920`（16:9 是设计栅格，1:1/9:16 等比缩放，竖屏多出的纵向空间留白）——一套代码路径，无分支版式
- chat 可改：`chat_intent_system.j2` 杠杆行（画幅/配音/配乐 = propose_tasks params，同座修订）

挂账（本批未做）：
- **移动视口重采**：9:16 仍用桌面截图缩放（先天别扭仍在）——采集按画幅分视口（capture.py WINDOW_* 参数化 + 竖屏链路重采）留待实证竖屏观感后再做
- **demo 货架填架**（横2/方1/竖2）：每片 = 全链真跑（LLM + T2A + 渲染配额），且货架是 home 会话在途文件——由用户跑片填架

## 5. 验收

- E1：贴链接 → 分镜表呈现 → 两轮修订（时长压缩 + 文案替换）→ 口头 yes → run 直渲（`confirmed_storyboard_used` 日志）→ 产物 probe 闸过；刷新回放分镜表各版在流。
- E2：分镜表逐幕带 Mic 配音词；run 后产物有配音轨 + 音乐床（probe 过、loudnorm 落 -16 LUFS）；`film_narration_scene` 日志逐幕在。
- E3：`aspect=9:16` 的 plan → 产物 1080×1920（probe 按 aspect 判）→ 画幅框卡比例正确。
- 仪式链：pytest + check_gates + prompt_gate（chat_intent / film_storyboard 两 prompt 面都动了）+ S11 复跑 + tsc/vitest（api/web/render 三端）。
