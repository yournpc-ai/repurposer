# Film 编排与持续修改——施工设计 v3.1

> Status: 施工待授权（v3.1 定点收口：字段级修复覆盖 schema 字段层 / 结算边界保持单体语义 / 旁白并发缓存原子化 / launch_film 注册兼容方案 / 契约矛盾清理）。未施工；未实际运行的检查逐项标注「未运行」。
> 范围纪律：保持 SaaS/App 路径可用；不建通用插件平台/依赖引擎/第三方脚本环境；不开放模型执行任意渲染代码；不删事实校验或必要执行约束；不擅自付费生成/部署/改生产数据。
> 产品模型（拍板基准）：agent 读素材与当前作品 → 理解需求 → 自主选择组合工具 → 创作或修改 → 读工具结果 → 检查并必要时修正。首次创作与交付后修改同此一模型。模型负责创作决策；工具表达修改；代码保证执行正确性。

## 0. 一句话

分镜成为有稳定场景身份、可被结构化编辑的作品版本；执行拆成少量真实宏阶段（准备执行 → 准备旁白 → 装配 → 渲染）；校验失败走字段级有界修复而非全稿重生成；配方约束降为指导层，创作空间还给模型。

## 1. 现状链路与代码位置（取证，v2 保留）

链路全量接线、无占位主链：`apps/api/app/tools/film/storyboard.py`（4125 行）是编排唯一座。

| 阶段 | 实现 | 位置 |
|---|---|---|
| Chat 意图 | `_website_film.j2` 三段式法条；无代码级意图特判 | `app/prompts/chat/_website_film.j2`；`chat_intent_system.j2:50` / `intent_router_system.j2:72` |
| 设计拍 | `design_storyboard` 非终态工具，双路镜像 | `app/chat/turn_tools.py:53-73`；`plan_turn.py:830-1049` / `propose_turn.py:606-818` |
| 素材读取 | playwright 逐 section 采集 + 元素清单 + 子页发现；**模型只看 fold 截图，section shots 从不作图喂模型** | `tools/research/capture.py:1130`；`page_media_inputs` `storyboard.py:2370-2384` |
| 分镜生成 | 代码骨架 + 模型填槽（ADR-127）：`_scene_plan`/`_assign_seconds`/`_pick_focus` 代码定结构；LLM 答 `FilmDirection` 槽位 | `storyboard.py:407-717`；`prompts/film_director.j2`；`skills/launch-film/SKILL.md` |
| 校验 | 引用层接地 by construction + 时长带/字数帽 + 质量闸；有界打回 1+2 候选；预算 1800s；预检 `_MIN_VIEWS=4` | `validate_storyboard` 1114-1469；`orchestrate_storyboard` 2387-2510 |
| 方案与授权 | 版本化 PendingPlan + digest 链 + review hold + Start 门三连 | `film_design_state` 2794+；`resolve_film_dock_state` 3030+；`lifecycle.py:345-432` |
| 执行 | `LaunchFilm` 单体节点：消费出生快照 → 帧分配 → 计费 → 音乐 → Output → 配音合成 → spec → 渲染入队 | `storyboard.py:3674-4125` |
| 配音 | 逐幕 T2A + 适配阶梯 + 零和借帧（ADR-136）；**音频按 output_id+index 存，跨版本不可复用** | `tools/film/narration.py`；`_save_narration` 92-101 |
| 配乐/字幕 | 音乐库复用 + beat snap；字幕 = 旁白 cue 投影烧录（非 ASR，合理分化） | `resolve_film_music` 3505+；`narration_caption_cues` 1643+ |
| 渲染 | film-spec 第二家族；渲染器黑盒；render mirror 是可见性+成本家 | `apps/render/src/film/schema.ts`；`pipeline/render_ownership.py:186` |
| 质量 | render_probe 容器级闸；Layer-4 画面内容验证不存在 | `pipeline/render_probe.py` |
| 计费 | hold→capture→release；**失败步骤只在步骤行记账（observability），永不 capture 钱包**（`billing.py:277-296` 注释与分支实证）；release = hold−Σcapture 钳 0 | `platform/billing.py:255-341` |
| 作品身份 | `Output.work_id` 已有（ADR-091） | `models/tables.py:612-618` |

**chat loop 是纯文本通道**（`agents/base.py:286-291` 注释实证：streaming 形态保持 plain-string，从不带 media parts）——编辑模型看图需要新机制（§7.2 读取座）。

**历史/占位/漂移清单**：`end.logo_url` 恒 None；theme `accent/accent2` 未渲染；`FilmSceneUi` 旧 captions 字段残留；`_scene_plan` docstring 与 `_MIN_VIEWS=4` 注释漂移；`on_row_append` 零调用点（需求池 P1）。

## 2. 决策权对照（取证，v2 保留）

| 决策 | 原版 skill | 产品 pre-127 | 当前（post-127） |
|---|---|---|---|
| 场景类型词汇 | 封闭 7 类 | 封闭 7 类 | 封闭 7 类（不变） |
| 场景顺序/数量 | **模型**（硬约束仅 hero≥1/end 末位/plate≤2/总带，validate.mjs:52-58） | **模型** | **代码固定弧** |
| 每场时长 | **模型选 beats 枚举** | **模型给 seconds** | **代码派生** |
| 选图 | **模型枚举选图+看图**（plan.mjs:68,146-152） | **模型选 page/shot** | **代码按序消费**，模型只见 fold 图 |
| 相机目标 | **模型点名元素+zoom+到达拍**，几何校验 | 模型给 focuses | **代码选最大未遮挡元素**，单 focus |
| 文案 | 模型写+接地校验 | 引用行 ID（更强） | 引用行 ID（不变） |
| 构图/布局/路径插值 | 代码 | 代码 | 代码（永不归模型） |
| 配音 | 无 | 模型逐幕旁白 | 模型逐幕旁白（增强，保留） |
| 修订 | 改 storyboard.json 重渲染 | 对话修订 | 对话全量重稿 + 版本闭环 |

## 3. 根因（首次编排侧，v2 保留）

ADR-127 治的病是传输形态（非流式全有或全无 + 盲重试烧腹稿）；流式传输（同批④）已独立治愈该病，骨架收归代码是搭车过度矫正。代价：盲选图/盲相机、单弧、一刀切时长。pre-127 的 `DraftStoryboard`（git `975a9a2^`）已是引用层紧凑形态，复活它是现代化而非新发明。

## 4. 真实事故取证：14fa16b6「再来个1:1」（v2 保留，结论不变）

时间线（/tmp/rep-api.log 2026-10-19 01:42:45–01:47:52 + 本地库只读查询）：首片 89s/15 幕/9:16 交付（run `c309ea72`）→ 交付消息主动建议 1:1 → 用户「再来个1:1方形的」→ `propose_tasks` 被守卫拒（`no_board/no_version_params`，Start 后 pending 已清）→ 引导「重呈现当前分镜不要重设计」→ v1 基准从 run provenance **恢复成功** → 模型携带 `aspect="1:1"`（用户真实请求），但 aspect 焊在内容指纹里（`canonical_film_params` 2684-2698）→ reuse 被拒 → **实际走了导演重设计**（两候选烧 106s+154.8s）→ 导演重写未被要求修改的旁白致两幕超帽打回 → 第二候选完成同秒回合落 "Internal server error"（`turn_failed`），无第二 run，pending 无设计状态。

