# Film 编排施工——进度台账

> 本文件 = 实际施工状态唯一落盘座。新会话读它即可继续，不依赖聊天搬运。模板见 `docs/tasks/film-storyboard-orchestration-handoff.md`；轮次定义见 `docs/tasks/film-storyboard-orchestration-execution.md`。

## 当前状态

- **当前轮次**：**R3c 修复批收口（2026-10-21）**——GPT 交叉评审 5 finding 全修全绿：全量 **1392 passed**（1385+7）+ check_gates OK。R3 实测收口：全量 1385 + check_gates 复验绿；围栏/阻断 stub 实证；patch 活动文案修复（compose=设计 / patch=调整）。付费面（R3 验收段）：① spike **POSITIVE**（MiniMax 接受并看见 tool-role 图片，选项 A 成立，fallback 不启用）；② 真实 Chat smoke **6 腿全硬断言绿**（读版本/双源分辨/像素问答/取景编辑落 patch/双时钟/超预算重读 + 每腿 L7 授权律）；③ prompt_gate **10/10 探针 PASS**（A 12/12、B 12/12、C 10/12 贴阈、D/E/F/G/H/H4 12/12、I 11/12——I 阈值仍未校准，读数单独解释）。累计消耗：349 HTTP（spike 10 / smoke 16 / gate 323），估算 ≈$0.77（缓存口径；无折扣上限 ≈$2.6——估算非硬顶）。验收证据（脱敏摘要 + 日志副本）= `docs/tasks/film-r3-acceptance-2026-10-21/`。**R3c 未验证项：prompt_gate（工具描述面动过，待授权重跑）；5 修的真实 LLM 旅程端到端未验（付费面）。** R3 范围内只剩浏览器活动展示真实渲染——仍需人工核验；编辑后真实制作/TTS/渲染/计费不在 R3 验收范围（未验证）。**下一轮 = R4，首日 = 旧作品 provenance 完整率抽查（execution.md 既定）。R4 范围已拍板扩展（新需求①）= voice 解析上移设计期 + 版本/快照钉 voice_id + 呈现「制作设置」行；新需求②（文字/知识视频模版能力）= R8.5 新批，排在 R8 后 R9 前。默认门控保持关闭；全部修改未提交、未部署。**
- **flag 状态**：链 flag / compose flag 均不存在（R5/R7 才引入）；**编辑能力门控默认关闭**（`settings.film_edits_enabled`）——R3 的图片/候选视图清单/`views` 参数同闸：关闭时生产 wire 零变化（无 views 参数、无图片描述句、无 base_ref、无候选清单、永不带图），开启（仅本地/测试）时完整送达。**门控不变式 = 供应商未验证的 wire 形态到不了生产**。

## R3c 修复批（2026-10-21）——GPT 交叉评审 5 finding 全修

> 来源：R3 收口后外部评审（GPT）交叉检查 5 finding，本会话逐条独立取证确认属实（座位精确）后修复。排期影响同批落档：新需求①（配音/BGM 可确认）的 voice 半并入 R4；新需求②（文字/知识视频模版）立 R8.5 新批（R8 后、R9 前，~2-3d；禁区：新场景型/转场/自由版式/AI 生图/多轨/声音选择器；G5 不并入）。配乐已在呈现命名（mood—title·BPM，`_dock_music_context` 设计期解析先例）；配音可拒绝本就端到端存在（param + op + validator）——真正缺口只有 voice 不可见。

1. **Finding ① 待产稿可重读**：`GetOutputSpecParams.output_id` 变可选——省略 output id = 读影片**当前**版本（骑 `resolve_film_revision_base` 同一优先级法：live pending 优先，否则最近交付影片的 provenance），与 output 读同一份事实表/base_ref 铸/候选清单/图片；项目零版本时诚实文案指向 design_storyboard。工具描述同步补省略语义。连续修订回合不再卡在「只能读已交付旧版」。
2. **Finding ② 素材身份核对（drift 点名）**：版本执行快照的 `pages[].asset_id` vs 当前 `load_storyboard_pages` 按位置比对——漂移页（删素材/替换/重采集致同 index 异 asset）点名 `- Materials drift` 行；引用漂移页的 ui 场视图行标 `(materials changed — the version's original view is unrecoverable)`，heading/camera 永不对错页解析（不对错页编造事实）；used-by 映射剔除漂移引用（当前页不冒充场景原视图）；候选清单仍列**当前**素材供 update_scene 重接地。**无快照的 legacy 版本跳过核对**（零误报）。
3. **Finding ③ 版本号入 base identity**：`film_version_identity_digest` payload 增 `version`——**只重卡点的新版本**（content/params 字节不动，retime 是执行指令永不是 param）照样使旧 ref 失效，因为 read 展示的冻结时间轴状态已随版本移动。四座同带版本：读取铸 ref（`version=base.film_storyboard_version`）/ 双路快拒 / `apply_film_edits(base_version=)` 复核 / `prepare_film_patch` 的 `next_base_ref` 铸下一版。version-less legacy ref 与 versioned base 也永不匹配（天然拒）。**content 复用 digest 永不带版本**——两种 digest 构造上不可比。
4. **Finding ④ provenance base 的发布重检**：发布守卫从「仅 live-pending base 查版本」扩为「**非钉 base 且（base 骑 live pending 或 committed pending 存在）且 live_version ≠ base 版本 ⇒ 丢弃**」——provenance 恢复后、resolve 与 begin 之间被并发提交的新 pending 使 patch 诚实丢弃（永不覆盖式版本）；无 committed pending 时恢复的世界照常发布。显式 @output 钉仍是唯一豁免（分支语义，钉恒胜）。
5. **Finding ⑤ 冻结时间轴补 reveal onset**：信封新字段 `film_kept_reveal_onsets`（reveal 场 word 落点帧 = 冻结场内切点）——此前 keep_cut 只保场景长度，场内切点在新音乐网格上重算漂移（实测 180f→174f = 早 0.2s）。`reveal_onset_frames` 提取为唯一计算座（spec builder 内联改骑，零行为变化）；`draft_reveal_onsets`/`spec_scene_reveal_onsets`/`valid_kept_reveal_onsets` 新座；`build_film_spec(reveal_onsets=)` 冻结 onset clamp 后骑（零重算）；keep_cut 继承时校验，**冻结切缺 onsets 且板带 reveal 场 = fail-closed `base_cut_unreadable`**；run() 消费 `ctx["film_kept_reveal_onsets"]` 同样 fail-closed。PendingPlan 增字段 + `film_cut_reveal_onsets` 属性（kept 语义绑定）；Start stamping / 钉座 / live-pending 座 / provenance 座全链传递。

## R3c 变更文件（全部未提交，叠于 R3 批上）

- `app/tools/film/edits.py`（identity +version / apply +base_version / prepare 传版本 + next_base_ref 带版本 / FilmPatchPrepared +kept_reveal_onsets / 冻结块继承+校验+fail-closed）
- `app/tools/film/storyboard.py`（`spec_scene_reveal_onsets`/`valid_kept_reveal_onsets`/`reveal_onset_frames` 一座/`draft_reveal_onsets` 新座；`build_film_spec` +reveal_onsets；run() 消费 fail-closed；`_film_revision_base_from_state` +cut_reveal_onsets 三座）
- `app/models/schemas.py`（PendingPlan +film_kept_reveal_onsets + film_cut_reveal_onsets 属性）
- `app/chat/service.py`（Start stamping 带 onsets）
- `app/chat/propose_turn.py` + `app/chat/plan_turn.py`（铸 ref/快拒带版本 + `base_is_pinned` 参数 + 发布守卫扩 + kept_reveal_onsets 传递；双路镜像同构）
- `app/chat/perception/executes.py`（output_id 可选 + 当前版本读取座 + `_film_observation` 重构为 base 参数化 + drift 核对 + 读铸带版本）
- `app/chat/perception/__init__.py`（get_output_spec 描述补省略语义）
- 测试：`tests/test_film_output_spec_pure.py` +4 / `tests/test_film_edits_pure.py` +1 / `tests/test_film_edit_wiring_pure.py` +2 新 + 既有批适配（`_base_ref` 强制 version；全部 keep_cut fixture 穿 onsets + `lead_frames` 等值断言 = finding ⑤ 回归锁）

## R3c 验证（实际运行，2026-10-21）

| 命令 | 结果 |
|---|---|
| `uv run --extra dev python -m pytest tests/ -q`（全量） | **1392 passed in ~8s**（1385 + 7，零回归） |
| `uv run python scripts/check_gates.py` | **OK** |
| 新回归 7 用例 | 当前版本读（seen_resolve==[None] + 同事实表 + 带图）/ 无版本诚实文案 / drift 标不可恢复（无 camera 无 heading 无 used-by）/ legacy 无快照零误报 / version bump identity 失效三腿 / recut-only 快拒零变动 / provenance base 遇 committed pending 发布丢弃 |

## R3c 未验证项

- **prompt_gate 待授权重跑**——工具描述面动过（get_output_spec 描述 + output_id 字段描述），属付费面
- 5 修的真实 LLM 驱动旅程端到端未验（付费面，归 R4 按需授权）
- 剧本矩阵 S11 家族未运行（归后续轮次按需授权）
- 修订场景下 kept-cut 冻结 onsets 的真实 run 渲染未验（断言止于版本落库与 spec 帧）

## R3 完成项（Chat 作品读取与图片机制）

