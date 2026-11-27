# Batch 3 · Mid-Run Ask User、高级剪辑原语与 Vlog 首页演示（施工合同）

> **状态（2026-11-27）**：DRAFT（待确认开工）。本合同整合三项强关联施工块：① **底座 A · 执行中 `ask_user` 同轨挂起与无感续跑**；② **底座 B · 双引擎视觉生产底座**——**B1 实拍高级剪辑原语**（画中画、层序、关键帧、蒙版、Clip 级通用变速、Top 10 参数化滤镜预设层、支持视频源的 Motion Block、源视频抽帧感知）、**B2 React / TSX + HTML + SVG 受控代码画笔（解锁并跨平台化现有 `remotion-project` 运行时）+ 定格抠像**、**B3 视频主体抠像（Luma Matte）** 及配套 Skills；③ **前台 C · 隐藏「模板」Tab，重构面向高级剪辑力、Vlog 与动态设计的首页演示货架、精细化技法填空 Brief 与真实标杆成片**。
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

## 3. 底座 A · Mid-Run `ask_user` 同轨挂起与无感续跑

### 3.1 解除现有 4 处过度限制（Backend）

| 目标文件 | 现状限制 | 改造方案 |
| :--- | :--- | :--- |
| `apps/api/app/chat/prompts.py` | ① `not native_creation` 时裁剪 `items`；② `authorized_media.status == "available"` 时 `discard("ask_user")` | ① 制作/编辑阶段全量开放 `ask_user` 的 `items` 多题数组；② 仅在“已导出固定 MP4 且仅剩 `review_video/deliver_video`”的窄收尾分支限制 `ask_user`，其余创作/修订/媒体就绪后阶段均允许调用 `ask_user` |
| `apps/api/app/chat/plan_turn.py` & `apps/api/app/models/schemas.py` | `missing_brief_question_items` 强制把 `items` 绑定到旧 `Brief` 固定槽位，临时剪辑问题被拒；同 `slot` 二次提问被拒 | 保留已知 `Brief` 槽位自动回填兼容，同时支持 **自由临时题（ad-hoc item）**（`slot` 可为可选字段或普通 `topic_key`，不再强制校验必须属于旧 `Brief` 字段集）；不阻断制作中基于新素材/新预览产生的合法追问 |
| `apps/api/app/chat/service.py` & `routes.py` | 调 `ask_user` 后终止并结算当前步骤；`/answer` 续行在视觉上新起一轮 | ① 持久化问题行携带 `mid_run_ask: true` 与所属 `opening_id` / 当前 `steps` 快照（**不把 `in_progress` 步骤误结为 `done`**）；② `/answer` 提交答案后沿原 `opening_id`、`steps`、已保存版本与已完成的工具回执继续拉起 `ToolLoop` |
| `apps/api/app/prompts/chat/video_editor.j2` | 明文禁止“确认卡后再问第二次”、禁止弹卡前调 `update_steps` | 改写为**克制提问宪法**：① 允许在 `update_steps` 展开的多步执行中途发起单卡 `ask_user`（遇多段素材选片、定格抠像选帧、原声/配乐取舍、明显审美分叉时）；② 纯技术参数（坐标、缓动、音效配方、闪避 dB）严禁打扰用户；③ 每次提问必给 `recommended_id` 与 `default_path`（一键跳过按推荐继续） |

### 3.2 续行返回 Agentic Loop 的自由响应策略

用户提交 `ask_user` 答案并进入续行 `ToolLoop` 后，**模型完全自主决定是否输出过渡文本**：
- **静音直调工具（允许零前置 prose）**：模型可以直接根据用户答案立即发出下一批工具调用（如 `insert_visual` / `extract_subject` / `create_video`），不强制吐一句“好的我收到了”，也不触发空文本异常；
- **简短确认 + 调工具**：模型也可以先用 1 句自然确认句交代即将执行的动作，再并行调用工具；
- **直接文本答复结束**：若用户的回答明确要求取消、仅回答问题或不再继续制作，模型可直接正文答复结束，不误触发 `bare_production_feedback` 强逼继续导出。

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