**根因分层**：① 旁白校验失败 ≠ 500 根因（在有界打回内正常处理，第二候选已完成）；② 最终异常无堆栈可考——SSE 回合异常座（`routes.py:652`）只做用户文案映射从不记 logger 堆栈，**日志缺口本身是待修项**；同窗口无关 GET 500 = `InterfaceError: connection is closed`，engine 无 `pool_pre_ping`/`pool_recycle`（`models/database.py:12-16`）；两个候选根因（落库撞闭连接 / 装配抛无 user_key 异常）无法字节级确证——此结论保留，不升级。③ 结构洞：无「同内容变画幅」概念，参数变化只能走重设计。④ 交付建议承诺了系统做不到的形态。

## 5. 原子能力复用边界（v2 保留 + 补充）

复用不动：音乐库/beat 网格、对象存储、统一渲染链、计费三件套、版本/digest/授权闭环、persona voice、work_id、修订基准恢复链。合理分化不合并：字幕双轨；film 无编辑器面（本方案用结构化 op 补强，不搬 clip 编辑器）。

真实缺口补齐：① 编辑/导演模型的视觉输入；② 旁白跨版本复用依据；③ 画幅变体概念；④ 局部修改路径；⑤ SSE 回合异常堆栈日志；⑥ 连接池活性检查；⑦ 执行单体内部的阶段持久化（失败后恢复不重做有效工作）。

## 6. 相对 v2 的关键变化（被替代方案已删）

1. **执行单体拆成宏阶段**：`LaunchFilm.run` 的单体逻辑拆出三个内部阶段（准备执行/准备旁白/装配）+ 沿用既有 render 镜像，注册节点形态不动（§9.6 最小兼容），每阶段真实持久化 + 独立失败与重试语义（§9）。v2 的「执行零改动」作废。
2. **字段级有界修复取代整候选重滚**：可解析候选保留为修复基准，校验回声带 scene_id/字段路径/错误类型/实际值/约束，模型只返修正字段，系统合入后重查受影响约束 + 整体一致性（§8）。v2 未覆盖此层。
3. **约束分层松绑到「agent 创作选择」**：配方默认值（时长带/幕数/弧）不仅用户明确要求可覆盖，**agent 基于素材与目标的创作选择也可覆盖，在方案中呈现即可**（§7.3）。删除「30s 无用户明确要求就拒绝」类验收。旁白字符/秒降为估计规则，执行真值 = 实际合成时长。
4. **编辑模型必须能看图**：chat loop 增图片携带机制（读工具结果带压缩图，预算帽内；超预算显式报错不静默丢图）——v2 只说「编辑模型读文字清单」，不够（§7.2）。
5. **授权法则应用产品新决定**：明确修改请求 + 设置允许 = 呈现变更摘要后可继续执行，不因「这是新版本」自动加确认；ADR-134 修订写法见 §11。v2 的「变体/编辑 hold 默认 ON」作废。
6. **旁白复用按实际变化推导，不按 op 名**；原始音频与速度适配结果分开存；并发/失败/文件丢失/清理最小实现写明（§10.1）。旧作品走「按需收割 + 可验证才复用」，不全库迁移（§10.2）。
7. **批次重排**：G0 事故修复 → G1 状态契约+编辑+变体 → G2 宏阶段拆分 → G3 编排恢复+字段级修复 → G4 验收。核心 ≈ 11 个工作日（估时见 §13）。

**v3.1 定点收口（施工前修正，不扩展范围）**：① 字段级修复覆盖 schema 字段层（JSON 可解析但字段不合法 → 同一定点通道；仅 JSON 不可解析才有界整篇重生成），全局调用预算与无进展判据明确（§8.2）；② 结算边界保持单体语义——capture 单座 = assemble，prepare/narrate 只 meter 不 capture，注入矩阵验收（§9.2/§10.3/闸 14）；③ 旁白并发缓存原子化（原子占位/有界接管/owner 双条件校验/过期不得覆盖，禁止后到覆盖；速度适配 staging 恢复语义写明）（§10.1/闸 16）；④ launch_film 注册兼容最小方案（注册 kind 不动 + 编译期展开，兼容点列早期验证）（§9.6/闸 17）；⑤ 契约矛盾清理（EMPTY_CHAPTER 实质形态不限 web walk、旁白帽 warning/repair 统一为修复通道、组合 op 示例去矛盾、零重合成断言限定可适配数据、审阅轴 vs 最终轴分层、删除未证实的 DB 因果表述）（§7.3/§8.2/§9.3/§12/闸 7/8/18）。

## 7. 状态与工具契约

### 7.1 作品 / 版本 / 场景身份

- **Work**（`work_id`，已有）：作品物理身份；版本与产物挂其下；原版本产物永不改写。
- **Storyboard version**：`{version, base_version, created_via: compose|patch|variant, change_set, content_params{focus,language,voiceover,music_mood}, constraints_choice, scenes[带稳定 scene_id], content_digest, execution_snapshot}`。存储座位不变（活设计 = pending_brief；执行血缘 = run.context；恢复 = `resolve_film_revision_base`），**不新增版本表**（寻址需求已被恢复链覆盖；版本浏览 UI 出现时再立）。
- **scene_id**：出生即分配（compose 时模型给语义 slug 或代码兜底 `s1..sN`；slot 模式用骨架 key）；**重排不改变 id**；legacy 板读容忍（无 id → 位置派生，下次 patch 一次性升级）。
- **digest 两级**：整板 content_digest = 全板 canonical dump（含顺序——重排是有意义变化，digest 应变，`storyboard_content_digest` 2728-2748 的 list 序敏感已满足）；**场级 digest**（新增）= 单场 canonical dump 的 hash，与位置无关——复用与 diff 的身份。
- **参数两分**：内容参数（focus/language/voiceover/music_mood → 指纹）；**aspect 出内容指纹**，成为 run 级呈现参数。参数 delta 分类 = canonical 集合确定性比对：纯呈现 delta = 变体；内容 delta = 修订。**意图来源是模型的显式 op，路由不反推**；分类器只作守卫与旧行兼容。
- **变体**：同内容版本 + aspect override → 新 run → 新 Output（同 work_id）；provenance 携带 storyboard_digest + aspect + 取景调整记录。

### 7.2 工具契约

**`design_storyboard`（唯一创作/修改入口，不新增 chat 工具）**增两互斥形：