1. **图片 wire 机制（选项 A = 现有消息结构）**：`ToolObservation` +`images`（MediaInput 形，kernel 不引 domain 层——check_gates 5a 约束下 `tuple[Any,...]` 松类型）；loop 的 role:tool 消息座 `_observation_wire_content` 把图片投影为 content parts（text 在前，每图 image_url + caption 对——agents/base.py 媒体配对律同形）。**双路共一座**：propose/plan 双路 dispatch 同走 `run_perception_tool`，同骑一个 `ToolLoopAgent.call_loop`——wire 测试一次证明双路。无图时 content 保持纯字符串字节不变（既有测试锁）。**spike 结论落档**：①本地代码明确支持（MiniMax 两 `generate_*_with_tools` 对 messages 原样透传，无 str()/归一化丢弃点；`_payload_chars` 已识别 parts）②请求形状测试通过（loop wire 测试钉死 parts 到达客户端入参）③**供应商实测 = POSITIVE（2026-10-21 第四段）**——MiniMax 接受并看见 tool-role 图片 parts，选项 A 成立；fallback（synthetic user 消息）不启用、未实现。
2. **事实表扩展**（`get_output_spec` film 分支 → `output_spec_observation`/`_film_observation` 座）：版本 + created_via + content digest 前缀 / canonical 参数（画幅·旁白·音乐 mood）/ **逐场** id·类型·**authored 秒与时间轴时长两列分行**（authored = 设计值；actual/frozen/planned = 权威帧数 ÷ 固定 fps 的单位换算，零重分配）·视图引用（page/shot + heading）·取景文本带元素 id（`ui_focus_moves(with_ids=True)` 一座——呈现侧默认参数行为不变）·**展示文案逐字子句**（`film_scene_content` 座，各场型原值，ui 场无文案；旁白独立子句）·逐字旁白 / **时间轴来源四态标注**（executed cut = spec 帧真值 / frozen = kept 帧 / planned = 版本快照音乐网格上的 `execution_frames` 唯一帧座 / unreadable = 点名不猜；帧数与场数不齐 = 点名损坏不 zip，无时长列）/ 候选视图清单（page·shot·heading·元素数·used-by 场景映射·asset id，fold-only 页如实退化；**随图同行的取景元素清单**——视图截图被 attach ⇒ 目录行附逐元素 `id · kind · "text"`，图片组与元素明细同一组）。计划值永不标成已执行值；缺字段不补成事实；读取零写副作用。
3. **素材截图接入**：fold + section shots，经 `load_storyboard_pages`（与编辑校验同一页面座，(page,shot) 引用同义）；`media_input_for_image` +`max_px` 一座（PIL 长边约束 + JPEG q88；None = 原样——导演 fold 图行为不变）；每张图 caption 绑定 page·shot·heading·host·使用场景。
4. **预算**：单次 ≤12 张 640px 缩略图；`views` 选择子（`ViewSelector{page,shot}`，恰好 1 张 = 1280px 高清再读）；**超预算显式报错零图片**（默认全量超帽 / 命名超帽两路同法，报文点名补救路径 = scoped read 同时携带截图与取景元素清单/元素 id）；缺图（无视图/未存图/读取失败）三类分述，其余图照常送达；回合内重读由 loop max_iterations=12 既有上限收口（无新分页协议）。
5. **门控同闸**：图片/清单/views 参数/base_ref 全骑 `film_edits_enabled`——声明面（wire_view 修剪 `views` + 孤儿 `$defs` 回收，GC 提升为 `tool_loop.prune_wire_parameters` 一座双用）+ 观察面（gate off 永不带图，dispatch 的 with_images 也救不回）；`_website_film.j2` 增 gated 法条（图是素材截图非成片，永不声称看过成片）。

## R3 变更文件（全部未提交，叠于 R2-B 批上）

- `app/agents/tool_loop.py`（ToolObservation +images / `_observation_wire_content` 投影座 / `prune_wire_parameters`+`_defs_refs` 上提一座）
- `app/chat/perception/executes.py`（`ViewSelector` + `GetOutputSpecParams.views` / `output_spec_observation` + `_film_observation` 座 / `_page_view`·`_page_view_count` fold-only 退化 / `_film_view_image` 测试缝 / 预算三常量；`get_output_spec` 保留为文本包装）
- `app/chat/perception/__init__.py`（PerceptionTool +wire_view 透传 / get_output_spec 描述拆 base+图片句常量 + gated wire view / `run_perception_tool` 分发座带图）
- `app/chat/turn_tools.py`（GC 改骑 `prune_wire_parameters`，行为不变）
- `app/pipeline/step_context.py`（`media_input_for_image` +`max_px` + `_resized_data_url`）
- `app/tools/film/storyboard.py`（`ui_focus_moves` 提取共享座 + `with_ids` 读取侧变体，呈现内联改骑零行为变化；`film_scene_content` 新座——逐字展示文案）
- `app/prompts/chat/_website_film.j2`（gated 图片法条一句）
- 测试：`tests/test_film_output_spec_pure.py`（新，15 用例）+ `tests/test_tool_loop_pure.py`（+1 wire 形态）+ `tests/test_film_edit_wiring_pure.py`（2 既有用例适配新事实表格式 + `load_storyboard_pages` stub）

## R3 验证（实际运行，2026-10-21）

| 命令 | 结果 |
|---|---|
| `uv run --extra dev python -m pytest tests/test_film_output_spec_pure.py -q` | **13 passed**（事实表+四态时间轴标注 / 损坏帧数点名 / 默认超帽显式报错零图 / 命名选择子+单图高清 / 命名超帽+未知视图 / 三类缺图分述 / fold-only 退化 / 门控双态（观察面+wire 面）/ 钉恒胜 / dispatch 座带图 / 压缩座真 PIL round-trip） |
| `uv run --extra dev python -m pytest tests/test_tool_loop_pure.py -q` | **42 passed**（+1：图片 parts 上 tool 消息 + 拒绝后 tail 字节不变不重读） |
| `uv run --extra dev python -m pytest tests/ -q`（全量） | **1379 passed in ~11s**（1365 + 14，零回归） |
| `uv run python scripts/check_gates.py` | **OK**（kernel 边界 5a 拦下 MediaInput 直引，已改松类型过闸） |

## R3 未验证项（限 R3 验收范围）

- ~~MiniMax tool-role 图片 spike~~ **已运行（2026-10-21）= POSITIVE**，证据见 `docs/tasks/film-r3-acceptance-2026-10-21/`。
- ~~prompt_gate~~ **已运行（同日）= 10/10 PASS**（共享路由回归口径）。
- ~~真实读图旅程 smoke~~ **已运行（同日）= 全硬断言绿**。
- **浏览器活动展示真实渲染——仍需人工核验（R3 范围内唯一剩余）**：patch 活动文案的 SSE 线形（服务端真值）已实证；界面呈现（now-line/落定行/折叠类目）未在浏览器实测。
- **编辑后真实制作、TTS、渲染及计费：本轮未验证**——L4 patch 的断言止于待产版本落库（pending v2）；真实 run 执行、旁白合成、渲染出片与计费结算不在 R3 验收范围，归 R4+ 轮次。
- 剧本矩阵 S11 家族延续未运行（归后续轮次按需授权）。

## R3 实测收口会话（2026-10-21 第二会话）——准备与免费验证段（已执行，全部本地/免费）

**环境实证**（以实际代码为准）：生效配置 = minimax-m3 @ `https://api.minimax.chat/v1`（repo 根 `.env`，`apps/api/app/config.py` `_REPO_ROOT/.env`），key 在位；本地 Postgres @ localhost:5432/repurposer；S3（TOS repurposer-dev）下载实测可用；门控默认关。底层重试事实：`generate_with_tools` tenacity ≤3 次（HTTP/传输错，LLMSchemaError 不重），流式变体首发射前 ≤3 次——**一次逻辑调用最坏 = 3 次真实请求**；chat loop max_iterations=12（intent.py:325/361）。

**已执行的免费验证**（命令与结果）：

| 验证 | 命令/方式 | 结果 |
|---|---|---|
| 全量回归复验 | `uv run --extra dev python -m pytest tests/ -q` | **1381 passed**（本会话 HEAD） |
| 静态架构门 | `uv run python scripts/check_gates.py` | **OK** |
| prompt 面归因 | j2 三态渲染（HEAD / 门控关 / 门控开）diff | 门控关 ≠ HEAD：差异 = R2-B 有意措辞修订（OPEN feedback / review_hold 例句 / approval 句重组）+ R3 门控段不渲染；门控开 +1265 chars。**prompt_gate 确有必要**（自 R2-B 起未跑） |
| spike 脚本 dry-run | `uv run python scratch/spike_tool_role_image.py --dry` | wire 形态实证：C0 无图 = 纯字符串（53ch）；C1 = `[text:53ch, image_url:30023ch, text:37ch]`（生产 `_observation_wire_content` 投影）；C2 user-role = `[image_url, text, text]`（导演同构形）；2 迭代收敛 |
| smoke fixture 播种 | `uv run python scratch/film_read_smoke.py --seed` | 隔离用户 + 项目 R（克隆真实 3 页采集 = 12 视图，卡预算线）+ 项目 B（+1 页 = 14 视图，超预算）；fixture 资产 `file_url=None` + **只读复用源截图 key**（删除只动 fixture 自身前缀，源项目对象零接触——delete 路径逐行核对过）；provenance（run ctx 板/参数/digest/执行快照 + render_spec 帧）逐字节拷自真实已执行影片 |
| **读取座端到端（除 LLM 全链）** | `uv run python scratch/film_read_smoke.py --verify`（in-process 翻门控） | **全绿**：R 默认读 = 17116 chars 事实表 + 12 张 640px JPEG（~40KB/张，caption 绑 page·shot·host·使用场景）+ 逐元素取景清单（真元素 id）；B 默认读 = 显式预算报错**零图**、补救文点名 scoped read、无孤儿元素清单（图与元素明细同组）；B scoped 单视图 = 1 张 1280px（83.7KB vs 缩略 40KB）+ 清单 |
| **编辑核离线实测** | in-process：真 `resolve_film_revision_base`（钉座）+ 真 `prepare_film_patch`（真 validator + 真页面）对 fixture | **正腿接受**：update_scene(s5, focuses=[s1e15]) → change_set `edited:[{s5, focuses}]`，冻结帧继承已执行 spec（[90,152,244,69,240…]）；**负腿拒绝**：猜测 id `s1e99` → `FilmEditError validation_failed INVALID_FOCUS` 点名「element s1e99 names nothing in shot 1's inventory」 |

**判读依据已建立**（smoke 断言的地面真值）：两张关键截图已下载目验——fold 大标题「We enable developers to create stunning presentations」（与影片 s1 叠字「Slide deck blues?/Same old slides./Almost there.」零重叠，双源分辨腿用）；page0 shot1 = 绿底代码面板（smoosh.py，像素独有知识）+「Share interactive slides」卡片 = 元素 `s1e15`（取景修改腿的目标 id，模型只能从读取清单获得）。板为 legacy 无 scene_id（读取派生 s1..s15，顺带实测 legacy 升级路径）。s14 authored 8.0s vs actual 245f=8.2s（两时钟腿判据）。

**本轮第二段收口（复审意见落实，全本地/免费）**：

