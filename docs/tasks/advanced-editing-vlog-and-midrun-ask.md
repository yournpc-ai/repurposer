# Batch 3 · Mid-Run Ask User、高级剪辑原语与 Vlog 首页演示（施工合同）

> **状态（2026-11-29 修订）**：READY FOR BRANCH（待在新分支开工）。本合同整合三项强关联施工块，并按交付收益重排落地顺序：**Stage 1 · 底座 A（执行中与修改轮 `ask_user` 同轨挂起、无感续跑与非写死决策记忆）** → **Stage 2 · 底座 B2-A（React / TSX + HTML + SVG 受控代码画笔：解锁并跨平台化现有 `remotion-project` 运行时，独立可交付商业大片跃升）** → **Stage 3 · 底座 B1（实拍高级剪辑原语：画中画、层序、关键帧、蒙版、变速、Top 10 参数化滤镜、视频 Motion Block 与源帧感知）+ 底座 B2-B/B3（定格与视频 Luma Matte 抠像）+ 前台 C（隐藏「模板」Tab 与首页货架/标杆成片）**。
>
> 上位架构与硬约束以 [Agent Editor 主合同](new-agent.md)、[作品模型](../VIDEO_PROJECT.md)、[渲染契约](../RENDERING.md)、[声音合同](../MUSIC_ARCHITECTURE.md)、[账本与授权](../BILLING.md) 及 [进度 §0](../PROGRESS.md) 为准。

---

## 1. 产品目标

将 Rookie 从“偏商业官网 MG 宣传片、开工前只能问一次”的创作体验，升级为**能与用户在制作中途自然协作、通过原子剪辑原语组合复杂剪辑艺术（画中画、蒙版、关键帧、抠像）的 AI 视频剪辑师**，并以 **Vlog 与高级视觉合成** 打开更广阔的创作者市场：

1. **像顶级 Agent 一样中途自然协作**：Agent 在多步骤剪辑中途遇到素材选片、定格选帧、原声/配乐取舍或明显审美分叉时，可在当前任务流内随时发起 `ask_user`；等待期间工作状态轨保持进行中（ing）观感不结算、不中断，回答后原轨无缝续跑。
2. **以少量正交原语释放高级剪辑艺术**：不造黑盒特效模板或第二套执行系统，通过升级 `insert_visual`（视频画中画/分屏）、新增 `set_layer_order`、`animate_object`（秒级全属性关键帧）、`set_mask`（声明式几何蒙版与动画）及分阶段 `extract_subject`（定格/视频主体抠像），组合出“人物穿字、定格弹出、拉帘对比转场、多机位画中画、丝滑运镜”等可随时继续自然语言精修的作品。
3. **前台心智去“模板化”、立“高级剪辑力”**：隐藏首页「模板」独立 Tab，以「Vlog 剪辑」「创意合成」「产品与演示」「观点与讲解」组织首页演示货架与填空式 Brief，并用 Rookie 真实链路产出首批高辨识度标杆成片。

---

## 2. 不可违背的架构与产品护栏

1. **单一执行架构与唯一写口**：继续沿用唯一 `ToolLoopAgent`、`apply_composition_edits` 唯一作品写口、`CompositionVersion` 不可变版本与 `video-spec` 中立契约；严禁为画中画、蒙版、抠像或 Vlog 新建独立工作流、第二套 Z-index 或不可编辑的黑盒烘焙捷径。
2. **`confirm_credits` / `confirm_execution` 与 `ask_user` 严格正交**：
   - `users.settings` 中的 `confirm_credits`、`confirm_execution`（见 `apps/api/app/platform/user_settings.py:read_confirmation_prefs`）**只控制付费生成与导出授权卡片（`media_permission`）**，绝不影响创作/剪辑决策类 `ask_user` 的可用性与触发；
   - 将积分确认设为 `auto` 不得抑制 `ask_user`；设为 `ask` 也不得把普通创作澄清误判为付费授权；
   - 用户回答 `ask_user` 或在对话中口头回复，**永不绕过**付费积分守卫线与 `media_permission` 显式授权机制（遵守 `BILLING.md` 与 `CLAUDE.md`）。
3. **持久化挂起而非挂死长连接**：`ask_user` 等待用户作答必须依赖数据库持久化状态与原 `opening_id` 续行，严禁在 API 进程内存中挂死 HTTP/SSE 连接空等用户输入；刷新页面、切 Tab 或服务重启后仍可从原 `opening` 恢复挂起状态与当前步骤。
4. **渲染双端确定性与可编辑性**：所有新增 `video-spec` 字段（`playback_rate`、`preserve_pitch`、`color_grade`、`crop`、`frame`、`mask`、`matte_source_id`、视频资源挂载及对应 `AnimatableProperty`）必须在 Python 编译器、Zod Schema、Web `@remotion/player` 与服务端 `apps/render` 保持 Py↔TS 逐帧一致，缺省值不序列化出多余 `null` 键以保证历史 `content_digest` 零漂移；所有合成结果保留图层身份，支持后续自然语言单对象续改。
5. **技法由“完备原语 + 提示词”按需组合，绝不写死为默认效果**：高级剪辑技法（画中画、蒙版、相似形匹配、瑞士网格排版、重调色、变速等）属于创作者可按需唤起的技术能力，**默认剪辑保持干净克制**，绝不把高风格化特效硬编码为所有视频的默认模板；首页 Demo 通过精细的 Hover/Use 提示词示范“如何用自然语言组合这些高级技法”。
6. **诚实样片、版权合规与测试门禁**：首页正式上架样片必须由 Rookie 真实链路制作并经视听与局部修订验证（不得用外部手剪冒充验收通过）；实拍素材与配乐须使用许可清晰可核验的开源/免版权或自拍源；施工按改动面通过 `make test-fast` / `test-chat` / `test-web` / `test-render` / `test-e2e`。