```
edits: list[FilmEditOp] | null   # patch 路径：对 base 版本的结构化编辑
# edits 空 = compose 路径（首稿；或带 specific_instruction 的开放重编排）
requirements: {total_seconds?: [min,max], scene_count?: [min,max]} | null  # 仅用户明确点名时钉
# 新增可选钉：base_output_id（@output 提及已支持）→ 确定性解析 base 版本+digest
```

**FilmEditOp（本期六个：update_scene / reorder_scenes / remove_scene / set_music / set_aspect / set_voiceover(false)；insert_scene 暂缓——compose 可增删场景）**：

| op | 字段 | 校验 | 失效推导（按实际变化，不按 op 名） |
|---|---|---|---|
| `update_scene` | scene id；view{frame?}/frame/seconds/focuses/narration/文案槽 | 视图存在；focus 元素法（换图后原 focus 元素不存在 = 字段级拒）；秒数下限；文案接地；旁白估计帽 | 场 digest 变 → 该场旁白重合成（仅当 narration 文本变）；seconds 变 → 时序重算；**改时长不改旁白文本 = 音频复用，只查窗口适配** |
| `reorder_scenes` | order: [ids] | 全集不重不漏；EMPTY_CHAPTER 按新序重查 | 场 digest 全不变 → 旁白音频文件复用，**但逐场重查窗口适配**（新位置新邻接）；时序重算重 snap |
| `remove_scene` | scene id | 删后结构合法性（hero/end 配方指导 + L1 不下沉） | 同上 |
| `set_music` | mood；`retime: keep_cut \| recut` | 曲目可解；时长够；节拍网格可得 | keep_cut：帧不动（呈现诚实：切点不压新节拍）；recut：边界重 snap + reveal onset 重压 + **已有音频逐场重查窗口**；音频本体复用 |
| `set_aspect` | 16:9/1:1/9:16 | 逐幕取景重查（代码解几何，调整入 change_set） | 内容零变 → 音频/音乐全复用；仅渲染重跑 |

`set_voiceover`：本期只实现 `false`（关配音 = 删旁白承诺，纯减法）；`true`（补配音）需逐幕旁白创作，走 compose 路径——工具描述、G1/G3 批次、§14 验收同此口径。

**应用语义（系统座）**：ops 有序、原子应用于 base 版本的内存拷贝 → 有效约束校验 → **成功才提交新版本（version+1），失败保留原有可用版本**（零部分落库）。未触碰场景字节级不变由构造保证（系统应用，非模型照抄）。compose 路径的保留核验**不依赖模型自报 kept/changed 自洽**：系统按 scene_id 独立比对场级 digest，kept 集合外的实际变化全部进 change_set 呈现（用户「其他内容不变」类要求由系统核验背书）。整批应用完成后统一判变（内容/参数/存活执行意图三者皆无变 = `unchanged` 拒，不创建无意义版本与制作任务——op 前后可抵消，故只在最后判）。

**base 引用协议（目标版本匹配的接线律）**：`expected_base_digest` 是**读取时刻**服务端铸造并记录的基准引用（读取座呈现当前版本时随响应返回 `film_version_identity_digest`，模型随 edits 原样传回；编造/过期引用在执行时必不匹配 = 安全失败，故「不信模型自报」= 不接受模型编造的基准，而非执行时重算一个恒匹配的期望值）。执行时核对当前解析 base 与该引用一致才应用；提交新版本前再复核一次（并发回防：检查后版本被更新 = 拒绝并提示重读）。**禁止用刚解析出的 base 现算期望值**（自比较恒匹配，防不了过期编辑）。显式 @output 钉旧版本 = 以该版本为 base 的分支语义，按其既定版本策略处理，永不静默换成最新版。

**change_set**（四类变化分列）：`moved`（id+from+to）/ `edited`（id+字段清单）/ `added`/`removed` / `retimed`（id+秒数 delta）/ `presentation`（aspect+取景调整）/ `music` / `warnings`。呈现只带变化行——用户不重读整份分镜。

**冻结时间轴 = 版本状态**（失效推导的同一法则延伸到执行面）：已确定的切点（已执行版本的 spec 逐场帧 / 草稿版本的冻结帧）随版本**继承**——任何不动时间轴的批次（无 moved/removed/added/retimed、无存活 recut）继承 base 的切点，不因本轮是否出现 `set_music` 而丢失；结构变化或存活 recut 合法丢弃，run 重新 allocate+snap。基准恢复链路携带切点来源（`film_cut_state` = spec/kept/draft/unreadable）：`kept` 也包括 Start 投影进 `run.context` 的冻结切点——**run 在 Output 创建前失败不丢冻结状态**（无 Output ≠ 普通草稿）；只有确无冻结状态的普通版本才按 draft 规则用其可信的已呈现计划时间轴；**已执行作品 spec 缺失/损坏、或冻结状态损坏/keep_cut 指令无帧 = 实际切点不可恢复，保时间轴的编辑结构化拒绝（`base_cut_unreadable`，指引重读或显式 recut）——永不静默重算冒充原片**。run 消费门 = `film_kept_frames` 在场即 fail-closed 消费（keep_cut 指令无帧 = 半写信封同罪），旁白 flex 同门冻结。

**读取座（编辑模型的眼睛，§六的落地）**：
- `get_output_spec` film 分支：当前版本事实（版本/digest 前缀/scene_id/类型/秒数/帧数/视图引用/取景文本/旁白状态/音乐/画幅）+ 时间轴来源标注（已执行 spec 帧 / 冻结 kept 帧 / 计划轴——计划值永不标成已执行值 / 不可恢复点名）+ 候选视图清单（page·shot·heading·used-by 场景映射·asset id）。页面座 = `load_storyboard_pages`（与编辑校验同座，(page,shot) 引用同义）；fold-only 页（pre-B1）如实退化为仅 fold。
- **图片携带机制（新）**：读工具结果可带压缩图（`ToolObservation.images` → loop 的 role:tool 消息投影为 content parts）。机制选项 A = tool 消息带 image parts（**本地代码与请求形状已验证；MiniMax tool-role 图片的供应商支持待 spike**）；选项 B（兜底）= 工具返回后追加一条带图 synthetic user 消息（与导演 media inputs 同构，已验证形态——仅当 spike 阴性才启用）。预算：每次 ≤12 张 ~640px 缩略图；`views` 选择子（page/shot 对）点名读取，恰好一张 = 1280px 高清；超预算显式报错（零图片 + 补救路径），**不静默丢图**；缺图/未存图/读取失败三类分述。图片与候选清单随编辑能力门控同闸（默认关 = wire 零变化）。chat loop max_iterations=12（`intent.py:325`）容纳「读图→改→再改」。**图片范围 = 素材截图**（页面采集 shots / 用户上传素材）；已交付成片的逐帧自动检查不在本期，成片视觉验收为人工（§14）。

### 7.3 约束四层（v3 修订版）