1. **调用上限落实为强制围栏**（不再是估算）：① spike 脚本加 `_instrument()` 请求围栏——共享 httpx 池客户端的 post/stream 被包装，超帽**在发包前**抛 `ProviderFenceTripped`（刻意非 LLMError/TransportError，任何重试层不吞；tenacity 重入会即再绊、零真实请求越帽——`--selftest` 实证：连发 30 次后第 31 次零发包）。分层计数钉死：**spike 逻辑调用 = loop 迭代（3 案 × max_iterations=3）+ C2 单发 = 最坏 10 逻辑调用；HTTP 请求 = 逻辑调用 × ≤3（tenacity/首发前手动重试）→ 强制帽 30 次 + 600s 墙钟**。② smoke 的活链调用发生在 API 进程，围栏随门控实例注入——新座 `scratch/run_api_gateon.py`：127.0.0.1:8001 第二进程（**不动在跑的 8000/worker**），进程级 env 翻门控（.env 零改动）、关 warmup、httpx 类级包装只数 MiniMax host 的请求（**强制帽 216 次 = 6 腿 × 12 迭代 × 3 重试 + 3600s 墙钟**）。启动实测：8001 可服务、围栏武装、零 MiniMax 调用（warmup 已关），已关实例。
2. **制作阻断改为确定性边界**（辅助层归位）：fixture 两项目的 pending 现播种 **standing review hold**（`film_review_hold=True`，film_* 键与 run ctx 同字节 → 钉座与 pending 座 base_ref 一致，已实证 `ref_pin == ref_pending`）。证据链：`evaluate_start_gate` 对 hold=True 的 film 链返 **422 `start.review_hold`，在 create_run 之前**（`pipeline/lifecycle.py:431-432`；create_run 只 flush 由调用方提交）；离线实测：hold=True → 422，对照 hold=False → 放行（None）。且 fixture 无 dock token，`draft_match=False` 会先撞 409 `start.stale_storyboard`——双闸都在付费 create_run 之前。零钱包 / ask+ask / 旅程永不发批准词 / 事后断言全部降级为辅助层。授权断言语义已修正：**读取不改状态**（读腿前后 `pending_brief` 字节比对）+ **standing hold 不被释放**（含 L4 patch 落版后仍须为 True）；不再用「hold 不出现」式错误断言。
3. **smoke 断言核纯函数化 + stub 实证**：每腿 answer 律（check_l1/l2/l3/l5/l6）与 activity 采集（全帧 kind/key/status 落 transcript）提成纯函数，`--selftest` 用构造 StreamTurn 跑 11 组正负 stub 全按设计通过（不跑真模型）。L4 增 activity 布线断言（落版 ⇒ draft-kind 跨度必开必落），且只在落版分支内检查（模型未落版 = 软失败单列，不污染硬断言）。

**Chat 工具链展示定点调查（差距清单；实际行为 → 用户影响 → 最小修复 → 所属轮次）**：

| # | 实际行为 | 用户影响 | 最小修复 | 所属轮次 |
|---|---|---|---|---|
| 1 | ~~**patch 拍复用 compose 的分镜跨度键**~~ **已修复（2026-10-21 第三会话，本地验证绿）**：`ReadExecuting` 增 `params` 字段（验证后参数 = 开局座唯一可确认变体的事实源，name_known 永猜不到）；projector 开局座按 `edits` 在场选 `_STORYBOARD_EDIT_KEYS`（`chat.activity.storyboardEdit`/`storyboardEditDone`），`_done_key`/`frame_persistence`/持久化/耗时四座同法覆盖；前端 `chatTimeline.ts` 过滤器放行四键族 + en/zh 文案（正在调整分镜…/已调整分镜）+ vitest 用例 | ~~用户在 transcript 永久看到一条措辞不实的「已设计分镜」回执~~ | 已实施；**浏览器真实渲染未验证**（归付费 smoke 后人工核验）；smoke L4 已增线形断言（落版 ⇒ draft 跨度必为 edit 键对） | ~~R2-B 批次~~ 本会话收口 |
| 2 | film 读取（带 12 图，数秒）显示「正在读当前设置…」（en "Reading the current settings…"）——既有键，clip/film 共用 | 措辞精度一般（读的是影片版本事实+视图截图，不止"设置"），非错误 | 若要精确：fork 需 output 类型比特，代价同上通道；建议不动 | 观察项，不立项 |
| 3 | `chat.inspectingFailed` 族只有 `understanding` 一键；get_output_spec 恒 ok=True（「无此 output」是诚实文本行而非失败读）——若未来 film 读真失败，落定 FAILED 的 label 会回退兜底 "Done"（✗ 红字仍在） | 假想路径，当前不可达 | 补键是单行事；随需要再做 | 预存缺口，非本批引入 |
| 4 | 读图的真实耗时（TOS 下载 + 压缩）由 ReadExecuting 重锚定诚实计量；预算报错读以 completed 落定（读确实成功，报错文在正文）；缺图三态分行——全部诚实 | 无 | 无 | —（核验通过项） |
| 5 | Start 后持久化制作 Tasks（RunTaskList）：film run 当前单 `launch_film` 步骤行，builder-written summary；宏阶段行（film_prepare/narrate/assemble）尚不存在 | 当前形态诚实（一步就是一步） | 宏阶段 Tasks 行 = R5 本体（链黑暗落地）+ R6（结算边界） | **R5/R6**（本轮不动） |

前端实测面标注：以上前端行为全部来自代码阅读（ActivityStream/activityReducer/RunTaskList/historyReplay/chatTimeline + en/zh 文案 + vitest 套件存在性），**真实界面渲染未运行（未验证）**——smoke 的 activity 断言钉的是 SSE 线形（服务端真值），浏览器呈现面归付费 smoke 后的人工核验。

**本轮第三段收口（2026-10-21 第三会话，全本地/免费——复审意见的围栏准确性与独立阻断落实）**：

1. **围栏准确性修正（spike）**：墙钟承诺从「只在下次发包前检查」升格为**真·总运行限时**——live 段骑 `asyncio.wait_for(MAX_WALL_SECONDS)` 外层可取消超时（超时取消在途请求），围栏的发包前检查保留为双保险。`--selftest` 重写为四腿并全部实际执行：(C) 在途请求被外层超时取消（CancelledError 落进传输 stub，清理实证）；(A) 计数帽 30 次绊闸、零越帽发包；(B1) **真实 streaming loop 传播**——真 `ToolLoopAgent.call_loop` + 真 `MiniMaxClient` 在围栏耗尽下首发射即绊、`ProviderFenceTripped` 穿出 loop（streaming 重试环的 `except (TransportError, LLMError)` 吞不到：恰好 1 次 trip 零重入）；(B2) **tenacity 重入重绊**——真 `generate_with_tools` 三次 attempt 各绊一次（3 trips）、`reraise=True` 透出原异常、零越帽。新增 `TRIPS` 台账支撑精确断言。报告输出与实际执行逐条一致。
2. **独立制作阻断（8001 启动器）**：`_install_run_blocker()` 在 app import 前把唯一出生地 `orchestrator.create_run` 换成进程内拒绝（`TestRunCreationBlocked`）——**先于任何 DB 写入与入队**，不查 hold/钱包/确认态/模型输出；读、提案、隔离 patch 不触 create_run 故不受影响；生产默认代码与 8000/worker 零改动。`--selftest`（新）三腿实证：MockTransport 下围栏 MiniMax 域计数 + 到帽先绊零越帽；阻断器对「触碰即炸」哨兵入参拒绝（拒绝先于任何输入读取）；模块属性 / deferred import / patch 后 module-level import（routes/projects.py 真实绑定）三式同证指向拒绝函数。smoke 文档改为两层表述：阻断器 = 确定性测试边界；standing hold = 被测产品法（L7 直读数据库自证，阻断器永不能掩盖 L7 失败）。
3. **prompt_gate 最小围栏包装（新座 `scratch/run_prompt_gate_fenced.py`）**：不改 gate 脚本本体。结构帽 = 选中探针 × n × 12 迭代 × 3 重试（全量 4320，**结构性最坏值 = 强制帽，非估算**）；外层 `asyncio.wait_for` 可取消墙钟（默认 7200s， `--wall` 可调）；围栏异常继承 BaseException——gate 的 `except Exception` 会把 RuntimeError 误记为 provider INVALID 并继续烧钱，BaseException 让绊闸立即响亮停跑。预期调用数只以 ESTIMATE 字样打印，永不写成硬限制。零请求 plumb 验证已跑（`--probe A --n 0`：参数透传 / 围栏武装 / 计数打印全通）。
4. **patch 活动文案修复（差距清单 #1，本会话已修）**：见表格行 1。验证：`test_activity_pure.py` +3 用例（edit 键对开落+持久化+耗时 / compose 双态字节不变 / 失败-取消-收尾终态律）、`test_tool_loop_pure.py` +1（ReadExecuting 携带验证后参数）、`chatTimeline.test.ts` +1（patch 键对不被 draft 过滤器吞、cancelled 行透传）。

**第三会话验证（实际运行，全部免费）**：

| 命令 | 结果 |
|---|---|
| `uv run --extra dev python -m pytest tests/ -q`（全量） | **1385 passed**（1381 + 4 新） |
| `uv run python scripts/check_gates.py` | **OK** |
| `uv run python scratch/spike_tool_role_image.py --selftest` | **四腿全绿**（取消清理 / 帽 / streaming 传播 / tenacity 重绊） |
| `uv run python scratch/spike_tool_role_image.py --dry` | wire 形态不变（C0 纯字符串 / C1 parts / C2 user-role） |
| `uv run python scratch/run_api_gateon.py --selftest` | **三腿全绿**（围栏计数+绊闸 / 阻断先于输入 / 三式绑定） |
| `uv run python scratch/run_prompt_gate_fenced.py -- --probe A --n 0` | plumb 绿（零请求；帽=0 时任何请求必绊的设计自明） |
| `uv run python scratch/film_read_smoke.py --selftest` | 11 组 stub 全按设计（不变） |
| `cd apps/web && npm test`（vitest 全量） | **180 passed (15 files)** |
| `npx tsc --noEmit`（apps/web） | **clean**（含 `zh: Resources` 键对齐） |

**第三会话变更文件（叠于既有未提交批上）**：`app/agents/tool_loop.py`（ReadExecuting +params）、`app/chat/activity.py`（edit 键对 + 变体选择座）、`tests/test_activity_pure.py`（+3）、`tests/test_tool_loop_pure.py`（+1）、`apps/web/src/lib/chatTimeline.ts`（四键族放行）+ `.test.ts`（+1）、`en.ts`/`zh.ts`（storyboardEdit 键对）、`scratch/spike_tool_role_image.py`（外层超时 + TRIPS + selftest 四腿）、`scratch/run_api_gateon.py`（阻断器 + selftest + 墙钟诚实表述）、`scratch/run_prompt_gate_fenced.py`（新）、`scratch/film_read_smoke.py`（两层阻断表述 + L4 线形断言增 edit 键对 + L7_NOTE 修正）。**未跑验证**：浏览器真实渲染（标注未验证）；三项付费面于同日第四段执行完毕（结果见下节）。

