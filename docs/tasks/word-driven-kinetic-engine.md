# 词级旁白驱动与活态动效基座升级（Word-Driven Kinetic Engine）

> 状态：已评审定稿，可按 Batch 1 → Batch 2 分批施工。
> 前置基线：Commit `9405b628`（已接通 Playwright 真实 CSS `canvas_bg`、MiniMax `subtitle_type="word"` 声学词级时间戳、`resolve_motion_block_cue_phrases` 基础解算、`preview_range` 转场边界双向贴齐）。

---

## 1. 背景与核心问题

对比标杆级旁白驱动宣传片（如 Gemini 4 动效发布片），我们当前系统虽已通过 `9405b628` 拿到 MiniMax 真实毫秒词级时间戳并修复了 `metric_grid` 的初步卡点，但在真实成片中仍存在 6 个导致“PPT 感”的基座短板：

1. **动画死静区（Dead Hold）**：`MetricGrid`、`StepTimelineBlock`、`BentoFeaturesBlock`、`FlowDiagramBlock`、`SplitCompareBlock` 只有一次 `0.35s` 入场弹簧，落定后全屏静止干等旁白；且念到第 2 张卡时，第 1 张卡不退焦、当前卡无活跃高亮。
2. **大量积木仍写死百分比时间**：
   - `BrowserUrlLoad`（`packages/video-remotion/src/blocks/InteractiveBlocks.tsx`）写死 `0.055..0.415` 打字与 `0.44..0.81` 揭示；
   - `ZoomFollowsClick` 写死 `click = durSec * (click_at_ratio ?? 0.4)`；
   - `CursorMagneticClick` 写死 `click = durSec * 0.48`；
   - `KineticBeatBlock`（`typewriter_swap` / `slot_flip`）按 `progress * words.length` 匀速切词；
   - `StatementHookBlock` 开场 `0.8s` 刷完所有字后静止干等。
3. **同一产品界面反复硬切静态截图**：`ProductShowcase` 的 `focus_x / focus_y / zoom_scale` 是整幕静态常量，`callout_steps[]` 只能原地闪框，不能随旁白关键词在同一工作台上平滑推拉平移。
4. **声画 1-to-1 契约缺失（孤儿元素 & 数字口误 & 弹卡无微音效）**：
   - 真实案例：口播只念了 2 个指标（`£18.7m`、`94%`），`metric_grid` 却塞了第 3 张从未被提及的孤儿卡 `03 待审阅`；口播把 `£18.7m` 念成 `一千八百万英镑`；2.5 秒口播的 `split_compare` 硬塞 6 条文字；
   - `create_video` 未把幕内弹卡/点击/高亮的绝对秒数回传给 `generate_sfx`，导致微音效无法帧级对齐幕内动画。
5. **`1 幕 = 1 段割裂 TTS` 枷锁**（Batch 2 解决）：目前每个视觉 `motion_block` 强绑一段独立 TTS + `0.45s` 留白，无法做到“人声一气呵成连续说话、画面在句中按关键词连续切态/转场”。

---

## 2. 铁律：严禁过度设计与防御性编程

施工必须严格遵守以下红线，违者返工：

1. **禁止新增冗余工具**：严禁创建 `prepare_narration_script` 或任何重复语音工具。语音合成只增强现有 `generate_voice`，成稿只增强现有 `create_video`。
2. **禁止过度抽象**：严禁新增抽象基类、策略模式、通用 Choreographer 框架、多余中间层文件或配置注册表。所有修改就地落在现有文件内，保持与周边代码风格一致。
3. **禁止膨胀“上帝块”**：严禁在 `product_showcase` 平级新增 `camera_steps[]` 重复数组；直接在现有 `callout_steps[]` 上加 1 个可选字段 `zoom_scale` 复用已有 `(x, y, start_s, end_s, label)`。
4. **禁止防御性编程与吞错**：
   - 严禁写宽泛 `try/except Exception: pass` 或无意义的 `if isinstance(...)` 多重套娃兜底来掩盖 schema 不一致；
   - 只在明确的外部数据边界（模型输入、可选历史字段 `None`）做最小化处理，内部契约违背直接暴露错误。