| 层 | 内容 | 违反后果 |
|---|---|---|
| L1 执行/安全硬约束 | 事实文案引用可解析且接地；focus 元素存在于所指视图且未遮挡、永不裸坐标；fps=30；FILM_MAX_FRAMES=3600 帧帽；每幕结构下限帧（渲染器行为法）；音频流承诺；配音承诺 fail-closed（NARRATION_MISSING） | 硬错误 |
| L2 渲染表达限制 | 7 场景型 / 相机 walk 模板 / plate 2..4 卡 / backdrop 枚举 / 字幕 cue 烧录 / 硬切转场 | 硬错误（改 = 渲染施工，本期不动） |
| L3 用户明确要求 | 时长目标/画幅/语言/静音/保留范围——结构化钉入 brief | 覆盖 L4 |
| L4 配方默认值 | 弧配方；总时长 70-118s；幕数 8-20；per-type 秒带；plate≤2 | **agent 创作选择可覆盖**（基于素材与目标判断，在方案中呈现所选）；用户未指定时 agent 自主选合理结构；**不得把 agent 选择标为用户要求**——版本记录 `constraints_choice.source: user|agent|default` |
| 质量提醒（从硬错误降级） | REPEATED_VIEW（同图同呈现——有意呼应合法）；PADDING_SCENE | warning：不打回，随呈现如实列出 |
| 保持硬错误 | EMPTY_CHAPTER（章节卡后无**实质内容** = 影片自身结构说谎；实质 = ui walk 或 plate 等现有场景型，不把网页 walk 固定为唯一章节内容，新场景型问世时同席重估） | 硬错误 |
| 最少素材数重构 | 废弃全局 `_MIN_VIEWS=4`；改 = 引用合法性（ui 场所指 (page,shot) 必须存在，L1）+ 零可用视图不烧 LLM 的诚实预检 + 素材单薄 warning | 分层 |
| 旁白帽（语义统一） | 字符/秒 = **估计规则**：设计期超出 = 字段级修复项（与硬违例同一 repair 通道，§8.2——修复成本在字段级机制下为秒级，不发明独立 warning 通道）；执行真值 = 实际合成时长（ADR-136 阶梯+弹性；装不下 = 诚实失败点名场景）。估计阈值不是物理规律，但同一语义贯穿 compose 与 edit | 设计期字段级修复；执行期硬 |

### 7.4 兜底边界（不变，重申）

`fixed_direction` 仅 worker 无人值守道且仅首次生成；修订/变体/设计旅程永不兜底——失败 = 诚实拒绝，当前已呈现版本保持；生产 run 只执行被引用版本、漂移即停；永不静默修剪文案/替换素材/换固定骨架冒充成功。

## 8. 校验失败与有界修复

### 8.1 现行重试链审计（逐项实证）

| 层 | 次数/预算 | 嵌套关系 | 是否丢弃已有候选 | 依据 |
|---|---|---|---|---|
| provider/transport | tenacity 3 次，指数退避 2-10s；流式只在首 delta 前重试 | 最内层 | — | `minimax.py:423-424,544,717-719` |
| schema 解析 | 每次 agent 调用 1 轮修复（结构化回声） | 套在 transport 外 | 是（同 prompt+回声重新生成整篇） | `agents/base.py:267-284` |
| 多模态降级 | 声明式 1 次纯文本重试（film_director 已声明） | 同上 | 是 | `agents/base.py:155-158,344-358` |
| 语义校验（导演 repair） | 1+2 候选，总预算 1800s | 套在 agent 调用外 | **是——每候选整篇重新生成，回声只带违例文本不带前候选内容** | `orchestrate_storyboard` 2444-2471 |
| chat tool loop | max_iterations=12（trigger 6） | 最外层（回合） | 守卫拒绝消耗迭代 | `chat/intent.py:325,361` |
| worker 节点 | LaunchFilm retries=0；TransientNodeError 预算 = node.retries | run 层 | — | `storyboard.py:3689`；`orchestrator.py:1531` |
| render | render_max_attempts=3（poison-pill 边界：cap 内可认领，越界终态）；render_concurrency=2；timeout 900s | 渲染链 | — | `config.py:77-89`；`jobs.py:37-43,272` |

最坏嵌套：3 候选 ×（1+1 schema 修复）= 6 次生成 × transport 3 = 18 次传输执行，同烧一个 1800s 预算。**无无限重试**；问题在候选级整篇丢弃——一个字段失败 = 全稿重生成（事故中 scene[2] 旁白超帽 → 整篇重出实证）。

### 8.2 字段级有界修复（v3 核心机制）

compose 路径的 `orchestrate_storyboard` 改为**保留候选 + 定点修复**：

1. 模型只填判断字段；帧数/几何/cue 时间/URL 全代码派生（现状已满足，不动）。
2. 调用前可行性预检（零可用视图不烧 LLM——保留）。
3. **可解析候选保留**：未通过校验的版本永不发布为执行版本（现状已满足：只在通过时落库）；未通过的内容作为修复基准持有。
4. **两层失败都进字段级通道**（不只覆盖 schema 通过后的语义错误）：
   - JSON 可解析但个别字段不合法（pydantic `ValidationError`，`errors()` 的 `loc` 可映射 scene_id/字段路径）→ 升级为结构化违例，走同一定点修复——**不整篇重滚**；
   - JSON 不可解析（候选不可用）→ 有界整篇重生成（≤1 次，共享同一预算）；
   - 语义校验违例 → 定点修复（现状机制升级）。
5. **结构化违例回声**：每违例带 scene_id + 字段路径 + 错误类型 + 实际值 + 约束（`FilmViolation` 增 `scene_id`/`field`/`actual`/`bound` 字段——现 detail 是自由文本，升级为结构化+人话双载；schema 层 `loc` 映射同一形状）。
6. **定点修复调用**：模型只返修正字段（`repairs: [{scene_id, field, value}]`，小输出），系统确定性合入保留候选 → **重查受影响约束 + 整体一致性** → 过则发布。整候选重新生成只在候选不可解析或整体结构不可用（如视图引用大面积失效）时允许——仍有界。
7. **全局调用预算（明确）**：设计回合一个预算座——总墙钟 1800s（现状不变）+ **总 LLM 生成调用硬上限 = 10 次**（= 初稿 1 + 定点修复 ≤4 轮 + 每次生成随附的 schema 层修复 ≤1 + 整篇重生成 ≤1 的算术上界 1+4+5=10）；所有层共享同一计数，**嵌套层（schema 修复/多模态降级）不得刷新或新设计数**，外层守卫拒绝 / chat loop 迭代不重置该预算；超限即停止并诚实失败。
8. **无进展判据（不仅凭错误数量）**：违例签名 = (scene_id, field, code)；① 同一签名连续两轮复现；② 合入后签名集两轮无变化；③ 一轮修复引入的新违例多于修掉的（倒退）——任一命中即停止并诚实失败（带上当前违例集）。
9. **错误分类**：模型可修复（schema 字段/语义违例）→ 定点修复；输入缺口（素材不足/页面不可读）→ 诚实告知要素材；系统错误（DB/网络/provider 非 schema 类）→ **永不进导演修复通道**——transport 归 tenacity，DB/装配异常直接冒泡为系统失败。（事故里导演两轮白烧由参数路由缺陷致，非 DB 异常——此处只立「系统错误不进文案修复」之法，不追加未证实的因果。）