**付费面实测（2026-10-21 第四段，三项授权后执行——顺序：spike → smoke → prompt_gate）**：

1. **图片 spike = POSITIVE（选项 A 成立，fallback 不启用）**。两跑：首跑 5 HTTP / 4,034 tokens 判 INCONCLUSIVE——归因 = 探针测量缺口（判读只读 prose，模型把发现写进 answer 工具参数，content 通道为空；非供应商错误、非 wire 问题）；修复 = answer 工具带 `findings` 字段 + 判读读双通道（selftest/--dry 复验绿）。第二跑 5 HTTP / 4,546 tokens：C1（tool-role 带图）命中随机码词（只在像素）+ 底色/红方块/七椭圆全对；C0（无图）诚实承认无图、码词零泄漏；C2（user-role 对照）命中。**MiniMax 接受并看见 role:tool 消息的图片 parts**（C1 迭代 2 载荷 30,610 bytes 含图，200）。附带观测：图像 token 化 ≈300 tokens/640×360 JPEG（非 base64 文本计费）——**单个探针样本的观测值，非通用计费规律**（不同尺寸/内容/供应商策略的费率未测量，不得推广）。spike 阶段累计：10 HTTP / ≈8,580 tokens / 估算 ≈$0.004。计数说明已修正（2 loop 案 × ≤3 迭代 + C2 单发 = ≤7 逻辑调用、≤21 HTTP；帽 30 为保守围栏值）。
2. **真实 Chat smoke = 全硬断言绿（6 腿 + 每腿 L7）**。活链：8001 门控开实例（围栏 + 独立 create_run 阻断武装，warmup 关）→ 真 SSE 回合。
   - L1：version 1 / 15 scenes（s1–s15）/ 9:16 / ≈89s / voiceover on——读帧在，事实全对；
   - L2：叠字三行逐字引用（"Slide deck blues?"…）+ fold 大标题（"We enable developers…"）双源分辨；
   - L3：绿底代码面板（smoosh.py）+「Share interactive slides」卡——像素独有知识；
   - L4：`update_scene(s5, focuses=[s1e15])` 落版，pending version 2——元素 id 来自读取清单非猜测；**活动线形 = `('draft','chat.activity.storyboardEdit','active') → ('draft','chat.activity.storyboardEditDone','completed')`**——patch 拍「调整」文案的服务端线形实证（浏览器渲染仍未验证）；
   - L6：8.2s（245f）actual vs authored 8s 双时钟分辨；
   - L5：14 视图超预算 → 默认读报错零图 → 模型 scoped 重读（3 次读调用），定价页 fold 像素级事实全对（$0/$5/$9/$32 档位、Save 33%、对比表首行），并正确指出「四个定价视图未被任何场景使用」（used-by 映射真值）——未伪装全量读；
   - L7（每腿后）：零新 run/output/台账行；读取腿 pending 字节不变；**standing hold 全程未释放（含 L4 落版后仍 True）**。
   - 阻断器全程未触发（产品门先拦 = 设计内；阻断器是兜底非主闸）。8001 实例已关（只清本会话进程）。产物 `/tmp/r3_smoke_transcript.md`。
   - 消耗：16 HTTP（帽 216）；prompt 457,852 / completion 6,891 / cached 262,563 tokens；估算 ≈$0.08（缓存 2 折口径）~$0.15（无缓存口径）。
3. **prompt_gate = 10/10 探针 PASS（共享路由回归口径）**。活性探针 `--probe A --n 2` = 2/2（provider 活性确认，无 402，前缀缓存命中 24,079/24,080）；全量经围栏包装一次跑完（未复跑、未调阈）：A 12/12（阈 8）、B 12/12（阈 8）、**C 10/12（阈 10——贴阈过线，读数记录在案不动作）**、D 12/12、E 12/12、F 12/12、G 12/12、H 12/12、H4 12/12、**I 11/12（阈 8 = 占位值，官方口径仍未校准——唯一失败形态 terminal=None 一次，本读数即校准样本，不刷绿不调阈）**。零 INVALID / 零 provider error。消耗：323 HTTP（探活性 2 + 全量 321；session 台账 323/600）；prompt 7,442,324 / completion 137,143 / cached 7,104,237 tokens（缓存命中 ≈95.7%）；估算 ≈$0.69（缓存 2 折口径；无折扣上限 ≈$2.4）。范围声明不变：gate 只是共享路由回归，**film 的真实读取/编辑证据来自 spike 与 smoke（上两条）**，互不冒充。

**下一会话第一步**（已于 2026-10-21 第四段全部执行完毕，结果见同节「付费面实测」；此行保留作历史记录）：~~授权后 ① 跑 spike…~~

**付费面授权清单**（2026-10-21 第三会话提交、第四段已按授权执行完毕——结果见本节「付费面实测」；清单保留作授权范围的历史记录）：

1. **供应商图片 spike**（`scratch/spike_tool_role_image.py`）— 范围：3 案（C0 无图对照 / C1 tool-role 带图受测 / C2 user-role 带图对照隔离变量），反作弊随机码词只在像素。前置：无（独立进程直调客户端）。调用次数：**逻辑调用 ≤10**（3 loop × max_iterations 3 + C2 单发；预期 5），**HTTP 请求强制帽 30（发包前绊闸）+ 600s 总运行限时（外层可取消超时，取消在途请求）——两座均已 stub 实证（selftest 四腿）**。输出限制：每答 ≤2 短字段（码词+底色），无 max_tokens 显式参数（客户端不带此参，模型自然短答——输出上限**未强制**，属供应商默认）。费用估算：每请求 ≤2K 文本 token + 1 图（按 4K token/图高估）→ 预期 ≈$0.005，**估算区间 ≤$0.05**（非硬顶）。停止条件：任一 4xx/异常即停该案并归类（认证/格式/传输/视觉分开记）；围栏跳闸/外层超时 = 立即停。判读：C1 命中码词且 C0 不中 → 选项 A 成立；C1 盲 C2 中 → 阴性启用选项 B fallback；两图皆错 → 视觉能力/图质问题非 wire 问题。
2. **真实 Chat 读取/编辑 smoke**（`scratch/film_read_smoke.py --run` + `run_api_gateon.py`）— 范围：6 腿真 SSE 回合（L1 点名读版本 / L2 叠字 vs 截图文字 / L3 scoped 视图像素问答 / L4 取景编辑落 patch 层即止 / L6 authored vs actual / L5 超预算重读），每腿后 L7（辅助三连 + 读不改状态字节比对 + standing hold 不被释放）。前置：fixture 已播种；门控开实例 8001（自带围栏 + **独立 create_run 阻断**——与产品态无关的测试边界，selftest 三腿实证）。调用次数：**逻辑调用最坏 72**（6 腿 × max_iterations 12；预期 15-25），**HTTP 强制帽 216 + 3600s 发包前墙钟（随门控实例落实；在途请求由连接池 120s 超时 + harness 每回合 300s 客户端超时收口，围栏不取消在途——已如实标注）**；harness 每回合 300s 超时。输出限制：供应商默认（未强制）。费用估算：12 图 × 640px 随 observation tail 迭代重发，预期 ≈$0.15-0.3，**估算区间 ≤$0.8**（非硬顶）。停止条件：任一腿 turn.failed 或硬断言红即停（harness check 抛 ScenarioFailure）；围栏跳闸 = 回合失败诚实上报。产物 `/tmp/r3_smoke_transcript.md`。
3. **prompt_gate 全量**（经 `scratch/run_prompt_gate_fenced.py` 包装；10 探针 × n=12，门控关 = 生产形态）— 范围声明：A-I 探针量路由/方案行为，**不覆盖 film 读取旅程**（film 行为归 smoke，不拿旧探针冒充 film 验收）；本轮 prompt 面与 HEAD 差异已归因（R2-B 措辞 + R3 门控句关时不渲染）。前置：先 `--probe A --n 2` 探活性（402 = INVALID 协议作废读数非 FAIL）。调用次数：**预期逻辑调用 ≈240（估算）**；**强制帽 = 结构最坏值 探针×n×12×3（全量 4320 HTTP）+ 7200s 可取消墙钟（包装已落实并 plumb 验证）**；绊闸即停跑（BaseException，不被 gate 的 provider-error INVALID 记账吞掉）。费用估算：系统+工具 prefix ≈20-24K token/调用（实测 75-85K chars），前缀缓存 2 折后预期 ≈$0.7-1.2，无缓存最坏 ≈$1.9（**估算**；强制帽只限请求数不限美元）。停止条件：探针 INVALID/FAIL 协议既定（复跑一次→二分归因，永不为放行调阈）；围栏跳闸/超时 = 停跑。

三项合计预期 ≈$1-1.5（**估算**）；**无严格美元总顶**（图像 token 率未证实；请求数有强制帽，美元没有），授权时按量级理解。

## R3 复审回修（评审三项读取契约缺口，2026-10-21 同日修复并验证）

复审判定 wire/门控方向无误，但三处本地读取契约缺口必须先修（不修即阻断付费验收与 R4）：

1. **[P1] 逐场行缺展示文案 → 已修**：非 ui 场型按场读取展示字段原值（words lines/dark、hero word/sub、divider label/roll、plate title/cards、reveal lead/word/sub、end name/tagline）——新座 `film_scene_content`（storyboard.py，与呈现事实表同层、docstring 互挂防漂移；ui 场无文案返回空）；旁白仍独立子句；零概括零改写零截图猜测。覆盖 = 呈现面同字段（读 > 写：plate cards 可读，`_COPY_SLOTS` 仍是可写白名单）。
2. **[P1] 候选视图缺元素引用 → 已修**：图片计划前移到清单之前——**随图同行的取景元素清单**（视图截图被 attach ⇒ 其目录行附 `camera targets:` + 逐元素 `id · kind · "text"`，covered 元素点名遮挡），图片组与元素明细**同一组**，scope 由 `views` 显式给出（超预算报错文点名补救 = scoped read 同时携带截图与元素 id）；场景行取景文本骑 `ui_focus_moves(with_ids=True)`（已解析 → `push to "text" (kind) [id]`；失效元素点名漂移，永不静默降级 center push）；呈现侧默认参数字节不变。
3. **[P2] 秒/帧混两时钟 → 已修**：分行分列——逐场 `authored {seconds}s`（设计值）+ `{actual|frozen|planned} {frames÷fps}s ({frames}f)`（权威帧数 ÷ 固定 fps 的单位换算，零重分配零 snap）；时间轴行带 `· total {sum÷fps}s ({sum}f)`；unreadable/帧数不齐 = 无时长列 + 点名；锁定混合形态的测试全部改写。

**验证（实际运行，2026-10-21）**：