### 4.2 Phase B2（两条王炸进阶能力）：React / TSX + HTML + SVG 代码画笔 + 静图/定格主体抠像

#### A. 解锁并跨平台化现有 `remotion-project` 受控组件运行时（HTML / SVG / CSS / React）
严禁使用低表现力的自定义光栅指令（放弃扩写 `draw-2d` PIL 光栅方案），直接启用并补齐仓库已有的 **React + TSX + HTML + SVG + CSS** 组件烘焙管线（`apps/render/src/component-runtime/{policy,worker,bake}.ts` + `apps/api/app/tools/video/components.py`）：
- **补齐 Linux 生产隔离与跨平台路径（解除当前仅 macOS Seatbelt 阻塞）**：
  - 修正 `bake.ts` 与 `worker.ts` 中硬编码的 `mac-arm64`/`mac-x64` Chrome Headless Shell 路径，改为跨平台自动解析（macOS / Linux x86_64 / Linux ARM64）；
  - 保留本地 macOS `sandbox-exec` 隔离，同时在 Linux 生产环境（`apps/render/Dockerfile`）新增标准内核级隔离方案：**`bubblewrap (bwrap)` 无网只读沙箱**（`--unshare-net`、只读挂载运行依赖、仅 `<work>` 目录可写、`--die-with-parent` + `ulimit` CPU/RSS/文件上限 + 清空业务环境变量）或**独立无网 `component-runner` Sidecar 容器**（`network_mode: none` / 内部只读）；`componentIsolation()` 如实上报当前隔离类型，缺失合法隔离时保持 fail-closed。
- **验证并开放完整 HTML / SVG / CSS 表现力（保留 AST 安全白名单）**：
  - 保留 `policy.ts` 的 TypeScript AST 安全审计（禁止 `fetch`/`process`/`eval`/`window`/`document`/`setTimeout`/裸 `<img>`/`<iframe>`/`<script>`，保持 `staticFile` 白名单防线与 `assertDynamicComponentFrames` 防静帧校验）；
  - 明确支持完整 React + HTML + CSS + 矢量 SVG 语法（`<svg>`、`<path>`、`<polygon>`、`<circle>`、`<rect>`、`<defs>`、`<filter>`/`<feGaussianBlur>`、`<linearGradient>`/`<radialGradient>`、`<clipPath>`、`<mask>`、CSS 排版/渐变/混合模式、`spring()`、`interpolate()`、`Easing`、`random()`），同时支持单文件组件与多文件 TSX 工程、以及引用项目已固定的静态图片资源。
- **向普通对话开放原生工具 `insert_visual_component` & `update_visual_component`**：
  - 解除当前 `prompts.py` 中“仅绑定外部 `ExternalSkillReference` 才开放 `remotion-project`”的限制，允许 Agent 在普通创作与修订轮直接编写 React/TSX/HTML/SVG 场景；
  - `insert_visual_component(start_seconds, end_seconds, code_or_files, parameters?, resources?, background?, layer?)`：在事务外经隔离渲染器烘焙为不可变固定视频与 `SourceSnapshot`，生成 `GeneratorObject(producer="remotion-project")` 原子落轨（精确 `program_digest` 命中缓存零重算）；
  - `update_visual_component(clip_id, code_or_files?, parameters?)`：保留时间位置、层序与周围音画，仅改 React/TSX/SVG 代码或参数重新烘焙，配合 `preview_range` 看帧闭环迭代；编译/AST/运行诊断以 `source_repairable=True` 返回模型自主修复。
- **新增内置 Skill `generative-motion/SKILL.md`**：教 Agent 合理分工（常规界面/产品演示/字幕优先用原生 `MotionBlockObject` 与 `TextObject`；多边形形变、点阵波场、3D 投影 SVG 丝带、实验排版等自由创意 MG 用 `insert_visual_component` 编写纯帧驱动 React + SVG + HTML），并约束确定性时间函数、构图留白、色彩对比与 Sound Engine 声画踩点纪律。

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