---

## 3. 底座 A · Mid-Run 与修改轮 `ask_user` 同轨挂起、无感续跑与决策协同

### 3.1 解除现有过度限制（Backend）

| 目标文件 | 现状限制 | 改造方案 |
| :--- | :--- | :--- |
| `apps/api/app/chat/prompts.py` | ① Line 351 隐藏路径 `names.discard("ask_user")`；② Line 492 `dialogue_wire` 裁掉 `slot`，Line 493 `not native_creation` 裁掉 `items`；③ Line 497 `authorized_media.status == "available"` 丢弃 `ask_user` | ① 制作/编辑/修改阶段全量开放 `ask_user` 的自由题与 `items` 多题数组；② 解除 Line 351 / 497 的过宽丢弃，**与最新 `export_video` 导出即自动交付机制对齐**（仅在“本轮已完成正式交付、只剩最终收尾回复”的窄态禁用 `ask_user`），其余创作、媒体就绪后与后续修改轮均允许调用 `ask_user` |
| `apps/api/app/chat/plan_turn.py` & `apps/api/app/models/schemas.py` | Lines 860–896 `missing_brief_question_items` 强制把 `items` 绑定到旧 `Brief` 固定槽位；`merged_brief.asked` 阻断同槽二次追问 | 保留旧 `Brief` 槽位兼容，同时全面放行 **无固定枚举的自由临时题（ad-hoc item）**（不要求预定义槽位表，任意创作分叉或修改方案确认均可直接发起） |
| `apps/api/app/chat/service.py` & `routes.py` | ① 调 `ask_user` 后终止并结算当前步骤；② `_continue_chat_answer`（Lines 1329–1336）把初始 `opening.content` 原封不动重拼进 `reply`，中途续行易误导模型重做全片；③ 自由题答案未投影给后续修改轮 | ① 持久化问题行携带 `mid_run_ask: true` 与所属 `opening_id` / 当前 `steps` 快照（**不把 `in_progress` 步骤误结为 `done`**）；② 中途/修改轮续行构造**增量续行上下文**（明确标出当前已保存 `version_id`、已完成工具回执与用户刚作出的决定），**不再把初始 `opening.content` 伪装成新指令重发**；③ 见 §3.2 轻量决策投影 |
| `apps/api/app/prompts/chat/video_editor.j2` | 明文禁止“确认卡后再问第二次”、禁止弹卡前调 `update_steps` | 改写为**克制提问与修改协同宪法**：① 允许在多步执行中途（选片/选帧/音画取舍/明显审美分叉）以及**成片后模糊修改请求**（如“第 3 幕改清爽点”给出 2–3 个具体改法选项先对齐再动手）发起单卡 `ask_user`；② 纯技术参数（坐标、缓动、音效配方、闪避 dB）严禁打扰用户；③ 每次提问必给 `recommended_id` 与 `default_path`（一键跳过按推荐继续） |

### 3.2 轻量非写死决策记忆与修改协同（Antigravity / Neon 风格）

`ask_user` 不只是“提问”，本质上是用户在创作与修改途中注入的**权威决策**。严禁为此新建写死字段的数据库表或固定枚举槽位，采用与顶级 Agent 一致的**无模式（schema-less）对话记录投影**：
1. **直接复用持久化 Q&A 记录（零新表、零写死槽位）**：每一次用户已作答的 `ask_user` 行本就持久化在 `messages`（含 `question`、`answer`、`turn_id` 及当时关联的 `version_id` / `scene_id` 语境）。
2. **上下文轻量投影（防跨轮失忆与修改回退）**：在 `prompts.py` 组装当前轮与后续任意**修改轮**上下文时，自动从会话最近已作答的 `ask_user` 记录中投影一个紧凑、自由格式的 `settled_user_decisions` 列表（每条仅含 `question`、`user_choice`、`at_version`），同时纳入 Per-Turn Trace（`turn_trace.py`）的 `context_sources` 审计。
3. **续行自由响应策略**：用户提交答案进入续行 `ToolLoop` 后，模型完全自主决定响应方式：
   - **静音直调工具（允许零前置 prose）**：直接按用户决定发出下一批工具调用（如 `update_motion_block` / `insert_visual_component` / `create_video`），不强制吐过渡废话；
   - **简短确认 + 调工具**：先用 1 句自然确认句交代动作再并行调工具；
   - **直接文本答复结束**：若用户明确取消或仅需说明，直接正文答复结束，不误触发强逼继续导出。

### 3.3 等待期与回答后的前端无感连续态（Frontend）

核心改造点位于 `apps/web/src/components/chat/timeline/liveState.ts`、`ChatConversation.tsx`、`ThinkingState`（`thinking-state-clean.tsx`）与 `DecisionCard`：

1. **等待作答期间保持“进行中（ing）”观感**：
   - 在 `selectChatLiveState` 中引入挂起态判定（当当前活跃 `opening` 存在未作答的 `mid_run_ask` 卡片，或已有 open `activityFold` 且处于 `mid_run_ask` 等待时）：
     - `mode` **保持在进行态（不跌落为 `idle` / `settled`）**；
     - 工作轨顶栏**严禁切换为 `Worked for Xs`、已停止或完成态 UI**，而是保持进行中的微动状态与当前 `liveFocus` / 活跃步骤（`in_progress`）；
     - **收起态完全无感**：若用户已折叠过程状态行，顶栏只维持自然进行中的状态条，同时输入区上方平滑浮出 `DecisionCard`，用户看不到任何“停止 → 重启”的视觉割裂。