| 命令 | 结果 |
|---|---|
| `pytest tests/test_film_output_spec_pure.py -q` | **15 passed**（13 + 2 新增：七场型原文覆盖 / **闭环**——scoped 读的元素 id 构造 update_scene 过真实 `apply_film_edits` + 真实 `validate_storyboard` 被接受、读取逐字文案经 `copy_slots` 白名单改写被接受、猜测 id 被同校验点名拒绝；预算报错补救文锁定） |
| `pytest tests/test_film_edit_wiring_pure.py tests/test_tool_loop_pure.py tests/test_film_edits_pure.py tests/test_film_storyboard_pure.py -q` | **202 passed** |
| `pytest tests/ -q`（全量） | **1381 passed** |
| `python scripts/check_gates.py` | **OK** |

变更（叠于本节 R3 批上，未提交）：`executes.py`（图片计划前移 + 两时钟分行 + 元素清单同行 + 报错文）、`storyboard.py`（`film_scene_content` 新座 + `ui_focus_moves` with_ids）、`test_film_output_spec_pure.py`（断言全面改写 + 2 新用例）、`test_film_edit_wiring_pure.py`（2 用例已随上批适配新格式）。**未验证项不变**（MiniMax spike / prompt_gate / 读图旅程 smoke 仍待授权）。

## R3 风险与注意

- **供应商风险被门控结构性隔离**：gate 默认关 ⇒ 生产 wire 永不带 tool-role 图片；spike 阴性也不影响生产（fallback 启用前编辑能力本就不开放）。
- 读取的页面座 = `load_storyboard_pages` 当前 READY 页（与 patch 校验同座）：设计后重采集的页面，其新 shots 对读取与编辑同义；版本执行快照的漂移门（run 期重算 digest）不受影响、职责不变。
- 回合内图片随 observation_tail 在后续每次迭代重发（既有 tail 语义）——12 张 640px JPEG ≈ 1MB 级 payload × 迭代数，由 max_iterations=12 收口；无跨回合持久（chat 本就不回放 tool 消息）。
- 旧 Output（无 cuts/快照字段）读容忍：cut_state None 按 draft 呈现计划时间轴；provenance 不可恢复的旧行维持 R2-B 的 honest unrecoverable 行。
- Pyright IDE 诊断为环境噪音（venv 未解析），非本轮引入。

## 工作区修改归属

- 本迭代产物**全部未提交**：R1 + R2-A + R2-B（含修正轮与复审回修）+ **R3（本节清单）** + 四份 docs
- 既有无关未跟踪文件不动：`a.json`、`apps/api/scratch/forensics_*.py`

## 下一轮起点：R4（execution.md R4 节）——R3 已通过复审（2026-10-21）

**R3 收口判定（2026-10-21，复审通过）**：execution.md 验收的纯测试面（投影形状/预算帽/超预算报错）全绿；评审三项读取契约缺口已修复并验证；读取座端到端与编辑核离线实测绿；**付费三项实测完成**——spike POSITIVE（选项 A 成立，fallback 不启用）、真实读图旅程 smoke 全硬断言绿（含 L4 patch 活动线形 = storyboardEdit 键对、L7 授权律每腿通过）、prompt_gate 10/10 PASS（共享路由回归口径，I 读数 = 校准样本）。**R3 范围内唯一未验证项 = 浏览器活动展示真实渲染（仍需人工核验）**；编辑后真实制作/TTS/渲染/计费不在 R3 验收范围（未验证，归 R4+）。验收证据 = `docs/tasks/film-r3-acceptance-2026-10-21/`。

**R4 首日 = 旧作品 provenance 完整率抽查**（prepared_storyboard/spec captions/语音配置字段存在性——execution.md 既定）。**本轮收口即止：不自动进 R4；默认门控保持关闭；全部修改未提交、未推送、未部署。**

---

## R2-B 复审第二轮回修（2026-10-20 第三轮评审两项 → 同日收口并验证）

## R2-B 复审第二轮回修（2026-10-20 第三轮评审两项 → 同日收口并验证）

1. **[P1] 连续编辑丢失冻结时间轴 — 已修并验证（冻结时间轴升格为版本状态）**
   - 复审复现：原片（旧床 snap 移动首/末幕）→ 换音乐 keep_cut → 再关旁白；第二刀无 `set_music` ⇒ 旧码 `kept_frames=None`、后续 run 回缺省按新床网格重卡，切点漂移。
   - **最终修法**：冻结切点不再是「本轮 keep_cut 指令的附属物」，而是**版本状态按实际变化继承**——`prepare_film_patch` 失效判定改为依赖驱动：批次改时间轴（moved/removed/added/retimed 非空）或带存活 recut ⇒ 合法丢弃（run 重新 allocate+snap，旧帧不盲目沿用）；其余批次**继承** base 的已确定切点（`film_cut_frames`：已执行 = spec 帧含 flex 真值；冻结草稿 = 信封 kept 帧），与本轮是否提音乐无关。普通草稿（从未执行从未冻结）无可继承状态：显式 keep_cut 仍冻结其已呈现计划时间轴，无指令批次不落 kept 帧（run allocate+snap 数学等价、旁白 flex 保持存活——零行为变化）。
   - **全链核对**：版本保存（`film_design_state` fresh/reuse 双支携带）/ 恢复（三座 resolve + `PendingPlan.film_cut_frames` 属性）/ Start stamping（service.py 投影不变）/ **run 消费门改为 `film_kept_frames` 在场即 fail-closed 消费**（keep_cut 指令无帧 = 半写信封同罪诚实失败；旁白 flex 冻结同门——继承冻结的版本重合成台词超窗同样诚实失败）。`film_music_retime` 仍投影，但只作指令 provenance + 绊线，不再是消费门。
2. **[P1] 已执行基准切点不可读时静默重算 — 已修并验证（来源区分 + 结构化拒绝）**
   - 旧码：`film_cut_frames=None` 统一退回 `execution_frames(board, base_beats)` 重算，不区分「未执行草稿」与「已执行但 spec 缺失/损坏」——后者伪造原片实际时间轴（flex 后真值丢失）。
   - **最终修法**：基准恢复链路携带切点**来源** `film_cut_state`（`spec` / `kept` / `draft` / `unreadable`）：pin 座（Output 必为已执行，spec 读不出即 unreadable）/ live-pending 座（kept 或 draft）/ provenance 座（**无 film output 行 = draft**——从未交付，已呈现计划时间轴可信；有行但 spec 缺失/损坏 = unreadable）。`unreadable` 下任何保时间轴的 patch（显式 keep_cut 或继承）结构化拒绝 `base_cut_unreadable`（修复回声指引重读版本或显式 recut；改时间轴的批次不受影响），零版本落库、原状态不变、不 500。损坏的冻结时间轴永不再当普通草稿缺省值。
   - ADR-137 决策点 8 已改写为现行法（DECISIONS.md）；总设计 §7.2 增「冻结时间轴 = 版本状态」段。

### 本轮变更文件（在 R2-B 批上叠加，全部未提交）

- `app/tools/film/edits.py`（`prepare_film_patch` 继承/失效律重写 + `base_cut_unreadable` 专用修复回声 + `FilmPatchPrepared.kept_frames`/`film_music_retime_of` 注释对齐）
- `app/tools/film/storyboard.py`（`_film_revision_base_from_state` +`cut_state`；`resolve_film_revision_base` 三座来源标记——provenance 座 output 查询改 `one_or_none` 行形以区分「无行」与「spec 为 NULL」；run() 帧座消费门 + flex 冻结门改 kept 在场；`film_design_state` 注释）
- `app/models/schemas.py`（`PendingPlan.film_cut_state` 属性 + 信封注释对齐）
- `app/chat/service.py`（Start stamping 注释对齐；代码不变）
- `docs/DECISIONS.md`（ADR-137 点 8 改写）+ `docs/tasks/film-storyboard-orchestration.md`（§7.2 版本状态段）
- `tests/test_film_edit_wiring_pure.py`（+4 用例；`_provenance_base` 带 cut_state；flex 冻结测试补继承腿）

### 验证（实际运行，2026-10-20 复审二轮）

| 命令 | 结果 |
|---|---|
| `uv run --extra dev python -m pytest tests/test_film_edit_wiring_pure.py -q` | **47 passed**（43 + 4 新：链式继承全旅「原 spec → keep_cut → 关旁白 → 新 run 逐场帧 == 原片」/ recut 对照腿（丢弃冻结、新床网格重卡、帧确移动）/ pin 道 unreadable 缺失+损坏 × keep_cut+关旁白 四组合拒绝（零版本、原状态不变、marker 清、真 resolve 座）/ provenance 道 draft-vs-unreadable 区分（无 output 行 = 草稿合法冻结呈现时间轴发布成功；spec 损坏 = 拒绝）） |
| `uv run --extra dev python -m pytest tests/ -q`（全量） | **1363 passed in 5.60s**（1359 + 4，零回归） |
| `uv run python scripts/check_gates.py` | **OK** |

**未验证项（本轮新增/延续）**：prompt_gate 与剧本矩阵仍未运行（待授权，付费面；本轮未触 prompt 面——纯执行链 + 测试）；run 级测试仍为 stub 外设 harness（真 run() + 真 build_film_spec + 真 validator；DB/渲染/TTS stub）；keep_cut 的活渲染验收（闸 8 帧腿最终座）仍归剧本矩阵/付费面。

**R2-B 收口判定**：两项复审问题的必验形状全部落码并验证（链式继承用真编辑核 + 真 run/spec 构建；unreadable 用例从真基准恢复座进 patch，非仅 run 层拒绝）。**R2-B 可以收口**；R3 起点不变（见下方「下一轮起点：R3」——首日 MiniMax tool-role 图片 spike，读取座扩展在同座，冻结时间轴语义对 R3 无新增前置）。

## R2-B 复审第三轮补漏（2026-10-20 第四轮评审一项 → 同日收口并验证）