5. **严格向后兼容 & 严守 `.strict()` 双端契约**：
   - 所有新增 Schema 字段必须为**可选**（Python：`default=None, exclude_if=lambda v: v is None` 或 `not v`；TS Zod：`.optional()` / `.nullish()`）；
   - 保留原有字段（如 `click_at_ratio`、`callout_steps[].start_s/end_s`），确保历史 `CompositionVersion`、`apps/api/app/skills/blueprint.py`、`slot_preview.py` 和 `kinetic-launch`（无旁白）100% 不受破坏。
6. **严禁碰无关文件**：工作区存在未提交的支付/充值改动（`payment*`、`credits/*`、`docs/PAYMENTS.md`、`docs/tasks/advanced-editing-vlog-and-midrun-ask.md`），**绝对不要修改或暂存这些文件**。

---

## 3. Batch 1 施工详设（模块 2 + 模块 3 + 模块 4）

> Batch 1 不改 Worker 队列，只动 Remotion 渲染引擎、Py↔TS Schema、`editor_create.py` / `catalog.py`、`brand-promo/SKILL.md`。改完只需重启 `apps/render` 刷新打包缓存。

### 模块 2：Remotion 活态引擎 & 全积木吃词级时间轴

#### 2.1 Py↔TS Schema 双端同步（仅新增可选字段）
涉及文件：
- `apps/api/app/editing/schemas.py`
- `packages/video-spec/src/schema.ts`
- `apps/api/app/editing/catalog.py`
- `apps/api/app/chat/editor_create.py`

精确字段清单：
1. `CursorMagneticClickProps`（`schemas.py` & `schema.ts` `interactiveProps.cursor_magnetic_click`）：
   - 新增可选 `click_at_s: CueSecond | None`（TS: `z.number().finite().min(0).optional()`）。
   - `resolve_motion_block_cue_phrases` 支持消耗 `cue_phrase` → 写入 `click_at_s`（提前 `0.08s`）。
2. `ZoomFollowsClickProps`（`schemas.py` & `schema.ts` `interactiveProps.zoom_follows_click`）：
   - 新增可选 `click_at_s: CueSecond | None`（TS: `z.number().finite().min(0).optional()`）；保留 `click_at_ratio` 兼容旧稿。
   - `resolve_motion_block_cue_phrases` 支持消耗 `cue_phrase` → 写入 `click_at_s`。
3. `BrowserUrlLoadProps`（`schemas.py` & `schema.ts` `interactiveProps.browser_url_load`）：
   - 新增可选 `type_at_s: CueSecond | None`、`load_at_s: CueSecond | None`（TS: 均为 `z.number().finite().min(0).optional()`）。
   - `resolve_motion_block_cue_phrases` 支持消耗 `type_cue_phrase` → `type_at_s`、`load_cue_phrase` → `load_at_s`（并兼容单 `cue_phrase` → `load_at_s`）。
4. `KineticBeatProps`（`schemas.py`，并在 `packages/video-remotion/src/blocks/KineticBeatBlock.tsx` `Props` 镜像）：
   - 新增可选 `word_reveals_s: list[CueSecond] | None = Field(default=None, exclude_if=lambda v: not v)`（长度若存在须与 `words` 一致且非递减）。
   - `resolve_motion_block_cue_phrases`：在 `typewriter_swap` / `slot_flip` 且有旁白时，按 `words[]`（或 `word_cues[]` 若模型提供，解算后剥离）查词级时间轴写入 `word_reveals_s`。
5. `StatementHookProps`（`schemas.py`，并在 `packages/video-remotion/src/MotionBlocks.tsx` `StatementHookBlock` 镜像）：
   - 新增可选 `word_reveals_s: list[CueSecond] | None = Field(default=None, exclude_if=lambda v: not v)`（与 `tokenizeLine(headline)` 对齐的短语/词出现秒数）。
   - `resolve_motion_block_cue_phrases`：若本幕有旁白，把 `headline` 的短语/词匹配到词级时间轴生成 `word_reveals_s`（匹配不足半数时按口播实测时长均匀铺开到口播前 75%，避免 `0.8s` 刷完干等 2 秒）。