2. **回答后原地折叠进同一工作轨**：
   - 用户在 `DecisionCard` 完成选择（或跳过）后，卡片收回并在**同一个 `activityFold` 内部**沉淀为一条紧凑、可展开/收起的 Q&A 纪要块（展示问题摘要与用户选择），紧接着续行工具步骤、阶段说明继续追加在同一工作轨下；
   - 只有当整个 `opening` 真正完成交付/给出最终答复（或被用户显式 Stop / 遇到终态失败）时，整个工作轨才统一结算为单条 `Worked for Xs ›`。
3. **与 `confirm_credits` 授权卡的视觉与语义边界**：
   - `media_permission` 付费授权卡继续作为独立高醒目确认卡（`ApprovalCard`）呈现报价与积分上限，与创作类 `DecisionCard` 清晰区分；二者互不覆盖、互不放行。

---

## 4. 底座 B · 高级剪辑原语（画中画 / 层序 / 关键帧 / 蒙版 / 抠像）与 Skills

按投入产出比与风险拆为 **3 个阶段（Phase B1 → B2 → B3）**，每阶段独立可验收、独立可出 Demo 成片。

### 4.1 Phase B1（优先落地，零新增 AI 推理成本）：画中画、层序、关键帧、蒙版、Clip 通用变速、Top 10 参数化滤镜、视频 Motion Block 与源帧感知

#### A. Schema & 渲染扩展（`apps/api/app/editing/schemas.py` → `packages/video-spec/src/schema.ts` → `packages/video-remotion/src/Video.tsx`）
- **Clip 级通用变速**（挂载于 `Clip`，与 `temporal.py` 现有 `time_map` 数学底座统一；默认 `1.0` 时 `exclude_if` 省略，保证旧版 `content_digest` 零变化）：
  - `playback_rate?: number`（`0.25..4.0`，默认 `1.0`）、`preserve_pitch?: boolean`（默认 `true`，变速不变调）；
  - **统一语义**：
    - `VideoObject` / `AudioObject`：`output_duration = source_duration / playback_rate`；Remotion 视觉走 `<OffthreadVideo playbackRate={...}>`，服务端音频与原声走 FFmpeg `atempo` 链（支持变调开关）；
    - `Animation` / `TextObject` / `ImageObject` / `MotionBlockObject`：沿用既有 `_time_mapped_clip` 按比例缩放 `clip.range`、全部关键帧 `at` 与 `text_part.stagger`，实现视频、音频、动画一套通用变速心智；后续可按同一模型平滑扩展分段速度曲线 `speed_curve`。
- **Top 10 参数化风格滤镜预设层（复用 `visual_presets` 目录表，0 新 SQL 表）**：
  - 复用 `apps/api/app/catalog/` 体系，在 `visual_presets` 新增 `asset_kind = "color_grade"`，接入 Studio `/presets` 浏览页与 Agent 目录检索工具（`search_color_grades` / `get_color_grades`）；
  - 预置 **Top 10 精选调色预设**（`fuji_classic` 富士青绿、`kodak_warm` 柯达暖调、`cinema_teal_orange` 电影青橙、`soft_pastel` 日杂奶油、`editorial_mono` 杂志黑白、`moody_forest` 森系暗调、`clean_studio` 通透影棚、`golden_hour` 黄金时刻、`vintage_vhs` 复古胶片、`cyber_neon` 赛博霓虹）；
  - **可调参数结构**（挂载于 `CompositionSettings.color_grade` 作整片统一调色层，亦可挂于单条 `VideoObject`/`ImageObject` 作局部覆盖；作品仅存展开后的确定性参数，目录元数据不入哈希）：
    `color_grade?: { preset_id?, intensity: 0..1, exposure: -1..1, contrast: -1..1, saturation: -1..1, temperature: -1..1, tint: -1..1, vignette: 0..1, grain: 0..1 }`；
  - **可关键帧化的光学与色彩属性**：在 `AnimatableProperty` 新增 `color_grade.intensity`、`color_grade.saturation`、`filter.motion_blur`（水平/定向动感拉丝模糊，SVG `<feGaussianBlur stdDeviation="x y">`）与 `filter.bloom`（电影高光柔光/丁达尔光晕，SVG `<feColorMatrix>` + `<feGaussianBlur>` + `<feBlend mode="screen">`），全部复用 `animate_object` 驱动（覆盖「城市轻轨聚焦/颜色晕染/丁达尔高光收束」等 3–8s 爆款开场）；
  - `Video.tsx` 统一用确定性 CSS filter + SVG `<filter>` + 按帧号伪随机颗粒渲染，保证预览与导出像素一致。
- **画中画外观与裁切**（挂载于 `VideoObject` & `ImageObject`，全部可选、向后兼容）：
  - `crop?: { x: number, y: number, width: number, height: number }`（0–1 归一化源裁切，支持横转竖局部构图与分屏裁切）；
  - `frame?: { corner_radius: number, border_color?: "#RRGGBB", border_width?: number, shadow?: "none" | "soft" | "elevated" }`。
- **声明式几何蒙版**（挂载于视觉 `Object`，向后兼容）：
  - `mask?: { shape: "rect" | "circle" | "ellipse" | "pill" | "linear_wipe" | "polygon", center: [number, number], size: [number, number], corner_radius?: number, angle_deg?: number, progress?: number, feather_px?: number, invert?: boolean }`；
  - `AnimatableProperty` 新增：`mask.center`、`mask.size`、`mask.progress`、`mask.feather`；
  - `Video.tsx` 统一采用按 `clip_id` 隔离 ID 且 `userSpaceOnUse` 对齐 `layout.width × height` 的 SVG `<mask>` / `<clipPath>`（羽化用 `<feGaussianBlur>`）逐帧求值，保证 Web Player 与 Remotion 导出逐像素一致。