edit 路径无需此循环：ops 拒纯以结构化错误回 chat loop（同字段形状），模型在回合迭代内修复重调。

### 8.3 修复实例（一个字段失败的完整旅程）

素材：三页采集。首候选 12 幕通过 schema；validator 报两违例：

```
- scene[s4].narration: 125 speech units over the ~104 estimate cap for a 8.0s window（估计帽——字段级可修复违例）
- scene[s7].focuses[0].element: "s2e99" not in view (page=1, shot=2) 的元素清单（硬错误）
```

旧路径：整篇重生成（125 个字段全重摇）。新路径：

1. 候选保留（未发布）。
2. 修复调用只带两违例 + 相关场景的现状字段 + s7 所指视图的有效元素清单；模型返回：
   `repairs: [{scene_id:"s4", field:"narration", value:"更短的新句"}, {scene_id:"s7", field:"focuses", value:[{at:2.0, element:"s2e4", intent:"feature"}]}]`
3. 系统合入 → 重查：s4 旁白帽（过）、s7 focus 元素法（过）→ 整体一致性（总时长带/重复视图/章节完整）→ 过 → 发布为新版本。
4. 其余 10 幕字节级未动（合入是系统行为）。墙钟：修复调用只输出两行修正 ≈ 秒级，而非整篇 100s+。

## 9. 宏执行阶段

### 9.1 为什么是节点边界而不是只拆函数

阶段产出需要**独立持久化**（执行计划/音频索引/spec），失败后恢复不重做已成功阶段的工作；需要**独立重试预算**（TransientNodeError/attempt 计数是步骤机自带）；需要**独立计费结算**（capture 以步骤为单位，失败步骤不 capture 的现行语义按阶段如实生效）；需要 **Tasks 可见性**（步骤行 = Tasks 行，失败落在真实阶段）。这些全是步骤机现成能力；拆成函数则要重建全部。节点形态 = 编译期注入的内部节点（`internal=True` 先例 = `materialize_source`，ADR-043：永不注册为 LLM 工具、用户永不点名）——**agent 面向的创作/编辑工具（design_storyboard）与后端执行阶段是两个层次，内部节点不暴露给 LLM**。

### 9.2 阶段表（输入 / 持久化输出 / 完成条件 / 失败与重试）

| 阶段节点 | 输入 | 持久化输出 | 完成条件 | 失败语义 | 重试 |
|---|---|---|---|---|---|
| `film_prepare`（准备执行） | run.context 的钉版分镜 + digest（**消费确定稿，永不重创作**）；项目 READY 页面 | `run.context.film_execution` 执行计划：页面清单解析 + 音乐曲目/节拍网格 + 意图时间轴（allocate+snap）+ **旁白复用计划**（逐场 hash 查 reuse store：reuse/missing/unfit）+ 逐 aspect 取景调整 | 计划落库 + 漂移校验过（对当前页面重校验，ADR-129 现状保留） | 漂移/音乐不可解/节拍网格不可得 → FAILED（诚实，请求重设计）；DB/存储异常 = TransientNodeError | 瞬时预算重试（幂等：计划重算无副作用） |
| `film_narrate`（准备旁白） | 执行计划的 missing/unfit 清单 | `film_narrations` 行（内容寻址）+ 执行计划补音频引用 + **最终时间轴**（见 9.3） | 每段承诺旁白都有适配窗口的音频 | voiceover 承诺下合成不出 = fail-closed FAILED（现状法）；TTS 传输瞬时重试 | 阶段重试 = 重查复用计划，已合成场命中 store，**天然断点续跑** |
| `film_assemble`（装配作品） | 最终执行计划 | Output 行（type=film，provenance digests + aspect + 调整记录）+ film-spec + `record_media_usage`（film_seconds 计费座）+ `pend_outputs_for_render`（render mirror 出生） | spec 落 Output + 渲染入队 | spec 校验/probe 前置失败 → FAILED；同 spec 重跑幂等清旧 Output（现状 3861-3885 保留） | 瞬时重试幂等 |
| `render`（渲染+校验） | outputs.render_status 认领 | 成片文件 + probe 结果 | probe 过（h264/分辨率/帧数 ±1/音频流） | FAILED + `spec.failure{stage:"probe"}`（现状） | render_max_attempts=3（现状不动） |

`LaunchFilm` 的注册形态**不退役**（最小兼容方案，§9.6）；原单体 run() 的逻辑按上表分家，**零行为新意**（同顺序同校验），只是把中间产物从内存变量变成持久化计划。

**计费边界（保持单体结算语义，不以「失败阶段不收费」宣称政策未变）**：单体时代 launch_film 是一步——中途失败则该步零 capture、钱包零变动。拆分后为保持同一钱包结果：**capture 座唯一 = film_assemble 成功时**（= 单体步骤成功点），金额 = 链累计 metered 成本（prepare+narrate+assemble 各行 cost 之和，经现有 capture_step 的 prior 减法幂等）；prepare/narrate 成功只 meter 落步骤行（observability 可见），**不触发钱包 capture**；prepare/narrate/assemble 任一失败 = 钱包零变动（与单体同点失败一致）；render mirror 语义现状不动（render 失败不退链上已 capture——单体时代亦然）。实现 = 内部阶段节点声明 `capture=False`（orchestrator 在步骤成功处按此跳过 capture_step，assemble 行捕获全链合计）——这是结算语义的真改动点，验收闸 14 锁它。

### 9.3 时间轴所有权（审阅轴 vs 最终轴）

- **审阅时间轴**（设计期呈现读它）：意图轴 = allocate + snap 的结果，由设计拍/Start 快照钉住——呈现稿与执行快照同源（ADR-130 不动）。
- **最终合成时间轴**：`film_narrate` 阶段末定稿（唯一写口）——ADR-136 弹性（无声场零和借帧、donor≤30%/receiver≤40%/Σ帧不变）在此处应用。**允许调整范围 = 弹性界内**；超出 = 诚实失败点名场景，永不静默改轴。
- **两轴关系**：assemble 只消费最终轴烘 spec（含 reveal onset 压网格）；probe 校验最终轴；若 narrate 的移动非零，交付事实如实列出（哪些场次帧数动了、动多少）——呈现时展示的意图轴与成片最终轴的差永远收敛在弹性界内且可解释，不是「呈现一套执行一套」。

### 9.4 新建 / 变体 / 编辑的执行推导（真实依赖，非 op 名路由）