3. **[P2] 冻结版本 Start 后、Output 创建前失败时 provenance 恢复丢冻结切点 — 已修并验证**
   - 复审复现（真 `resolve_film_revision_base`）：run.context 冻结首/末幕 123/177 帧，但无 film Output 行 ⇒ 旧码直接标 `draft`、`film_cut_frames=None`——**无 Output ≠ 没有已确定的时间轴**（「换音乐保持切点 → Start → Output 创建前失败 → 用户继续修改」旅程断链）。
   - **修法**（`storyboard.py` provenance 座 `row is None` 分支）：无 Output 行时先恢复 run.context 已持久化的版本状态——`film_kept_frames` 经 `valid_kept_cut` 对已验证板复核 ⇒ `kept` + 帧继承；**冻结状态损坏或 keep_cut 指令在场却无帧（半写信封）⇒ `unreadable`**（保时间轴编辑结构化拒绝，永不降级普通草稿静默重算）；只有两键皆无的普通版本才按 `draft` 规则。pin 座既有规则不变（Output 在而 spec 不可读 = unreadable）。
   - 回归 ×2：① 必验旅程「原片实跑 → keep_cut 版 Start 的 context（Output 未创建）→ 真 provenance 恢复 → 关旁白（不动时间轴）→ 执行 spec」逐场帧 == 原片，新床网格对照腿证明若重卡必移动；② 三种损坏形态（帧场数不齐 / keep_cut 指令无帧 / 帧低于结构下限）真恢复面直证 `unreadable` + patch 面结构化拒绝（零版本、原状态不变、marker 清）。
   - 变更文件：`app/tools/film/storyboard.py`（provenance 座分支）+ `tests/test_film_edit_wiring_pure.py`（+2 用例）+ DECISIONS.md ADR-137 点 8 来源区分句 + 总设计 §7.2 版本状态段同步。
   - 验证：`test_film_edit_wiring_pure.py` **49 passed**；全量 **1365 passed in 5.48s**（零回归）；`check_gates` **OK**。未验证项不变（prompt_gate / 剧本矩阵待授权，付费面）。


## R2-B 复审漏修项（2026-10-20 第二轮评审发现 → 同日收口）

1. **[P1] keep_cut 初版语义错误（回裸分配帧）— 已修正并验证**
   - 复审复现：base 按旧床网格渲染首/末幕 123/177 帧（板分配 120/180），初版 keep_cut 回 `allocate_frames` = 仍改切点。**正确语义**：keep_cut 消费 base 版本**自身**的时间轴——已执行 → 其 run 产出 spec 的逐场帧（flex 后真值，revision-base 座以 `film_cut_frames` 读入：pinned 座读 Output.render_spec / provenance 座查该 run 的 film output / live-pending 座读 `film_kept_frames`）；未执行草稿 → 其**已呈现计划时间轴**（base 板按 base 床网格 snap——`execution_frames` 同一公式）。**永不回裸分配、永不按新床网格重卡**
   - 链路：patch 拍计算冻结 → 信封 `film_kept_frames`（PendingPlan 读容忍字段；`film_cut_frames` 属性 = base 读取面）→ Start stamping 投影 run.context → run() fail-closed 消费（`valid_kept_cut` 校验缺失/损坏 = 诚实失败）
   - **旁白适配冻结**：keep_cut 下 narration flex 要移动帧即诚实失败（指引缩短台词或 recut）——「保持节奏」覆盖旁白自救
   - **兼容律**：keep_cut 不得与改时间轴 ops 同批（moved/removed/added/retimed 非空 → `keep_cut_incompatible` 结构化拒绝，指引 recut/拆批）
   - 测试（用户要求的形状）：**先生成带实际卡点的原 spec（旧床 snap 移动首/末幕）→ 换新音乐 keep_cut → 新 run 的 spec 逐场帧与原 spec 一致**；草稿 base 走呈现时间轴链；缺 kept cut fail-closed；flex 冻结；对照腿证明新床网格若重卡必移动切点
2. **[P2] j2 PRESENTATION 段编辑拍仍强制追问 — 已修并验证**
   - 「After an EDIT call … then the same ONE question」改为授权分岔（意图在场+hold off → 直接提案；hold on → 一句制作问句；纯审阅 → 呈现即止），与 patch 观察文本同法
   - 一致性测试：gate-on 系统 prompt 与 patch 观察**同断言同一分岔**（两侧无「同一问」、均含 review hold 双支）

## R2-B 审查收尾项（2026-10-20 评审发现 → 修正轮全部收口）

1. **[P1] 编辑入口门控 — 已修并验证**
   - 实施：`ChatTool.wire_view` 钩子（`tool_spec` 每回合应用）+ `_design_storyboard_wire_view`（turn_tools.py 一座）；执行端双路 dispatch 前置拒绝；prompt 两座 builder 传 `film_edits_enabled` 渲染变量；compose 观察 base_ref 铸造行与 `get_output_spec` base_ref 行同闸条件化
   - 测试：wire 双态（schema/描述/$defs GC）/ prompt 双态（两 builder）/ 执行拒绝双路（零副作用断言）/ compose 观察双态 / get_output_spec 双态——6 条新测试；套件 autouse fixture 显式开门（生产默认关）
2. **[P1] keep_cut 执行语义 — 已修并验证（stub/spec 帧数层）；活链路验收归付费面**（语义经复审修正——初版回裸分配帧是错的，正确版见上方「复审漏修项 #1」）
   - 路径：edit `set_music(retime)` → change_set.music.retime（R2-A 法：不进 params/指纹）+ patch 拍冻结 `film_kept_frames` → Start stamping 投影 `film_music_retime` + `film_kept_frames`（service.py）→ `LaunchFilm.run` fail-closed 消费；帧公式一座 `execution_frames`（呈现/执行同骑）
   - **后续验收归属**：实跑渲染旅程（闸 8 帧腿的最终座）= 剧本矩阵/付费面，待授权；~~后续音乐未变的新版本回缺省 allocate+snap~~ **已被复审二轮翻案**——冻结切点升格为版本状态按实际变化继承（见上方「复审第二轮回修」#1，本条以此为准）
3. **[P2] patch 观察文本去冲突 — 已修并验证（双路）**
   - 双路删「then ONE direct question — whether to start」无条件追问；改为授权分岔单法：制作意图在场 + hold off → 继续 propose_tasks/present_plan（dock 复用本版板与参数，确认设置管启动）；hold on → 呈现 + 一句制作问句（明示 yes 是 hold 唯一释放座）；纯审阅拍 → 呈现即止。测试 ×2（双路分岔文案断言）
   - **同类遗留（未修，超本轮范围）**：compose 观察（propose_turn/plan_turn 既有座）同存「ONE direct question」与「hold off 继续提案」双指令张力——系 ADR-129 时代既有法条，非本批引入；已在风险节登记，是否统一归后续评审拍板
4. **[P2] superseded 泄漏本 draft marker — 已修并验证（四座同法）**
   - patch 双路 + **compose 双路**（同形漏洞一并修，丢弃前 `clear_film_draft_marker`——该函数只清本 draft，他人 marker no-op）
   - 测试：patch 并发回防测试补 marker 释放断言（既有 + plan 镜像新）/ compose 双路 superseded 清 marker / 真函数条件测试（自己 marker 清且提交；他人 marker 不动不提交）——原板与新版本不被覆盖由「丢弃在写库前返回」+ pending 字节不动断言锁
5. **[附带项] 画幅文案 — 已修并验证**
   - 工具描述 TARGETED EDITS 段：aspect 修改不再导向 specific_instruction 重设计，改为「诚实暂不支持，永不以重设计兜底」；wire 测试断言旧误导句消失 + 新诚实句在场。首次创建指定画幅（aspect 设计参数 + j2 法条第 8 行）不受影响

## R2-B 修正轮变更文件（在 R2-B 批上叠加，全部未提交）

- `app/config.py`（`film_edits_enabled` 门控字段）
- `app/agents/tool_loop.py`（`ChatTool.wire_view` 钩子 + `tool_spec` 应用座）
- `app/chat/turn_tools.py`（描述拆 base+编辑段常量；wire view + $defs GC；画幅诚实文案）
- `app/chat/propose_turn.py` + `plan_turn.py`（门控拒绝 ×2 / compose base_ref 条件化 ×2 / patch 观察去冲突 ×2 / superseded 清 marker ×4（patch+compose））
- `app/chat/perception/executes.py` + `__init__.py`（base_ref 行门控；描述去 base_ref 命名）
- `app/prompts/chat/_website_film.j2`（编辑法条三处条件渲染）+ `app/chat/prompts.py`（两 builder 传门控变量）
- `app/tools/film/storyboard.py`（`execution_frames` 唯一帧座；`spec_scene_frames`/`valid_kept_cut` 纯座；resolve 三座携带 `film_cut_frames`；`film_design_state` 信封 +`film_kept_frames`；run() keep_cut fail-closed 消费 + narration flex 冻结）
- `app/tools/film/edits.py`（`film_music_retime_of` 投影座；keep_cut 兼容律 + base 切点计算 + `FilmPatchPrepared.kept_frames`；repair echo +`keep_cut_incompatible`）
- `app/models/schemas.py`（PendingPlan +`film_kept_frames` 读容忍 + `film_cut_frames` 读取面属性）
- `app/chat/service.py`（Start stamping + `film_music_retime`/`film_kept_frames`）
- `docs/DECISIONS.md`（ADR-137 + 决策点 7 门控 / 8 keep_cut 消费座——复审后 8 改写为「冻结 base 自身时间轴」语义，Consequences 同步）
- `tests/test_film_edit_wiring_pure.py`（autouse 门控 fixture + 19 新用例；既有并发回防测试补 marker 断言）

## 验证（实际运行，2026-10-20 修正轮，含复审收口）

| 命令 | 结果 |
|---|---|
| `uv run --extra dev python -m pytest tests/test_film_edit_wiring_pure.py -q` | **43 passed**（24 既有 + 19 新：门控 6 / 去冲突 2+一致性 1 / superseded 4 / keep_cut 6——含「原 spec → 换音乐 → 逐场帧一致」执行链与 flex 冻结） |
| `uv run --extra dev python -m pytest tests/ -q`（全量） | **1359 passed in 5.56s**（R2-B 后 1340 + 本轮 19，零回归——门控默认关下全站行为不变） |
| `uv run python scripts/check_gates.py` | **OK**（boot 冒烟在门控默认关下通过；`wire_view` 不改依赖方向） |

## 未验证项（修正轮新增/延续）

- **prompt_gate 未运行（待授权）**：本轮再触 prompt 面（j2 条件化 + turn_tools 描述文案 + perception 描述）——10 探针付费面；门控双态文案对探针的形态影响（默认关 = 探针应完全不见编辑词表）待授权后确认
- **剧本矩阵未运行（待授权）**：S11 家族；keep_cut 的活渲染验收（闸 8 帧腿最终座）与 compose 观察形态（base_ref 行默认关后消失）随剧本座确认
- run() 级测试为 stub 外设 harness（真 run() 函数体 + 真 build_film_spec + 真 validator；DB/渲染外设 stub）——非活链路

## 风险与注意（修正轮新增）