- **`MotionBlockObject` 扩展视频资源挂载 + 瑞士动态网格块（`editorial_grid_frame`）**：
  - 扩展 `motionBlockResourceSchema` 支持 `content_type: "video/mp4" | "video/webm"` 及可选 `source_start_frame` / `source_end_frame` / `muted` / `gain_db` / `playback_rate`，让高级排版动效块也能直接挂载动态实拍视频；
  - 新增原生块 `editorial_grid_frame`（支持 3×3 细线红点动态网格按拍点滑移、底层模糊全屏视频 + 上层清晰网格视口、磨砂半透明条与杂志风大字/注释同步重排），解决纯靠 LLM 手动对齐 10+ 独立元素关键帧必然漂移的问题。

#### B. Native Tools（注册于 `apps/api/app/chat/editor.py` & `turn_tools.py`，全部秒级参数，严禁暴露 `tick`）
1. **升级 `insert_visual`**：
   - 支持图片**与视频**固定快照（`source_id`）；视频支持 `source_start_seconds` / `source_end_seconds`、`muted`、`gain_db`、`playback_rate?`；严格区分静态图（无源窗）与视频（必填源窗）两套校验；
   - `layout_preset`: `fullscreen | pip_top_right | pip_top_left | pip_bottom_right | pip_bottom_left | split_left | split_right | split_top | split_bottom | custom`；
   - 可选 `box: { x, y, width, height }`（归一化 0–1）、`crop`、`corner_radius`、`border_color`、`border_width`、`shadow`、`layer: "above_main" | "below_captions" | "top"`。
2. **新增 `set_layer_order`**：
   - 参数：`clip_id`、`position: "above" | "below" | "to_back" | "below_captions"`、`reference_clip_id?`；
   - 服务端复用已有 `SetTrackOrder` Op（必要时拆轨），默认保护字幕轨不被意外遮挡。
3. **新增 `animate_object`（渐进替代受限的 `set_keyframe`）**：
   - 参数：`clip_id`、`property`（`transform.position` / `transform.scale` / `transform.rotation` / `opacity` / `filter.blur` / `mask.progress` / `mask.center` / `mask.size`）、`mode: "replace" | "upsert" | "clear"`、`keyframes: [{ at_seconds, value, easing: "linear" | "ease_out" | "ease_in_out" | "spring_soft" | "hold" | [x1, y1, x2, y2] }]`；
   - 服务端将片段局部秒数换算为合法整数 tick、把语义 easing 映射为标准 `cubic_bezier`，并在工具说明与回执中明确 `transform.position`（相对静态变换的偏移）与 `scale/rotation/opacity`（绝对值）的语义差异，完整保留同 Clip 其他属性动画。
4. **新增 `set_mask`**：
   - 参数：`clip_id`、`shape`（`rect | circle | ellipse | pill | linear_wipe | none`）、`center?`、`size?`、`corner_radius?`、`angle_deg?`、`feather_px?`、`invert?`、`wipe_in_seconds?`、`wipe_out_seconds?`；
   - 若传 `wipe_in_seconds` / `wipe_out_seconds`，自动编译为标准 `mask.progress` 关键帧，后续可被 `animate_object` 精修。
5. **新增 `set_clip_speed`（Clip 级通用变速）**：
   - 参数：`clip_id`、`playback_rate`（`0.25..4.0`）、`preserve_pitch?: bool`、`ripple?: bool`；
   - 对视频、音频、动画/文字/动效块统一生效，自动校验源素材可用时长边界并同步更新输出时长与关键帧刻度。
6. **新增 `set_color_grade` & 目录查询 `search_color_grades` / `get_color_grades`**：
   - 参数：`scope: "composition" | "clip"`、`clip_id?`、`preset_id?`（从 Top 10 展开基准参数）、`intensity?`、`exposure?`、`contrast?`、`saturation?`、`temperature?`、`tint?`、`vignette?`、`grain?`、`clear?: bool`；
   - 支持“一键套预设 + 任意单维参数微调”，不覆盖未点名字段。
7. **新增 `inspect_source_frames`（源视频关键帧抽帧感知）**：
   - 参数：`source_id`（已上传/准备的视频资产或快照）、`timestamps_seconds?: list[float]`（默认均匀抽 4–6 帧，受有界上限约束）；
   - 返回带归一化坐标参考的真实帧图给多模态模型，使 Agent 在剪辑前就能看清上传视频的构图、主体中心点（如圆形匹配剪辑对齐 `(0.5, 0.5)`）与废镜头位置。

#### C. Phase B1 内置 Skills（`apps/api/app/skills/`）
- **新增 `vlog-editing/SKILL.md`**：定义实拍 Vlog 剪辑方法论（先用 `inspect_source_frames` 看片选段、前 2s 视觉/声音钩子、1.5–3.0s 节奏切镜与适度变速、A-Roll 原声与 B-Roll 空镜交替 + BGM 自动闪避 `-24 ~ -26 dB`、36 条实录 Foley 与 Sound Engine 轻音效贴点、画中画/分屏空间叙事、按用户需求选用调色预设与轻字幕、遇多段实拍选片或音画取舍时使用 Mid-Run `ask_user`）。
- **升级 `talking-head-video/SKILL.md`**：从纯字幕口播升级为「视觉化口播」（ASR 去气口 + 每 4–6s 轻推镜关键帧呼吸感 + 画中画参考图/录屏浮窗 + 蒙版分屏对比 + `karaoke_focus` 逐词高亮）。

---

### 4.2 Phase B2（其中 B2-A 提前至 Stage 2 优先落地）：React / TSX + HTML + SVG 代码画笔 + 静图/定格主体抠像

#### A. 解锁并跨平台化现有 `remotion-project` 受控组件运行时（Phase B2-A — Stage 2 核心）
严禁使用低表现力的自定义光栅指令（放弃扩写 `draw-2d` PIL 光栅方案），直接启用并补齐仓库已有的 **React + TSX + HTML + SVG + CSS** 组件烘焙管线（`apps/render/src/component-runtime/{policy,worker,bake}.ts` + `apps/api/app/tools/video/components.py`）：