三种 run **同一条四阶段链**；各阶段的工作量由执行计划的实际差异决定：
- 新建：复用计划全 missing → narrate 全量合成。
- 变体（set_aspect）：计划重算仅取景维度；复用计划全命中 → narrate 零合成（其 done 摘要如实报「12/12 幕复用既有配音」）；assemble 烘新 aspect spec。
- 局部编辑：复用计划只列变化场；重排/重卡点后**已有音频逐场重查窗口适配**（适配失败 = 该场进 missing 重合成，或诚实拒并说明）。
- **Tasks 显示** = 四个宏阶段行的真实状态/耗时/成本 + done 摘要带复用计数；失败行落在真实阶段；恢复重跑只重做失败及下游阶段（上游产出已持久化）。不按场景拆 step，不造空壳节点凑行数。

### 9.5 画布形态

画布**保持一个作品生成节点**（launch_film，node_type=video 词表不动）；阶段是 run 内部步骤，不上画布；画布节点状态 = 链的 rollup 投影（现状机制）。

### 9.6 注册兼容（launch_film 的最小兼容方案——不默认链定义能直接替代注册节点）

- `launch_film` **保持注册节点 kind 不动**：NODE_KINDS 自举、工具注册表条目（提案/能力菜单/意图目录三面投影）、报价 fold、出生地 `requires=(WEB_PAGE,)` 门、画布归属全部沿用现状座位。
- 拆分走**编译期展开**：compile 把 launch_film 一步展开为三个 internal 步骤（`film_prepare`/`film_narrate`/`film_assemble`）+ 既有 render mirror——先例 = `materialize_source` 的编译期注入（`orchestrator.py:627-631`、`graph_fill.py:1173`）；internal kinds 声明 `internal=True`（自举豁免先例 `graph.py:239-242`），永不入 LLM 工具目录。
- 报价等价：链 estimate = 三阶段 estimate 之和 ≡ 旧单体公式（编辑/变体 run 的分叉报价同法折算）——等价性入验收断言。
- output_type 归属：Output 出生座 = film_assemble（`type="film"`/`_RENDER_CONTRACTED` 判定/run_review 映射扩展读链，现状 `run_review.py:45` 单点映射改读链尾）。
- **早期验证项（G2 第一天，有阻塞证据再报告）**：编译展开对既有图形状/birthplace ∀-门/画布投影/`pend_outputs_for_render` 认领链的兼容——未定稿前不把「链定义可替代注册节点」当已验证。

## 10. 复用、计费与迁移

### 10.1 旁白复用存储（最小实现）

新表 `film_narrations`（MODULE_ARCH §4 登记 + alembic 迁移）：`(project_id, content_hash, storage_key, duration_s, voice_id, language, config_hash, status, owner_token, lease_expires_at, created_at, updated_at)`，unique `(project_id, content_hash)`。**项目级作用域**（已定）。

- **content_hash** = sha256（归一化文本 | voice_id | language | 合成配置）——复用依据覆盖文本/声音/语言/配置；**窗口适配是时间条件**（音频真实时长 ≤ 新窗口，超出走弹性阶梯）——hash 命中 ≠ 可用，适配检查是第二道。
- **原始音频与速度适配结果分开**：store 只存原始合成音频与真实时长。速度适配是执行期变换：**适配产物 = run 级 staging 文件**（spec 引用的逐场 audio URL 指向它），**不入 store、不进 hash**；恢复语义 = run 重试/恢复时从 store 的原始音频按目标窗口**确定性重 derive**，不依赖上轮 staging 存活；staging 文件随 Output 生命周期（现状输出文件同律）。
- **并发（唯一索引不防重复调 TTS，写路径全部带所有权条件，禁止无条件后到覆盖）**：
  1. **原子占位**：`INSERT … ON CONFLICT (project_id, content_hash) DO NOTHING RETURNING`——拿到行 = 成为 owner（owner_token = 本 run 随机 token + lease 过期时刻）；没拿到 = 读已提交行，done 则直接用。
  2. **有界等待**：占位行 synthesizing → 有界轮询（独立短事务读）；lease 过期未落定 → **有界接管**：`UPDATE … SET owner_token=我, lease=新, status='synthesizing' WHERE … AND status='synthesizing' AND lease_expires_at < now`——影响 1 行才接管成功，0 行 = 他人已接管/已完成，回去重读。
  3. **完成（拥有者校验）**：音频先传 **staging key**（带 owner token 后缀的临时对象）→ `UPDATE … SET status='done', storage_key=<staging>, duration_s WHERE … AND owner_token=我 AND status='synthesizing'`——影响 0 行 = 我已失去所有权（被接管/已 done）→ **删除我自己的 staging 对象**，重读行取他人结果；任何写都不覆盖非我所有的行或文件。
  4. **过期任务不得覆盖/删除新结果**：所有 UPDATE/DELETE 带 `owner_token=我 AND status='synthesizing'` 双条件；staging 对象按 token 后缀隔离，清理只碰自己的。
  5. 合成失败的占位行由 owner 条件删除（不留毒）；run 失败时已 done 的行保留（资源合法，后续 run 可复用）。
- **文件丢失**：读时 storage 对象不存在 = 删行当 miss 重合成（自愈，如实记日志）。
- **清理**：随项目级联删除（同 assets 律）。
- **估算**：估价 tts_chars 行 = 设计拍 change_set 已知的失效场字数（edit/variant）或全量（新建）。

### 10.2 旧作品兼容

旧 Output 自带 render_spec + run.context.prepared_storyboard（provenance）。变体路径：从 provenance 读板 + digest 重证（现状机制）→ 场景无 id → 位置派生一次性升级 → 走正常变体链。旁白复用**按需收割**：旧 spec 的逐场 audio URL + 同文本 captions 可重建 hash 输入（文本来自 spec captions，voice/language/config 来自 run context）→ 文件存在性核验通过才入 store；**无法证明复用条件（文件丢失/字段缺失）= 如实按 miss 重合成并在 change_set 说明**。不全库迁移；不以「只验证新代码生成的新作品」收口——验收含旧作品变体旅程（fixture：以事故项目同构的手工板 + spec 构造，不动原项目）。

### 10.3 计费语义（成本记录与结算边界分开陈述，用户政策不变）

- **报价**：compile 期 estimate fold 现状；film 链分叉——新建 = 导演 token 最坏界 + film_seconds 锚 + tts_chars 全量；**编辑/变体 = 设计拍已算失效范围，报价按实际**（零导演 token 行、tts_chars 只算失效场、film_seconds 按实际板秒数——板已存在，不用 85s 锚）。链报价 = 各阶段 estimate 之和，与单体公式等价（验收断言）。
- **实际成本记录**：每阶段 meter 落各自步骤行（observability：哪阶段烧了多少可见）；「零导演调用」≠ 零 token——edit/variant 的 chat 回合 token 现行不计入生产计量（不变），TTS/渲染如实计量。
- **结算边界（单体语义保持，见 §9.2 计费边界段）**：钱包 capture 唯一座 = film_assemble 成功（= 单体步骤成功点），金额 = 链累计 metered；prepare/narrate 失败或 assemble 失败 = 钱包零变动——与单体同点失败一致；render 失败不退链上已 capture（单体时代亦然）。**这是结算实现的改动（capture 触发位置从「每步骤成功」改为「链尾单座」），不是用户政策的改动**；不以「失败阶段不收费」的话术宣称未变，用注入矩阵实证（验收闸 14）。
- **失败与重试**：幂等键现状（run/step/attempt 三级）；capture_step 的 prior 减法现状；阶段重试不重复 capture（同一座一次调用，重跑由幂等键挡）。