#### 2.2 Remotion 渲染层活态化（禁止花哨堆料，只做精准动效）
涉及文件：
- `packages/video-remotion/src/blocks/Stage.tsx`
- `packages/video-remotion/src/blocks/InteractiveBlocks.tsx`
- `packages/video-remotion/src/blocks/KineticBeatBlock.tsx`
- `packages/video-remotion/src/MotionBlocks.tsx`（`MetricGridBlock`、`StatementHookBlock`、`ProductShowcaseBlock`）
- `packages/video-remotion/src/blocks/StepTimelineBlock.tsx`
- `packages/video-remotion/src/blocks/BentoFeaturesBlock.tsx`
- `packages/video-remotion/src/blocks/FlowDiagramBlock.tsx`
- `packages/video-remotion/src/blocks/SplitCompareBlock.tsx`

精确渲染行为：
1. **全交互块吃词时间戳**：
   - `CursorMagneticClick`：`const click = props.click_at_s ?? frame.durSec * 0.48;`
   - `ZoomFollowsClick`：`const click = props.click_at_s ?? frame.durSec * (props.click_at_ratio ?? 0.4);`
   - `BrowserUrlLoad`：若传入 `type_at_s` / `load_at_s`，按绝对秒数驱动打字起止与页面加载揭示，否则回退原百分比逻辑。
   - `KineticBeatBlock`（`typewriter_swap` / `slot_flip`）：若存在 `props.word_reveals_s` 且长度匹配 `words`，按当前 `t` 落在哪个区间 `[word_reveals_s[i], word_reveals_s[i+1])` 计算 `index` 和 `phase`；否则回退原匀速逻辑。
   - `StatementHookBlock`：若存在 `props.word_reveals_s`，每个词的入场延迟改用 `word_reveals_s[i]`（而非固定 `i * 0.06`），`highlight_phrase` 在 `highlight_at_s` 瞬间扫光点亮。
2. **Active Focus 活跃焦点演进（写 1 个 10 行小函数放在 `Stage.tsx` 供列表块复用，不造框架）**：
   - 函数 `activeFocusStyle(tSec, itemTimes, index, durSec)`:
     - 找出当前正在被讲述的 `activeIdx`（最后一个 `itemTimes[i] <= tSec` 的项）；
     - 若所有项都已入场且距幕尾不足 `0.5s`（收束态），全部柔和回正（`opacity: 1, scale: 1`）；
     - 否则：当前 `index === activeIdx` 获得 `scale: 1.025`（加轻微平滑插值）+ 满不透明度；已讲完的 `index < activeIdx` 柔和退焦到 `opacity: 0.78, scale: 0.99`；未到的保持原隐藏态。
   - 接入 `MetricGridBlock`、`StepTimelineBlock`、`BentoFeaturesBlock`、`FlowDiagramBlock`、`SplitCompareBlock`。
3. **Stage 极轻连续呼吸 + 幕尾势能**：
   - 在 `Stage.tsx` 内容容器（1920×1080）上叠加极克制的连续微推进：`const breath = 1 + 0.018 * clamp01(frame.tSec / Math.max(frame.durSec, 0.5));`，彻底消灭最后 1 秒像素完全纹丝不动的死静感；
   - 注意：`ProductShowcase` 已有独立 `evaluateCamera`，不要双重缩放。

---

### 模块 3：连续舞台运镜（轻量扩展 `callout_steps[].zoom_scale`）

涉及文件：
- `apps/api/app/editing/schemas.py`（`ShowcaseStep`）
- `apps/api/app/editing/catalog.py`（`product_showcase.desc`）
- `packages/video-remotion/src/MotionBlocks.tsx`（`ProductShowcaseBlock`）

精确设计：
1. 在 `ShowcaseStep`（`schemas.py:684`）新增 1 个可选字段：
   - `zoom_scale: float | None = Field(default=None, ge=1.0, le=2.2, allow_inf_nan=False, exclude_if=lambda v: v is None)`
2. 在 `ProductShowcaseBlock`（`MotionBlocks.tsx:120-200`）中：
   - 当 `props.callout_steps` 非空且至少有一个 step 指定了 `zoom_scale`（或 `callout_steps.length >= 2`）时：
     - 计算当前 `cueSec` 对应的目标焦点 `(targetFocusX, targetFocusY, targetZoom)`：
       - 若落在某个 `step` 内：`targetFocusX = step.x + step.width / 2`，`targetFocusY = step.y + step.height / 2`，`targetZoom = step.zoom_scale ?? Math.max(zoomScale, 1.32)`；
       - 在相邻 step 之间或进入首个 step 前 `0.45s` 内，使用 `easeInOutCubic` 在前一个焦点（初始为 `focusX, focusY, zoomScale`）与目标焦点间平滑插值，再喂给 `evaluateCamera`（将 `evaluateCamera` 的 `zoomScale` 上限从 `1.35` 放宽到 `2.2` 仅在 step 驱动时生效，且保证视口边缘不露黑边）。
   - 无 `callout_steps` 或 `camera_preset === "scroll_reveal"` 时保持原逻辑 100% 不变。