- **架构铁律：坚决不把 `remotion-project` 做成「半个 OpenFilm」**（源码、文件与全链路边界）：
  - **现状链路剖析**：
    1. **原生活对象层**：`TextObject`、`MotionBlockObject` 在 `apps/api/app/editing/video_spec.py`（Lines 198–206）编译为活结构化 JSON，由前端 `packages/video-remotion/src/Video.tsx`（`TextLine` / `MotionBlocks.tsx`）实时作为真实 DOM/React 渲染——改文案、改字号、改颜色 0ms 生效，且天然支持未来画布直接点选文字；
    2. **代码画笔烘焙层**：`GeneratorObject(producer="remotion-project")` 在 `apps/api/app/editing/schemas.py`（`RemotionProjectSource` Lines 540–600、`GeneratorObject` Lines 1247–1330）完整保存不可变 TSX 源码与 `props` / `props_schema`；经 `apps/api/app/tools/video/components.py` → `apps/render/src/component-runtime/{bake.ts,policy.ts,worker.ts}` 烘焙为 `h264` MP4 后，在 `apps/api/app/editing/video_spec.py`（Lines 207–222、472–489）降维编译为普通 `kind: "video"` 片段，由 `Video.tsx` 通过 `<OffthreadVideo>` 播放；修订时再通过 `apps/api/app/editing/service.py`（Lines 408–427）把完整 `project` 源码和 `props` 读回给 Agent 做单 Clip 精准重烘。
  - **为什么必须防退化**：如果把本该活着的普通字幕/常规标题硬写死进 TSX 字符串，或把整条 30–45s 视频烘成一个巨型 `remotion-project` Clip，就会丧失网页/DOM 的瞬间编辑优势，退化成“改一个字等半分钟全片重烘”的半个 OpenFilm。
  - **4 条强制工程与创作护栏**（落地于 `insert_visual_component` / `update_visual_component` schema、`apps/api/app/editing/service.py` 与 `generative-motion/SKILL.md`）：
    1. **活字留原生轨，画笔专攻高表现力图形**：普通字幕、常规角标与常规标题继续留在原生 `TextObject` 轨叠加在代码画笔之上（0ms 修改、可批量 `edit_text`）；只有文字与 SVG 遮罩/路径/粒子存在像素级融合（如 Claude 15s 片里的遮罩字效、Gemini 粒子聚字）时才放进 `remotion-project`。
    2. **文案、字号、品牌色必须参数化进 `props` + `props_schema`**：`insert_visual_component` 鼓励/要求将组件内可变文案、字号缩放、主色/底色声明在 `RemotionProjectSource.props` 与 `props_schema`；`update_visual_component` 支持轻量 `props_patch`（无需重写 TSX 源码即可精准改字/改字号/换色，100% 确定性不漂移）。
    3. **按幕/按拍模块化（单 Clip 2–8s），禁止整片单组件烘焙**：每个代码画笔 Clip 独立对应 1 个视觉幕或高潮拍，修改局部时仅重烘该 Clip，命中相同 `program_digest` 直接复用缓存，周围音轨、字幕与其他幕纹丝不动。
    4. **B2-A 先行聚焦全屏/实底 `h264`（`worker.ts:179`）**：不盲目引入有 Safari 兼容风险的 WebM Alpha，实底/全屏独立幕直接复用现有 `h264` 管线零风险落地；如需叠加透明前景留给 B3 Luma Matte。

- **解除 4 处已有代码卡点（实测现状已确认）**：
  1. **修复 `bake.ts` 单槽并发硬拒**：`apps/render/src/component-runtime/bake.ts`（Lines 31–32、100）当前 `MAX_ACTIVE_BAKES = 1` 在并行调用时**直接抛错**，会导致 Agent 同轮并行创建多幕 TSX 组件时第 2、3 幕瞬间失败；必须改为**有界 FIFO 排队队列**（并发 1–2，超额排队而非报错）。
  2. **跨平台浏览器路径与 Linux 生产隔离**：修正 `bake.ts`（Lines 15–25、40–44）与 `worker.ts`（Lines 24–32）硬编码的 `mac-arm64`/`mac-x64` Chrome Headless Shell 路径；本地开发继续沿用已实测可用的 macOS Seatbelt（`sandbox-exec`，本机 `:3001/health` 已返回 `enabled: true`），**Linux 生产优先落地独立无网 `component-runner` Sidecar 容器**（`network_mode: none` + 只读依赖挂载，避免云容器默认 seccomp 禁止非特权 userns 导致 `bwrap --unshare-net` 报 `Operation not permitted`；`bwrap` 作为裸机环境可选后端）；`componentIsolation()` 如实上报，缺隔离保持 fail-closed。
  3. **保留并验证完整 HTML / SVG / CSS 表现力**：保留 `policy.ts` 的 TypeScript AST 安全审计（`url(#id)` 本地 SVG 滤镜/渐变/遮罩已放行，保持 `staticFile` 白名单与 `assertDynamicComponentFrames` 校验，并核查 `dynamics.ts` 避免误杀含短开场留白的创意镜头）；全面支持 React + HTML + CSS + 矢量 SVG（`<svg>`、`<path>`、`<polygon>`、`<circle>`、`<rect>`、`<defs>`、`<filter>`/`<feGaussianBlur>`、`<linearGradient>`/`<radialGradient>`、`<clipPath>`、`<mask>`、`spring()`、`interpolate()`、`Easing`、`random()`）及单/多文件 TSX 工程与已固定图片资源。
  4. **向普通对话开放原生工具 + Per-Turn Trace 埋点**：
     - 解除 `apps/api/app/chat/prompts.py`（Lines 83–84、107–108）与 `editor_create.py`（Lines 1089–1096）“仅外部 `ExternalSkillReference` 才开放 `remotion-project`”的限制；
     - 新增 `insert_visual_component(start_seconds, end_seconds, code_or_files, props?, props_schema?, resources?, background?)` 与 `update_visual_component(clip_id, code_or_files?, props_patch?)`（编译/AST/运行诊断以 `source_repairable=True` 返回模型自主修复，并把编译耗时、缓存命中与修复轨迹写入 `apps/api/app/providers/llm/turn_trace.py`）；
     - 新增内置 Skill `generative-motion/SKILL.md`：讲清“原生积木 / 原生 `TextObject` / 代码画笔”三者分工，以及参数化 `props`、模块化时长、确定性帧函数与声画踩点纪律。