- 门控读 `settings` 单例的运行时属性：系统 prompt 在 import 期渲染（门控状态 = 进程启动态，env 语义正确）；wire view / 执行拒绝 / 读取座为每回合动态读——部署改 env 需重启 API 生效于 prompt 面（wire/执行面即时）
- keep_cut + 旁白内容编辑的组合：冻结窗口下重合成台词超长即**诚实失败**（flex 冻结法）——罕见（validator 台词帽在先）但存在；用户指引 = 缩短台词或允许 recut
- keep_cut 的 base 切点读取面：`film_cut_frames` 有三座来源（pinned Output.render_spec / provenance run 的 film output 查询 / PendingPlan 属性映射 `film_kept_frames`）——provenance 座每次命中多一次 output spec 查询（仅命中候选一次，不在扫描循环内）
- compose 观察的「追问 vs 继续」双指令张力遗留（见收尾项 3）——既有法条，未动
- R2-B 既有风险节全部仍有效（validator 现状带 / warnings 恒空 / 快照 best-effort / pinned 版本号语义 / `_role_pins_for` 行为修复）

## 工作区修改归属

- 本迭代产物**全部未提交**：R1（routes.py 两日志座 + database.py pre_ping + 2 测试文件）+ R2-A（schemas.py / storyboard.py / edits.py 新 / test_film_edits_pure.py 新）+ R2-B（前节清单）+ R2-B 修正轮（前节清单）+ R2-B 复审二轮/三轮回修（本节清单）+ 四份 docs
- 既有无关未跟踪文件不动：`a.json`、`apps/api/scratch/forensics_*.py`

## 下一轮起点：R3（execution.md R3 节）

**R3 准入条件已具备**：R2-B 四项收尾全收口（已修并验证 / 付费面验收归属明确），编辑能力门控默认关（R3 的读取机制扩展不改变该隔离——读图服务于编辑模型，编辑能力仍内部测试）。

1. **首日 = MiniMax tool-role 图片 spike**（实测探针落档；不支持则 synthetic user 消息兜底定型）
2. `get_output_spec` film 分支扩到完整事实表（取景文本/视图引用/候选视图清单）——最小座已就位（版本/逐场 id；base_ref 行随门控），扩展在同座
3. 读工具结果带图机制（预算 ≤12 张 640px + 单张 1280px 按需；超预算显式报错不静默丢图）
4. 纯测试（投影形状/预算帽/超预算报错）+ 真实读图旅程 smoke（人工核验，标未运行则不宣称）
5. 前置软依赖已齐：编辑拍在位且门控隔离（R3 的读图服务于编辑模型的取景/视图修订决策）

## R2-B 完成项（chat 接线 + 版本信封 + 授权 + 报价）

1. **编辑契约入模型可调用面**（`models/schemas.py`）：`DesignStoryboardArgs` + `edits: list[FilmEditOp]` + `base_ref`（均读容忍 null）；schema 层互斥校验器——edits 仅与 base_ref/review_hold 同现，与全部设计参数/specific_instruction/material_urls 混用即拒；**edits 无 base_ref 必拒**（协议牙齿）
2. **base 引用协议四步接线**（双路 `_design_storyboard` 同构，propose_turn.py + plan_turn.py 各增 `_design_storyboard_patch` 座）：
   - a. 铸造：compose 观察文本尾行带本版 `base_ref`（`film_version_identity_digest`）；`get_output_spec` 增 **film 分支**（最小基准读取座：版本/created_via/base_ref/canonical 参数/逐场 `[id] type · 秒数 · 旁白状态`——图片与候选视图清单属 R3）
   - b. 模型随 edits 原样传回（编造引用必不匹配 = 安全失败）
   - c. 执行前**快拒**（无 marker 空转）：base_ref ≠ 当前解析 base 身份 → 拒并指引重读；apply 座内复核同键
   - d. 提交前**并发回防**：`read_committed_film_state`（新座，一次 committed 侧读）查 marker 仍名本草 + live-pending base 的 committed 版本未移动；显式 @output 钉旧版 = 分支语义不做版本回防（钉恒胜，永不静默换最新版）
3. **真实 validator 接入**：`prepare_film_patch`（edits.py 新增 DB-aware 层）——载 `load_storyboard_pages`（空 → `pages_missing` 拒）、`validate_storyboard` 真接（narration_required 随 patch 后 voiceover 标志）、`set_music` 严格门 `resolve_named_film_track`（**命名 ref 自解**，不走 fallback 链——错拼 mood 诚实拒 `music_unavailable`/`music_no_rhythm`）、执行快照以当前页+版本曲目重建（run 期漂移闸对本版世界比对）、指纹以 patch 后参数+birth 叙事计算（**批准 dock 重算同键 → 复用本版板，永不重起草**，测试钉死）
4. **结构化拒绝进 loop**：`FilmEditError` → `film_edit_repair_echo`（unchanged/validation_failed/base_mismatch/结构性拒各有人话指引），清本 draft marker、零版本落库、不退导演重设计、不 500
5. **版本信封落库**：PendingPlan + `film_base_version`/`film_created_via`(compose|patch|variant)/`film_change_set`/`film_constraints_choice`（全读容忍；constraints_choice 写座属 R7 约束分层）；`film_design_state` 增 `created_via`/`change_set` 参数；Start stamping（service.py）与 provenance 恢复（`_film_revision_base_from_state`）携带同键
6. **授权新法落地（ADR-134 修订 + ADR-137 落档 DECISIONS.md）**：`film_design_state` fresh 分支 hold 默认 = `created_via == "compose"`；patch/variant **不新增 hold 且永不代释放 standing hold**（唯一释放座仍是用户明示生产请求）；review_hold 参数双向逃生门不变。闸 15 授权矩阵纯测试 5 条
7. **出生即分配 scene_id**：`assemble_storyboard` 七构造点 `scene_id=scene.key`（slot 骨架 key——open/hero/home/chN_divider/chN_ui/plate/reveal/prove/end）；呈现事实表场头行带 `[id]`；digest 律不变（剥 id 字节兼容，测试钉死）
8. **edit 报价分叉**：`_estimate_facts` 增 `film_quote_facts_from_pending`（pending 带有效版本板 → 实际板秒数 + 实际全量旁白字符，voiceover-off → 0）；`LaunchFilm.estimate` 有 facts 用真值、无则常数不变（既有报价测试全绿）；**interim 不预宣称复用折扣**（全量重合成口径）
9. **能力文案收窄（闸 19）**：`design_storyboard` 注册描述列已实现 5 ops + 「Nothing else exists」否定句（无 insert_scene/set_aspect/voiceover 加法）；`_website_film.j2` 三处法条修订（edits 岔路 + edit 拍呈现 = 变化行非全表 + 批准拍 change words 双通道）——prompt 法合规（现在时现行法、无日期无 ADR 叙事）
10. **既存潜伏崩溃修复（接线实证发现）**：propose_turn `_role_pins_for` 对 dict 形 tasks 属性访问崩溃——chat 路 compose 设计拍盖章前必炸（`tasks=[{"tool":...}]` 字典 vs `t.tool` 属性读，确定性复现）；修为形状容忍读（TaskItem/字典双态），compose+patch 两支同愈

## R2-B 变更文件

- `apps/api/app/models/schemas.py`（DesignStoryboardArgs edits/base_ref + 互斥校验器；PendingPlan 版本信封 4 字段）
- `apps/api/app/tools/film/storyboard.py`（`film_design_state` 授权/信封；`assemble_storyboard` 出生 id；`storyboard_presentation` 场头 `[id]`；`resolve_named_film_track` + `film_snapshot_track` 新座（prepare_dock_storyboard 快照音乐改骑同座）；`read_committed_film_state` 新座；`_film_revision_base_from_state` 信封携带；`LaunchFilm.estimate` 报价分叉）
- `apps/api/app/tools/film/edits.py`（DB-aware 层：`prepare_film_patch` / `FilmPatchPrepared` / `change_set_presentation` / `film_edit_repair_echo`；纯核不动）
- `apps/api/app/chat/propose_turn.py` + `plan_turn.py`（双路 `_design_storyboard_patch` + base_ref 铸造行；propose 另修 `_role_pins_for` 形状容忍）
- `apps/api/app/chat/perception/executes.py` + `__init__.py`（get_output_spec film 分支 + 描述）
- `apps/api/app/chat/service.py`（Start stamping + 信封两键）
- `apps/api/app/pipeline/step_context.py`（`film_quote_facts_from_pending` + `_estimate_facts` 接线）
- `apps/api/app/chat/turn_tools.py` + `prompts/chat/_website_film.j2`（能力文案）
- `docs/DECISIONS.md`（ADR-134 修订 + ADR-137 新增）
- 测试：`tests/test_film_edit_wiring_pure.py`（新，24 用例）+ `test_film_storyboard_pure.py`（出生 id/digest/呈现 3 断言）

## 验证（实际运行，2026-10-20）

| 命令 | 结果 |
|---|---|
| `uv run --extra dev python -m pytest tests/test_film_edit_wiring_pure.py -q` | **24 passed**（stale 拒绝+版本字节不动+零 marker 空转 / 钉旧 Output 分支+信封+指纹平价 / 并发回防丢弃 / unchanged/validation_failed/unknown_scene/music_unavailable 修复回声 / 闸 2 零导演 kill-switch / PlanTurn 平价 / 授权矩阵 5 / 报价分叉 4 / 呈现与回声 / schema 互斥 / get_output_spec film 分支） |
| `uv run --extra dev python -m pytest tests/ -q`（全量） | **1340 passed in 5.67s**（R2-A 后 1315 + 本轮 25，零回归） |
| `uv run python scripts/check_gates.py` | **OK**（edits.py → storyboard.py 单向保持；无反向引入） |

**「核心函数有校验」vs「完整接线已验证」口径**：本轮验证到了**双路 `_design_storyboard` 分支级**——stub DB/marker 座 + 真实编辑核 + 真实 validator + 真实指纹/快照座的集成（非仅纯函数级）。未验证到的是真实 SSE 回合与剧本矩阵（付费面）。

## 未验证项

- **prompt_gate 未运行（待授权）**：本轮触及 prompt 面（`_website_film.j2` + turn_tools/perception 两处 registry 描述）——10 探针需 provider 配额，属付费面
- **剧本矩阵未运行（待授权）**：S11 家族 + 编辑旅程座未跑（活 API + LLM + TTS 配额）；compose 观察文本新增 base_ref 段落的形态影响待剧本座确认
- 真实 chat 回合端到端（SSE/activity 帧/呈现挂号落 message id）未经活链路验证——分支级 stub 集成覆盖到 `_presentation_pending` 挂号
- `get_output_spec` film 分支未经真实 DB 行验证（stub Output + stub resolve）

## 风险与注意（R2-B 新增）