---

### 模块 4：声画 1-to-1 诊断回执 + 幕内微音效坐标 + 文案对位规范

涉及文件：
- `apps/api/app/chat/editor_create.py`
- `apps/api/app/skills/brand-promo/SKILL.md`
- `apps/api/app/prompts/chat/video_editor.j2`

精确设计（区分「硬拦截」与「软诊断」，严禁诱发 `create_video` 3 次止损）：
1. **`create_video` 返回 `resolved_visual_cues`**：
   - 收集全片所有已解算的幕内视觉事件绝对秒数（最多 32 条，按时间排序）：
     `{"act_index", "clip_id", "block_id", "kind": "reveal"|"callout"|"cursor_click"|"word_flip", "label", "at_seconds"}`
   - 模型在后续批量调用 `generate_sfx` 时，除了幕间切点，可以直接把微音效（`select_tick` / `ui_pop`）精准对齐到 `resolved_visual_cues[].at_seconds`。
2. **`create_video` 返回 `sync_warnings`（结构化诊断，不阻塞保存 v1）**：
   - **孤儿条目检测（Orphan Item）**：对有旁白的 `metric_grid` / `step_timeline` / `bento_features` / `flow_diagram` / `split_compare` / `data_chart`，若条目数 `>= 2`，记录哪些条目既无 `cue_phrase` 命中、也无自动关键词命中（例：`act[3] metric_grid item[2] ("03 待审阅") was not mentioned in narration; remove it or add it to narration.`）。
   - **数字精度一致性检测（Numeric Parity）**：提取视觉条目 `value` 中的数字（如 `18.7`、`94`、`27`），经中英数字归一化后检查本幕 `narration`：若存在近似数字但丢小数/偏差（如画面 `18.7`，旁白只出现 `18` / `十八` / `一千八百` 而无 `.7`/`七`），输出精确告警。
   - **信息密度检测（Density Warning）**：若列表条目数 > `max(2, floor(spoken_seconds / 0.9))`（如 2.5s 口播塞 6 条），输出过密告警。
   - **死静帧检测（Dead Hold Warning）**：对无 `callout_steps` 且无 `scroll_reveal` 的数据/排版幕，若最后一个视觉事件完成后距幕尾超过 `1.3s` 且占比 `> 38%`，输出静帧告警。
   - **唯一新增硬拦截**：仅拦截「模型显式传了 `cue_phrase`，但该短语在本幕 `narration` 中完全找不到（含数字归一化后仍找不到）」——此时无需阻断整稿，记入 `sync_warnings` 并在 observation 中明确标出（防止模型因单个拼写偏差炸掉整轮 `create_video`）。
3. **升级 `brand-promo/SKILL.md` 与 `video_editor.j2`**：
   - 在 `brand-promo/SKILL.md` 增加「声画 1-to-1 对位法」：
     - 画面列几张卡/几个步骤，口播必须按同顺序、同数量、精确数字念出来（绝不出现旁白没念的孤儿卡，`£18.7m` 必念「一千八百七十万英镑」而非「一千八百万」）；
     - 30–45s 成片中主动安排 1 段 `2–3.5s` 无旁白视觉节奏段，打破播音腔；
     - 收到 `create_video` 返回的 `sync_warnings`（尤其是孤儿卡、数字误差）后，在预览前用 `update_motion_block` / 修订立刻清零；并参考 `resolved_visual_cues` 给核心弹卡与点击铺 3–5 处幕内微音效。

---

## 4. Batch 2 施工详设（模块 1：连续口播轨 + 句中词锚定切镜）

> Batch 2 涉及 `media_jobs.py` / `narration.py`，改完需重启 **API + Worker**。在 Batch 1 验收通过后再执行，或作为独立 Commit 落地。