#### B. 静图 / 视频定格帧主体抠像
- **新增异步工具 `extract_subject(mode="image" | "freeze_frame")`**（复用既有 `MediaJob` 报价、授权、预占与 Worker fencing 链路）：
  - 输入：`source_id`、`mode`、`at_seconds?`（定格时间点）、`subject_hint?`；
  - 输出：带真实 Alpha 通道的不可变 PNG `SourceSnapshot`（返回 `snapshot_id`、尺寸与实测边界框），复用普通 `ImageObject` 参与叠层与关键帧动画。
- **新增 `layered-compositing/SKILL.md`**：沉淀“定格人物介绍卡（底片 `filter.blur` 关键帧 + 人物透明定格 `transform.scale` 弹入 + 侧边标签滑入 + 快门 Foley）”、“人物定格穿字转场”、“蒙版拉帘对比”等原子组合公式。

---

### 4.3 Phase B3（动态前景合成）：无绿幕视频片段主体抠像（Luma Matte）

- **扩展 `extract_subject(mode="video_clip")`**（严格设单次时长上限与显式报价授权）：
  - Worker 调用视频主体分割模型，对指定源时间窗产出同 fps、同分辨率的 **Luma Matte 黑白遮罩 MP4 `SourceSnapshot`**（规避 WebM Alpha 编解码兼容风险）；
  - `VideoObject` 增加可选 `matte_source_id`，`Video.tsx` 将源视频与 Matte 视频同帧同步渲染进 SVG `<mask>`；
  - 解锁**动态“文字穿人后”**（轨道 0 原片 + 轨道 1 可编辑大号 `TextObject` + 轨道 2 同源带 Matte 前景），后续可继续用自然语言单独修改人后文字内容、颜色或动效。
- 独立验收边界（沿用 `i8.md §4`）：单独核对边缘锯齿/溢色、时序闪烁、编解码耗时、积分计量及失败释放，验收通过后再对外开放。

---

## 5. 前台 C · 首页 Tabs 重构、Vlog 填空 Brief 与标杆 Demo 规划

### 5.1 首页 Tabs 架构（`apps/web/src/components/home/DemoGallery.tsx` & `en.ts` / `zh.ts`）

- **移除独立的「模板 (`templates`)」与旧「口播动效 (`talking-head`)」一级 Tab**；模板绑定能力（`templateReference`）保留在单卡属性上静默生效，不再割裂分类心智。
- **重构为 5 个一级 Tab**（如初期标杆成片少于 10 条，可先合并「产品与演示」与「观点与讲解」为 4 Tab 避免空架）：

| 一级 Tab (`id`) | 中文 / 英文 | 二级 Sub-tab | 主打场景与高级剪辑力 |
| :--- | :--- | :--- | :--- |
| `discover` | 精选 / Discover | 无 | 9:16 与 16:9 混排各品类最佳样片 |
| `vlog` | Vlog 剪辑 / Vlog | `旅拍与转场`、`日常与分屏`、`探店与人物定格` | 实拍精选 + 蒙版转场 + 多机位画中画 + 定格抠像 + 原声/Foley 混音 |
| `visual-craft` | 创意合成 / Visual Craft | `动态图形与代码艺术`、`人物穿字与分层`、`分屏与匹配快剪` | React / TSX + HTML + SVG 受控组件动态设计（形变/点阵波/3D 丝带）、瑞士动态网格、圆形匹配剪辑与抠像分层 |
| `product-promo` | 产品与演示 / Product & Demo | `官网与品牌大片`、`画中画操作演示`、`新品发布` | 网页直采 + Motion Blocks + 录屏局部放大镜蒙版 + 讲解浮窗 |
| `explainers` | 观点与讲解 / Explainers & Talks | `视觉化口播`、`概念与故事拆解` | 去停顿精剪 + 画中画参考浮窗 + `karaoke_focus` 字幕 + 动态图解 |

> **Landing 同步改版清单（随 Milestone 3 首批真实标杆成片同步落地，不提前画饼）**：
> - **Hero 主标题**：保留「探索剪辑的艺术 / Explore the art of the cut.」不变；
> - **Header `Features` 下拉 4 项（`FeatureList.tsx`）**：将第 3 项「模板一键同款」升级为「多层合成与动态设计」（画中画、蒙版、关键帧、变速与自由图形动画），第 1 项升级为「对话式协作精剪」（呼应 Mid-Run `ask_user`），第 2 项升级为「电影调色与影棚声效」；
> - **首屏 `CreationShowcase` 4 Tabs（`content.ts` + `CreationShowcase.tsx`）**：同步切换为 `Vlog 剪辑`、`创意合成`、`产品与演示`、`观点与讲解`，并将竖屏布局判定由硬编码 `item.id === "talking-head"` 改为按 `item.aspect === "9:16"` 驱动；
> - **底部 `LandingSkills`（`LandingSkills.tsx`）**：大标题升级为「从日常实拍，到每一帧的剪辑艺术。」，同步替换 4 组 3:4 氛围剧照（`vlog-1..4.webp`、`visual-craft-1..4.webp` 等）与对应入口；`CreationStory` 与 `FAQ` 保持结构不变，仅在 FAQ 示例补一句旅拍 Vlog。