- **编辑走现状 validator**（8..20 场 / 70..118s / REPEATED_VIEW 硬错误等全部现状规则）：删场/压短类编辑可能被现状带拒（`validation_failed` 修复回声，模型可修）——L4 可覆盖是 R7 约束分层才落地，属已知边界非缺陷
- `change_set.warnings` 恒空：warnings 通道随 R7 warning 级（REPEATED_VIEW/PADDING_SCENE 降级）落地
- 音乐未变的 patch 快照 best-effort 重解（设计拍同法）；base 床若在编辑间隙被删 → run 期漂移闸诚实失败（现状法不变，非新增风险）
- pinned 分支版本号跟随钉住 base（v1+1），与既有 pinned-compose 语义一致；live pending 被新版本分支取代是设计内行为
- `_role_pins_for` 修复改变了 chat 路 compose 设计拍的一个确定性崩溃——修复后该路径行为变化（从必炸到可用）；chat 路 compose 设计拍此前在生产是否真实可达未被本轮取证，已在测试锁定新行为

## 工作区修改归属

- 本迭代产物**全部未提交**：R1（routes.py 两日志座 + database.py pre_ping + 2 测试文件）+ R2-A（schemas.py / storyboard.py / edits.py 新 / test_film_edits_pure.py 新）+ R2-B（上述清单）+ 四份 docs
- 既有无关未跟踪文件不动：`a.json`、`apps/api/scratch/forensics_*.py`

## R2-A 完成项（版本/scene ID 契约 + 编辑 ops + 原子应用 + change_set）

1. **scene_id 契约**：7 个场景模型加读容忍 `scene_id: str | None = None`（`models/schemas.py`）；`ensure_scene_ids`（`tools/film/edits.py`）= 已有 id 保留/重复即拒、缺失按位置派生 `s1..`（避让已占用 id）——legacy 板一次性升级路径
2. **digest 律落地**（本轮最重兼容点）：`storyboard_content_digest` 改为剥 `scene_id` 的 canonical dump——**id 是句柄不是内容**，legacy 板 digest 与加字段前字节级一致（测试钉死）；新增 `scene_content_digest`（位置无关场级身份，复用/diff 的键）
3. **ops 契约**（`models/schemas.py`）：`FilmEditOp` 判别联合 = `update_scene`（view/seconds/focuses/narration 显式 null=清除/copy_slots 按场型白名单）/ `reorder_scenes` / `remove_scene` / `set_music(mood,retime)` / `set_voiceover(enabled=False 唯一)`；`set_aspect` 留 R4
4. **原子应用座** `apply_film_edits`（`tools/film/edits.py`）：有序、深拷贝不 mutate 入参、任一拒则整批中止零部分落库；结构校验内置（id/排列/场型重验/正向秒数/no-op 拒），语义校验（接地/时长带/章节实质）经注入式 `validate` callable——真实 `validate_storyboard` 接线在 R2-B
5. **change_set 系统计算**（非 op 回声）：`compute_change_set` 按 scene_id 独立比对场 digest——moved/edited（seconds 不重复计）/added/removed/retimed/music（含 retime 指令）/voiceover/warnings（留空，R2-B 填）；`presentation` 字段随 R4 落（ additive None-default，不预建）
6. **28 条纯测试全绿**，覆盖本轮六条必验：目标版本匹配（`expected_base_digest` 真实校验——内容+参数+场 id 绑定，不匹配在首个 op 前拒）/ id 唯一且重排不变 / 按序原子 / 失败原版字节级不动 / 未触碰场景字节级保持 / 重排动整板 digest 不动场 digest + legacy digest 字节兼容

## R2-A 修正（评审三项 P2，2026-10-20，同日落盘）

评审复现的三个行为问题及修法（无重构、无范围扩张）：

1. **同 mood + recut 误拒 / 往返后 retime 意图丢失**——`set_music` 的 noop 判定改为「同 mood **且** keep_cut」才拒（同曲重卡点是合法修改）；`change_set.music` 发射条件改为「mood 变化 **或** 存在存活 recut 指令」，mood 往返归零但 recut 存活时如实上报（mood_before=mood_after+retime=recut）
2. **目标版本匹配原为空转**（原测试只证「传 v2 返回 v2 digest」）——新增 `film_version_identity_digest(board, params)`（内容 digest + canonical params + 有序 scene_id 绑定）与 `apply_film_edits(expected_base_digest=...)`：不匹配在首个 op 前以 `base_mismatch` 拒。R2-A 初版汇报的「目标版本匹配已通过」为过度宣称，以此修正为准。**接线口径再修正（第三轮评审）**：expected 必须是**读取时刻**服务端铸造的引用（模型原样传回），禁用刚解析 base 现算（自比较恒匹配）——四步协议与并发回防见下方 R2-B 起点 2 与总设计 §7.2「base 引用协议」
3. **无变化批次仍返回成功**——整批应用完成后统一判变（内容 digest + canonical params + 存活 timing 意图三者皆无变 → `unchanged` 拒）：空 update、同序 reorder、改了又改回、mood 往返无 recut 全部拒绝；不创建无意义版本/任务

新增边界测试 6 条（同曲重卡点成功 / 往返 recut 存活 / 空 update 拒 / 同序 reorder 拒 / 改后改回拒 / 往返无 recut 拒）+ 目标版本匹配测试重写为四情形（匹配通过/内容漂移拒/参数漂移拒/场 id 绑定漂移拒）。

4. **命名分家（第三轮评审非阻塞项，已落）**：`FilmEditResult.base_digest` → `base_identity_digest`（身份摘要：内容+参数+场 id 绑定），`result_digest` → `result_content_digest`（内容摘要：ADR-129 呈现/执行链真值）——两种 digest 从此不可被误当作同类比较。

## R2-A 变更文件

- `apps/api/app/models/schemas.py`（7 场景类 +scene_id；ops/change_set 契约模型块，位于 FilmStoryboard 与 FilmProvenance 之间）
- `apps/api/app/tools/film/storyboard.py`（`_scene_content_dump` + `scene_content_digest` 新增；`storyboard_content_digest` 剥 id；`TypeAdapter` 入 import）
- `apps/api/app/tools/film/edits.py`（新，编辑核心）
- `apps/api/tests/test_film_edits_pure.py`（新，22 用例）

## R2-A 实现级决定（已落码，非新设计）

- op 字段命名 `copy_slots`（`copy` 撞 BaseModel 弃用方法触发 shadow 警告——命名纪律改wire名，总设计表格只说「文案槽」未钉 wire 名）
- no-op op（同 mood/已关配音）显式 `noop` 拒绝，不静默通过
- `set_music` 的 `retime` 是执行指令不进 params（指纹不染）；经 change_set.music 传递，持久化座位 R2-B 定
- narration 显式 null = 清除（`model_fields_set` 区分缺席/显式 null）
- 版本信封组装（created_via/change_set 落 `film_design_state`）属 R2-B 接线，本轮只到契约 + 核心

## 验证（实际运行，2026-10-20）

| 命令 | 结果 |
|---|---|
| `uv run --extra dev python -m pytest tests/test_film_edits_pure.py -q` | **28 passed**（零警告） |
| `uv run --extra dev python -m pytest tests/ -q`（全量） | **1315 passed in 5.45s**（1287 既有 + 28 编辑核心，零回归） |
| `uv run python scripts/check_gates.py` | **OK**（依赖方向：edits.py → storyboard.py digest 座，无反向） |

未触 prompt 面 / web / render / 旅程 → prompt_gate、tsc、剧本矩阵不适用（剧本矩阵属付费面另行授权）。

## 未验证项

- 编辑核心对**真实 `validate_storyboard`** 的接线未做（R2-B；本轮以注入 stub 证明原子拒绝语义）
- ops 未经真实 chat 回合驱动（R2-B 接线后；付费面旅程待授权）
- R1 无遗留未验证项

## 风险与注意

- 新字段 `scene_id` 会出现在**新落库**的 board JSON 里（None 或实值）——digest 已免疫，但消费 board JSON 的其它座位（render spec 烘焙/presentation）若有 strict schema 需注意；全量测试绿表明现状消费面兼容
- Pyright IDE 诊断（venv 未解析 + 联合类型语法误报）是环境噪音，非本轮引入

## 工作区修改归属

- 本迭代产物**全部未提交**：R1（routes.py 两日志座 + database.py pre_ping + 2 测试文件）+ R2-A（schemas.py / storyboard.py / edits.py 新 / test_film_edits_pure.py 新）+ 四份 docs（orchestration / execution / handoff / progress）
- 既有无关未跟踪文件不动：`a.json`、`apps/api/scratch/forensics_*.py`

## 下一轮起点：R2-B（execution.md R2 节 ⑤-⑦ + 接线）

入口清单：
1. `DesignStoryboardArgs` 加 `edits: list[FilmEditOp] | None`（schemas.py；此刻才开放模型可调用面——同步能力文案收窄闸 19）
2. `_design_storyboard` 双路（`chat/propose_turn.py:606-818` / `plan_turn.py:830-1049`）增 edits 分支，**base 引用协议四步**（接线律；禁止「刚解析 base 现算 expected」的自比较接法）：
   - a. 读取座（`get_output_spec` film 分支/呈现响应）返回当前版本的 `base_ref = film_version_identity_digest(board, params)`，服务端记录该读取绑定；
   - b. 模型随 `edits` 原样传回 `base_ref`（编造/过期引用执行时必不匹配 = 安全失败）；显式 @output 钉旧 Output = 以该版本为 base 的分支语义，按既定版本策略处理，**永不静默换最新版**；
   - c. 执行：`apply_film_edits(expected_base_digest=<读取时记录的 ref>, validate=真实 validate_storyboard 适配)`，当前 base 不符 → `base_mismatch` 拒并提示重读；
   - d. 提交新版本（`film_design_state` 落 `created_via="patch"`/`change_set` 读容忍字段）前再复核当前版本仍 == 读取基准（并发回防），通过才提交 → 呈现 change_set（仅变化行）；
   - e. 必带集成测试：「读取 v1 → 当前版本更新为 v2 → 提交基于 v1 的 ops」→ 拒绝且 v2 字节级不动。
3. ADR-134 修订落地（edit/variant 不新增 hold）+ DECISIONS 落档 + 授权回归测试（闸 15）
4. edit 报价分叉（实际板秒数 + interim 全量 tts_chars）+ 闸 2（edit 零导演调用）断言
5. 出生即分配 scene_id（slot 模式骨架 key/compose 兜底）接入 `assemble_storyboard`/`prepare_dock_storyboard`——此后新板自带 id
6. 拆分预案若再需细切：先 1+2+5（链路通）再 3+4（授权+报价）