### 1.1 升级现有 `generate_voice`（不新增工具）
涉及文件：
- `apps/api/app/chat/editor.py`（`GenerateVoiceArgs`）
- `apps/api/app/tools/video/narration.py`（`narration_original_request_key`、`narration_original_quote_characters`）
- `apps/api/app/pipeline/media_jobs.py`（`media_quote`、`_voice`）
- `apps/api/app/chat/editor_media.py`（`_record_audio`）

精确改动：
1. `GenerateVoiceArgs` 新增可选 `speed: float = Field(default=1.0, ge=0.5, le=2.0)` 与 `emotion: str | None = Field(default=None)`。
2. **关键防炸点**：`media_jobs.py:55` 的 `media_quote` 会用 `narration_original_request_key(**voice_params)`——必须同步给 `narration_original_request_key` 与 `narration_original_quote_characters` 增加带默认值的可选参数 `speed: float = 1.0, emotion: str | None = None`，并在内部透传给 `narration_synth_config(speed=speed, emotion=emotion)`；`_voice()` 同步把 `speed` / `emotion` 传给 `SpeechObject`。
3. `_record_audio` 保持前端既有 `MediaJob` 回执字段 100% 不变（保护 `apps/web` 的 `AUDIO_PREVIEW_TOOLS` 与 mount tests），仅在返回给模型的 JSON observation 里附加精简 `word_cues`（按短语/词聚合后的 `[{text, start_s, end_s}]`，避免塞几百条单字 JSON 爆上下文）。

### 1.2 `create_video` 支持连续口播轨 + 词锚定句中切镜
涉及文件：
- `apps/api/app/chat/editor_create.py`
- `apps/api/app/skills/brand-promo/SKILL.md`

精确改动：
1. `CreateVideoArgs` 新增可选字段 `voiceover_snapshot_id: UUID | None = None`（指向 `generate_voice` 产出的已固定音频 `SourceSnapshot`）。
2. `MotionBlockDraft` 新增可选字段：
   - `start_cue_phrase: str | None = None`
   - `end_cue_phrase: str | None = None`
3. 当 `voiceover_snapshot_id` 传入时：
   - 从该 `SourceSnapshot.meta` 读取完整 `text`、`duration_s`、`cues`（含 `words`）；
   - 将整条连续音频作为单一 `AudioObject` 铺入 `trk_dialogue`（`[0.15s, 0.15s + duration_s]`），并一次性生成全局精确同步的 `trk_caption`（支持 `caption_translations` 双语）；
   - 每个 `motion_block` 若声明了 `start_cue_phrase` / `end_cue_phrase`，通过 `resolve_cue_phrase_window_s` 将其切镜边界精确锚定在连续口播的词毫秒上（相邻幕首尾自动闭合、零缝隙），同时将该幕区间内的局部 `narration` 与偏移后的 `cues` 传入 `resolve_motion_block_cue_phrases`，实现**一句话不中断、画面随词在句中连续切镜与弹卡**；
   - 未传 `voiceover_snapshot_id` 时，原有逐幕 `narration` 与纯音乐 `kinetic-launch` 路径保持 100% 不变。

---

## 5. 全仓库验证与验收标准

每完成一个 Batch，必须全部通过：
1. **自动化验证**：
   - `make test-fast`（API 全套单测 + `@repurposer/video-spec` + `@repurposer/sound-engine` + Web `tsc`）
   - 若触及前端文件或 `video-spec` 类型，追加 `make test-web`
   - 补写精准单元测试（覆盖 Py↔TS Schema strict 校验、`callout_steps[].zoom_scale`、`sync_warnings` 孤儿卡与数字精度、`resolved_visual_cues`、`generate_voice(speed, emotion)` 防 `TypeError`、`voiceover_snapshot_id` 句中切镜），不写水分测试。
2. **重启与真实端到端验证**：
   - Batch 1 完成后：**重启 `apps/render`**，用现有已渲染项目或新建项目跑通真实渲染与 MP4 导出，抽帧核验：
     - `ProductShowcase` 多 step 平滑推拉运镜；
     - `MetricGrid` / `StepTimeline` 的 Active Focus 焦点切换（当前卡高亮微抬，前序卡柔和退焦）；
     - `sync_warnings` 在真实稿件中能清零孤儿卡。
   - Batch 2 完成后：**重启 Worker**，用 `generate_voice` → `create_video(voiceover_snapshot_id=...)` 跑通一条真实连续口播句中切镜 MP4。