### 5.2 Hover 浮层与精细化技法填空 Brief（`MentionEditor` 现有 `[必填]` / `[optional:选填]` 语法）

- **核心原则**：高级剪辑技法（瑞士网格、圆形匹配剪辑、日系胶片旅拍等）**不是全局默认值，而是通过精细提示词显式唤起的能力组合**。点「做同款」时，预填文本既用 `[必填]` 槽降低素材/主题输入门槛，又把关键剪辑技法写得明确、可编辑，用户可原样直发复现同款高度，也可自由删改其中任意技法。
- **Hover 轻量信息**：卡片 hover 除自动开声预览与操作按钮（`做同款` / `Make one like this`）外，在按钮上方展示 1 行轻量风格标签（如 `9:16 · 胶片旅拍`、`16:9 · 瑞士动态网格`、`9:16 · 圆形匹配转场`），不遮挡主体画面。
- **精细化技法 Brief 示例**（守住 `RECIPES.md` 合同：引导上传实拍素材、不暴露内部工具名或 Skill 词）：
  - **胶片旅拍 Vlog（对标视频 1）**：`把上传的实拍素材剪成一支电影感旅拍 Vlog，主题与片名：[例如：Sojourn in Nagoya / 周末京都]\n剪辑技法与观感（可选）：[optional:开场 2 秒极速闪切配叠层片名；中段用 1 个居中竖屏画中画叠加在动态背景上；按鼓点切镜并穿插局部慢动作；全片统一富士日系胶片调色，高潮做三词踩拍大字与切镜扫风音效]`
  - **瑞士动态网格大片（对标视频 2）**：`用上传的实拍镜头制作一支瑞士极简网格风格短片，关键词与短句：[例如：HORIZON / GULL / QUIET，及对应 2–3 句短诗]\n网格与视觉节奏（可选）：[optional:白底细线红点 3×3 动态网格随鼓点变形缩放视频视口；中段切换为全屏模糊暗底+中央清晰视口与半透明磨砂条，配粗体压缩红字与轻快律动鼓点]`
  - **圆形蒙版相似形匹配剪辑（对标视频 3）**：`把上传的多段带圆形主体的视频剪成高能相似形匹配快剪，画面顺序或主题：[例如：地球仪 → 吉他音孔 → 沸腾圆锅 → 瞳孔]\n转场与音效设计（可选）：[optional:先把每个圆形主体对齐到画面中心，用圆形蒙版缩放关键帧+镜头快推缩放和切点模糊衔接，并在每个切点叠扫风+重击+低音下潜三层音效]`
  - **探店/日常分屏**：`剪一支探店/日常 Vlog，主角是：[店名、好物或这一天的亮点]\n画面与声音（可选）：[optional:保留关键原声，用圆角画中画和双屏对比展示细节，套用暖调胶片滤镜、轻音乐闪避与胶囊字幕]`
  - **定格人物分层**：`把这段实拍剪出定格创意感，主题是：[想突出的人物或瞬间]\n特效偏好（可选）：[optional:关键瞬间定格抠像弹介绍卡（背景渐变虚化+人物微放大弹入+快门声），或大字穿插在人物身后]`
  - **动态设计师 Showreel（对标视频 4，Phase B2）**：`制作一段 15 秒动态图形作品集短片，品牌或核心主张：[例如：MAKE THINGS MOVE. — with intent. / 你的品牌名]\n视觉母题与节奏（可选）：[optional:黑底极简取景框开场闪切暖白纸底，依次演绎黑色多边形顶点形变+紫粉线框残影、高饱和撞色大字逐行遮罩滑入、暗底蓝橙同心点阵波纹扩散、3D 投影多色发光丝带曲线，最后定版品牌 Logo，全程配电子律动鼓点与切点扫风重击音效]`
  - **视觉化口播**：`精剪我的口播/自拍记录，这一期聊：[核心话题或观点]\n包装方式（可选）：[optional:去掉停顿和口癖，加逐词高亮字幕、重点圆角画中画参考图和每 5 秒轻微推镜]`

### 5.3 首批标杆 Demo 成片矩阵（15–25s，前 2s 强钩子，由 Rookie 真实链路产出）

| 样片 | 归属 Tab | 画幅 / 时长 | 验收必秀能力 |
| :--- | :--- | :--- | :--- |
| **1. 胶片旅拍 Vlog（对标视频 1）** | `vlog` | `16:9` 或 `9:16` · ~22s | 开场极速闪切 + 居中竖屏画中画叠动态背景 + `set_clip_speed` 局部慢放 + `fuji_classic` 调色 + 踩拍三词弹字 + Drumprints 鼓点 & 实录 Foley |
| **2. 瑞士动态网格（对标视频 2）** | `visual-craft` | `16:9` · ~18s | 支持视频源的 `editorial_grid_frame` 动效块 + 底层模糊全屏与中央清晰视口切换 + 踩拍网格变形与杂志排版 |
| **3. 圆形蒙版匹配快剪（对标视频 3）** | `visual-craft` | `9:16` · ~6–12s | `inspect_source_frames` 主体居中对齐 + `set_mask(circle)` 与 `mask.size`/`transform.scale`/`filter.blur` 关键帧 + 三层叠轨 SFX（Swoosh + Impact + Sub Drop） |
| **4. 动态设计师 Showreel（对标视频 4）** *(Phase B2)* | `visual-craft` | `16:9` · ~15s | `insert_visual_component`（React/TSX + HTML + SVG 实现多边形形变+线框残影、点阵波纹场、3D 投影发光丝带）+ 原生撞色大字排版 + 品牌定版 + 电子律动 BGM 与切点音效 |
| **5. 咖啡馆探店双屏** | `vlog` | `9:16` · ~20s | A-Roll 原声 + 圆角画中画/双屏对比 + `kodak_warm` 参数化滤镜 + BGM 自动闪避 + `cinema_glass` 胶囊字幕 |
| **6. 人物定格介绍卡** *(Phase B2)* | `visual-craft` | `9:16` · ~16s | `extract_subject(freeze_frame)` 人物抠像定格 + 背景虚化关键帧 + 侧边标签滑入 + 快门 Foley |
| **7. 视觉化口播精剪** | `explainers` | `9:16` · ~20s | ASR 去停顿 + `karaoke_focus` 逐词高亮 + 关键点圆角画中画参考图弹出 + 轻推镜关键帧 |