## 6. 施工顺序与逐阶段验收门禁

| 阶段 | 施工内容 | 确定性门禁 | 真实浏览器 & 视听验收 |
| :--- | :--- | :--- | :--- |
| **Milestone 1 · 底座 A** | `ask_user` 解绑（`prompts.py` / `plan_turn.py` / `service.py` / `video_editor.j2`）+ 续行静音直调工具支持 + `liveState.ts` / `ChatConversation.tsx` 进行态保持与轨内 Q&A 折叠 + `confirm_credits` 正交回归测试 | `make test-fast`、`make test-chat`、`make test-web`、`make test-e2e` | Chrome 实测：① 多步执行中途弹出自由多题卡，顶栏（展开与收起态）均保持 ing 不出现 `Worked for Xs`；② 刷新页面后挂起态与步骤不丢；③ 回答后 Q&A 收进同一工作轨、模型可直接调工具继续；④ `confirm_credits=auto` 下仍正常弹创作 `ask_user`，`confirm_credits=ask` 下付费导出仍独立弹授权卡且不可被纯文字绕过 |
| **Milestone 2 · 底座 B1** | `playback_rate`/`color_grade`（Top 10 目录 + 参数微调）/`crop`/`frame`/`mask` Schema + `Video.tsx` 渲染 + `MotionBlockObject` 视频源挂载与 `editorial_grid_frame` + `insert_visual` 视频 PiP + `set_layer_order` + `animate_object` + `set_mask` + `set_clip_speed` + `set_color_grade` + `inspect_source_frames` + `vlog-editing` & 升级 `talking-head-video` Skills | `make test-all`（含 Py↔TS Zod/动画/蒙版/滤镜/变速 parity 与旧 digest 零漂移） | 真实上传实拍素材走 `/api/v1/chat`，分别跑通：① 胶片旅拍 Vlog（含居中画中画 + 局部变速 + `fuji_classic` 参数微调）；② 瑞士动态网格视频块；③ 圆形蒙版相似形匹配快剪（对齐中心 + 圆形蒙版关键帧 + 三层音效）；验证 Web Player 与 1080p MP4 逐帧对齐及单对象续改 |
| **Milestone 3 · 前台 C** | 隐藏「模板」Tab，重构 `DemoGallery.tsx` 分类与 hover 标签、更新 `en.ts`/`zh.ts` 填空 Brief、上架首批真实产出的 Vlog 与创意合成标杆成片 | `make test-web`（含 EN↔ZH 键与槽位 parity）、`make test-e2e` | Chrome 实测桌面/手机、中英、明暗、reduced-motion 下的混画幅播放、hover 开声与静音互斥、点击预填填空 Brief（零自动发请求） |
| **Milestone 4 · 底座 B2 → B3** | **B2**：跨平台化并解锁 `remotion-project`（Linux `bwrap` / 无网 Sidecar 隔离 + 跨平台 Chromium 路径 + React/TSX/HTML/SVG 完整矢量支持 + `insert_visual_component` / `update_visual_component` + `generative-motion` Skill）与 `extract_subject(image \| freeze_frame)` + `layered-compositing` Skill，产出「动态设计师 Showreel（视频 4）」与「人物定格介绍卡」；**B3**：独立启动 `extract_subject(video_clip)` Luma Matte 管线与边缘/时序/成本专项验收 | `make test-api`、`make test-render`、`make test-web`（含 AST 策略安全、Linux `bwrap` 隔离逃逸/断网/超时测试与确定性帧回归） | ① 实测 15 秒 React/SVG 动态设计师 Showreel（多边形形变+线框残影、点阵波场、3D 发光丝带）及 `update_visual_component` 二次自然语言改色/改节奏；② 核对定格/视频抠像在 Web Player 与 1080p MP4 中的透明边缘、文字穿人后可二次改字，以及积分预占/实扣/取消释放台账 |