### 10.4 迁移与回退（覆盖 schema/指纹/资源记录）

- 新 schema 字段全部读容忍（scene_id/change_set/constraints_choice 缺省读旧形）——**增量兼容，无数据迁移**；唯一新表 film_narrations 为纯增量。
- 指纹变更（aspect 出 canonical 集）：旧存储指纹永不匹配新算法 → 参数 delta 分类器对 aspect-only delta 判变体、其余判诚实的重呈现一次（不触发导演）；回退 = 恢复 aspect 入集（纯代码，双向存储行不受影响）。
- 资源记录：film_narrations 回退 = 停读停写（合成回落 per-output 存储——旧代码路径保留一个开关周期）；表可留空不拆。
- 每批回退 = 该批 feature flag 或 revert；render spec/renderer 零改动故无渲染侧回退。

## 11. 授权法则应用（产品决定落地 + ADR 修订）

本次产品决定：**用户明确要求制作或修改，且账户设置允许时，呈现变更摘要后可继续执行；不因「这是新版本」自动增加一次确认。** 落地写法：

- **ADR-134 修订**（随批次落档）：fresh 稿 review_hold 默认 ON 收窄到——①作品首稿；②compose 开放重编排（用户没见过的结构）。**edit/variant 版本产生于用户的明确修改请求 = 授权已在场**，不新增 hold：呈现 change_set → 按全局 ask/auto + 费用守卫线（`billing.always_confirm_above` / 不可报价族恒问）继续。
- 用户明示 review-only（「先让我看看」）仍挂 hold（`review_hold=true` 参数保留为唯一逃生门）；Start 门 `422 start.review_hold` 兜底不动。
- ADR-117（auto 档呈现即开工）与 ADR-129（批准 = 消费呈现版）语义不变——修订只动 ADR-134 的默认 hold 面。
- 能力诚实：交付承接建议/能力菜单只承诺已支持的 ops 集合（事故 seq-11 的教训；随 G1 的注册表文案落地）。

## 12. 旅程与执行示例

**主旅程（事故项目同构 fixture 全链）**：贴链接 → 方向讨论（answer）→ design_storyboard(compose) → 呈现分镜（首稿 hold ON）→ 用户「按这版做」→ dock → run：`film_prepare`（计划+复用分析）→ `film_narrate`（全量合成）→ `film_assemble`（spec+Output+计费+渲染入队）→ `render`（probe）→ 交付 → 用户「再来个1:1方形的」→ `design_storyboard(edits=[set_aspect])`——**pending 已清空不影响**：base 从 run provenance 恢复（事故中已实证有效）；**重呈现路径零导演调用**（aspect 已出指纹 + ops 路径无 LLM）→ 变体版本 + change_set（仅呈现类 + 取景调整清单）→ 摘要呈现后按全局 ask/auto + 费用守卫线继续（授权新法：明确修改请求不新增版本确认；本例 auto 档 dock 即开工）→ 变体 run（prepare 只重算取景；narrate 全复用零合成；assemble 烘 1:1 spec；render）→ **第二 Output 诞生，原片保留可访问**（同 work_id）。

**局部内容修改**：「第三幕换图并缩短旁白，其他保留」→ 读座读当前版本 + 候选视图带图 → `edits=[update_scene(s3, view, narration)]` → 新版本（change_set 仅 s3）→ run：narrate 只合成 s3（11/12 复用）。

**重排**：「价格那幕提前」→ `edits=[reorder_scenes(...)]` → 场 digest 全不变、整板 digest 变（顺序是有意义变化）→ 旁白零重合成、逐场窗口适配重查 → divider 序号确定性重编号 → 时序重 snap。

**换音乐双形**：`set_music(retime=keep_cut)` = 换曲帧不动（呈现诚实：不压新节拍）；`retime=recut` = 边界重 snap + onset 重压 + 音频窗口重查。模型按用户原话选形。

**自由结构**：用户未指定时长 → compose 由 agent 依素材厚度选结构（如 6 幕 38s 短切）并在方案呈现所选（`constraints_choice.source=agent`）——不再有「无明确要求就拒绝」。

**无专用路由的组合修改**（验收必含）：「结尾改成行动号召文案、proof walk 换成 pricing 页视图并配新旁白、第二章整章删掉压短全片」→ `edits=[update_scene(end, 文案槽), update_scene(prove, view={page:pricing,shot}, narration=新句), remove_scene(ch2_divider), remove_scene(ch2_ui)]`——四个既有 op 有序原子应用（整章删除 = divider+walk 成对删，EMPTY_CHAPTER 按新序重查自然通过），无新路由。（施工时以真实 ops 语义写剧本断言。）

## 13. 施工批次（依赖序）

| 批 | 范围 | 估时 | 依赖 | 回退 |
|---|---|---|---|---|
| **G0 事故修复** | SSE 回合异常 `logger.exception` 全堆栈（routes.py:652 座）；engine `pool_pre_ping`+`pool_recycle`；机制级回归（异常日志可见性 + 闭连接恢复） | ~1d | 无 | revert |
| **G1 状态契约 + 编辑 ops + 变体** | scene_id（slot 板用骨架 key）+ ops 应用座（原子/有序/失败保留原版）+ 参数两分与 delta 分类 + change_set 呈现 + 读取座（get_output_spec film 分支 + 图片携带机制——**早期验证①：MiniMax tool-role 图片 spike 首日，失败走 synthetic user 消息兜底**）+ 旁白复用 store（表+迁移+原子占位并发律 §10.1）+ 取景重查 + 授权新法落地（ADR-134 修订）+ 能力文案收窄 + **早期验证②：旧作品 provenance 字段完整率抽查**（§10.2，未运行项） | ~3d | G0 | 指纹/flag 回退见 §10.4 |
| **G2 宏阶段拆分** | film_prepare/film_narrate/film_assemble 内部节点（internal=True）+ 编译期展开（§9.6 最小兼容：launch_film 注册形态不动）+ 阶段持久化/重试 + **计费边界改造（capture 单座 = assemble）与结算注入矩阵** + Tasks 宏行真实显示——**早期验证③首日：注册链兼容定点验证（编译展开/报价等价/output_type 路由/Tasks 投影/出生地门），阻塞证据再报告** | ~2.5d | G1（复用 store/版本形状） | 链编译开关回单体（保留单体一个开关周期） |
| **G3 编排恢复 + 字段级修复** | DraftStoryboard v2（scene_id）+ resolve_draft + 约束四层 validator（warning 分级）+ 全 shots 视觉（预算帽）+ prompt/pack 重写（骨架降配方工艺+worker 兜底）+ 保留候选定点修复循环 | ~3d | G1（scene_id/视觉机制） | revert（骨架代码保留） |
| **G4 验收矩阵** | §14 全量 | ~1.5d | G1+G2+G3 | — |
| **G5 餐馆素材适配（另立批）** | image 资产 → StoryboardPage 接缝 + manifest 来源设计 | 另估 | G4 后 | 不合并 |