> **素材与音乐获取及版权边界**：
> - 严禁抓取含版权流行曲或无商用许可的社媒搬运视频；
> - 实拍视频素材来源：团队自拍或经许可核验的免版权公开库（如 Pexels / Pixabay / Coverr，留存每条素材来源 URL 与许可记录）；
> - 配乐来源：优先复用仓库既有策展曲库（Drumprints 4 首按 CC BY 4.0 保留署名 + 已核清许可的 Shotcraft 曲目，避开待复核的 `bgm-tech-house.mp3`）、经核验的 CC0/CC BY 开源配乐，或自研 `generate_music` / Sound Engine v3 + 36 条 CC0 Foley。

---

## 6. 施工顺序与逐阶段验收门禁（按商业交付收益重排）

| 阶段 | 施工内容 | 确定性门禁 | 真实浏览器 & 视听验收 |
| :--- | :--- | :--- | :--- |
| **Stage 1 · 底座 A（Mid-Run & 修改轮 `ask_user`）** | `ask_user` 全量解绑（`prompts.py:351/492/493/497`、`plan_turn.py:860-896`、`video_editor.j2`，对齐最新导出即交付流程）+ 修复 `_continue_chat_answer` 重复拼接 `opening.content` + 无模式 `settled_user_decisions` 对话投影（防后续修改轮失忆回退）+ 续行静音直调工具 + `liveState.ts` / `ChatConversation.tsx` 进行态保持与轨内 Q&A 折叠 + `confirm_credits` 正交测试 + Per-Turn Trace 埋点 | `make test-fast`、`make test-chat`、`make test-web`、`make test-e2e` | Chrome 实测：① 多步执行中途与成片后模糊修改轮均可弹出自由多题卡，顶栏（展开与收起态）保持 ing 不出现 `Worked for Xs`；② 刷新页面挂起态与步骤不丢；③ 回答后 Q&A 收进同一工作轨、续行不重做已保存版本且后续第 2/3 轮修改仍记住已拍板决定；④ `confirm_credits` 与 `ask_user` 严格正交 |
| **Stage 2 · 底座 B2-A（提前！React/TSX + HTML + SVG 代码画笔）** | 解锁并升级 `remotion-project`：`bake.ts` 单槽硬拒改为有界 FIFO 队列 + 跨平台 Chromium 路径 + Linux 生产无网 Sidecar 隔离（保留本地 macOS Seatbelt）+ `insert_visual_component` / `update_visual_component`（支持 `props_patch` 参数化微调，严防做成“半个 OpenFilm”）+ `generative-motion/SKILL.md` + Per-Turn Trace 烘焙/修复诊断。**完成 Stage 1 + Stage 2 即达到可直接给领导演示的视觉跃升交付点** | `make test-api`、`make test-render`、`make test-web`（含 AST 安全审计、并发队列排队、隔离逃逸/断网/超时、确定性帧与 `props_patch` 重烘回归） | ① 真实跑出 15 秒 React/SVG 动态设计师 Showreel（多边形形变+线框残影、点阵波场、3D 发光丝带）及带定制粒子/微交互幕的商业官网宣传片；② 验证 `update_visual_component(props_patch=...)` 精准改字号/配色/文案不漂移且周围音轨字幕不动；③ 验证原生 `TextObject` 字幕叠在代码画笔之上可 0ms 单独修改 |
| **Stage 3A · 底座 B1（Vlog 高级剪辑原语）** | `playback_rate`/`color_grade`（Top 10 目录 + 参数微调）/`crop`/`frame`/`mask` Schema + `Video.tsx` 渲染 + `MotionBlockObject` 视频源挂载与 `editorial_grid_frame` + `insert_visual` 视频 PiP + `set_layer_order` + `animate_object` + `set_mask` + `set_clip_speed` + `set_color_grade` + `inspect_source_frames` + `vlog-editing` & 升级 `talking-head-video` Skills | `make test-all`（含 Py↔TS Zod/动画/蒙版/滤镜/变速 parity 与旧 digest 零漂移） | 真实上传实拍素材走 `/api/v1/chat`，分别跑通：① 胶片旅拍 Vlog（居中画中画 + 局部变速 + `fuji_classic` 微调）；② 瑞士动态网格视频块；③ 圆形蒙版相似形匹配快剪；验证 Web Player 与 1080p MP4 逐帧对齐及单对象续改 |
| **Stage 3B · 底座 B2-B → B3 & 前台 C（抠像与首页重构）** | **B2-B**：`extract_subject(image \| freeze_frame)` + `layered-compositing` Skill；**B3**：独立启动 `extract_subject(video_clip)` Luma Matte 管线与边缘/时序/成本专项验收；**前台 C**：隐藏「模板」Tab，重构 `DemoGallery.tsx` 与 Landing，上架首批真实标杆成片 | `make test-api`、`make test-web`（含 EN↔ZH 键与槽位 parity）、`make test-e2e` | ① 核对定格/视频抠像在 Web Player 与 1080p MP4 中的透明边缘、文字穿人后可二次改字及积分台账；② Chrome 实测桌面/手机、中英、明暗、reduced-motion 下的混画幅播放与填空 Brief |