核心合计 ≈ **11 个工作日**。G2 与 G3 可并行（不同子系统），串行排是保守口径。每批仪式链：pytest + check_gates + 触及 prompt 面加 prompt_gate + 剧本矩阵 + tsc。

## 14. 验收（可执行）与未验证项

**主验收 = 真实 Chat 旅程**（§12 事故同构 fixture：隔离副本/手工构造，不修改不付费复跑原事故项目）：

硬性正确性闸（确定性断言，pytest 纯套件 + 剧本矩阵）：
1. pending 清空 ≠ 失去作品（provenance 恢复 + 变体成功）；
2. 「重呈现」/变体请求**零导演调用**（agent_calls 台账证据；「零导演调用」不宣称零 token——chat 回合 token 不入生产计量为现状口径）；
3. 原片保留、变体独立（两 Output 同 work_id、原文件可访问）；
4. Tasks 宏行与真实执行/复用一致（复用计数 = 实际 TTS 调用数的补）；
5. 阶段失败落在真实阶段；恢复重跑不重做上游有效工作（prepare 成功行不重来——store 命中证据）；
6. 一幕换图+缩短旁白：其余场景 digest 不变、只该场重合成；
7. 重排：场 digest 全不变、整板 digest 变；旁白零重合成——**限定在全部既有音频适配新窗口的 fixture 数据**；另设不可适配注入用例：窗口容不下的场重合成、其余复用，各自如实进 change_set；
8. 换音乐双形各自的帧/音频断言（keep_cut 帧全等；recut 帧变、音频在可适配 fixture 下复用，不可适配场重合成）；
9. 用户未指定时长时 agent 自主结构合法过闸（无 70-118 硬拒）且 `constraints_choice.source=agent`；
10. 字段级修复双层覆盖：注入**语义违例**与 **JSON 可解析但 schema 单字段不合法**（pydantic loc 映射）各一例 → 定点修复成功、其余字段字节级不漂移；
11. 多层重试不重置预算不重复生成：预算单座（1800s + 调用数上限 §8.2.7）；无进展判据断言（同签名违例两轮复现 / 签名集两轮无变化 / 修复倒退 → 停止并诚实失败）；
12. 无专用路由的组合修改走既有 ops 完成（§12 末例）；
13. 计费回归：变体 run 实扣 = film_seconds 实际值 + 零 TTS；hold=capture+release 台账平衡；旧作品变体同政策；
14. **结算边界注入矩阵（issue-2 闸）**：prepare/narrate/assemble/render 四个注入点 ×（拆分前基线 worktree / 拆分后）同 fixture 同注入 → 按用户口径比较：**净扣费相等、hold 释放/退款相等、无重复收费**（不同步骤结构产生的钱包行数/行形可以不同，不要求逐行相同；链累计结算不得把同一成本重复汇总进 capture）——拆分前单体中途失败零 capture；拆分后 prepare/narrate/assemble 失败同样零 capture、render 失败同样保留链上已 capture（现行政策：装配成功后 render 失败保留已结算制作费用，不以「失败 run 零扣费」概括）；
15. 授权回归：edit/variant 无新增 hold；首稿/开放重稿 hold ON；review-only 参数与费用守卫线不动；
16. 旁白并发：**正常并发**两 run 同 hash → 一次 TTS 调用（provider 计数证据）；**超时接管**场景断言 owner 隔离（过期 owner 的 finalize 不得覆盖/删除新结果，行与文件双向）与结算幂等（重复 capture 由幂等键挡）；provider 无幂等支持时**不承诺外部 TTS 调用绝对恰好一次**——承诺的是行级占位唯一与结果不串台；速度适配 staging 缺失时从原始音频确定性重 derive；
17. 注册链兼容：NODE_KINDS 自举绿、链报价 ≡ 单体公式、output_type 路由、编译展开图形状、出生地门——全部既有断言在拆分后形态下重跑绿；
18. 约束契约：EMPTY_CHAPTER 对「章节卡 + plate 紧随」合法放行（实质 ≠ 仅 web walk）；旁白估计帽超出走字段级修复通道（非 warning 通道）；
19. 不主动承诺未支持能力（能力菜单/交付建议只列已实现 ops）；
20. 仪式链全绿 + S11 更新 + 新增变体/编辑旅程剧本座。

观察指标（非闸）：一次通过率/修复轮次/墙钟/token 成本——**n=3 仅探索冒烟，不作 P95 或统计显著性结论**。

视觉验收（**人工**，不宣称运行时自动视觉闭环）：每幕中点帧 + 相机到达帧接触表 + **全片动态看片**（相机运动/转场/节奏）；A/B 同素材同渲染器对照（linear.app / zymix.ai / 一新站）。

**未验证项（早期验证，有阻塞证据再报告；不把未知写成已验证）**：
- MiniMax tool-role 图片支持（本地代码与请求形状已验证；供应商实测 spike 待授权——阴性则启用已选定的 synthetic user 消息兜底）。
- 旧作品变体的 provenance 字段完整率（G1 抽查旧行 prepared_storyboard 存在性——未运行）。
- 注册链兼容（§9.6 各兼容点的编译期展开实证——G2 首日定点验证）。
- 结算边界注入矩阵的拆分前后一致性（设计目标 = 净扣费/释放/重复收费口径一致；G2 实证前为待验证项）。
- 全 shots 视觉对导演一次通过率的方向性影响（G4 观察指标读出前为假设）。

## 15. 不做清单

第三方 skill 执行平台 / 自由渲染代码 / 行业专用流水线 / 新场景型与转场大扩展 / 可视化编辑器 / 版本浏览产品（版本表随之延后）/ 通用依赖框架 / 自动视觉验收系统 / insert_scene 快捷 op（compose 可增删场景）/ set_voiceover(true)（走 compose）/ 导演工具 loop / 餐馆素材接入（另立批）/ 全库迁移 / 修改用户计费政策。

## 16. skill 库方向

skill 指导 agent **组合**现有能力（ops/场景型/约束分层），不是给固定生成器喂文案；新的创作方法不应天然要求新增后端生产工具——三层判据：只改 skill = 弧配方/节奏/选图与取景工艺/旁白声音/呈现口吻（pack 装配层，现状座位）；必须扩展工具/schema = 新 op 词汇、新约束 override、新材料源适配；必须扩展渲染底座 = 新场景型/转场/字幕样式/自由布局。

## 17. 待拍板

无剩余待拍板问题。变体收费沿用已拍板决定：变体 run 实扣 film_seconds（渲染真工作）+ 零 TTS 零导演 token，报价单如实列复用项。其余技术选择已按证据在本文定案（§7-§10）。
