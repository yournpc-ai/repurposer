# recipe-cards-r1 实施简报——caption catalog + stacking preset + dub 配方接线 + 首页卡片层

> Status: ✅ 已落地（2026-07-31：caption catalog + stacking preset + dub 接线 + 首页卡片层，见 RECIPES.md §8）
> 依据：`docs/RECIPES.md` §2（三层正交）/§3（caption catalog）/§4.1（dub 卡）/§7（卡片层）/§8 R1/§10（禁令）；`CHAT_ARCHITECTURE.md` §4（registry 纪律）；`NAMING.md`（宪法 + §5 审计触发）
> 迁移：**零表迁移**——dub_languages 全住 JSON 载荷层（pending_intent / GenerateRequest / TaskSpec / run.context）；catalog 是代码层收编
> 用户裁决（RECIPES 头部①–④）适用本期：配方 = 能力承诺；dub 卡上了就必须能用用户素材跑出同款

## 0. Context

RECIPES R1 期四件事：① 字幕样式从"枚举 + 一次性分支"收编为 **caption preset catalog**（原语 × 注册表）；② catalog 第一个新成员 `stacking`（堆叠字幕：新行淡入、旧行驻留、向下累积）；③ **dub 配方接线**——任务书携带配音语言集，compile_graph 在 clips 节点后扇出 dub 节点，单 run 出"原声 clips + N 语言配音版"；④ **首页卡片层**——composer 下方配方卡区，R1 上线 dub 卡一张（点亮纪律），点击 = 预填 prompt + explicit 槽 pin 确定性兑现。

dub 接线有一个 chat 时代不存在的新语义：chat 的 dub 是**单语言 morph**（原地改 spec 重渲染，"把这条配音成德语"）；配方要的是**单源 → N 语言并存**（原声 clip 不动，每语言一条独立产物）。morph 语义顺序执行两次会互相覆盖（DE 被 FR 冲掉），必须引入 fork 语义。

## 1. 已核实的现状事实（读码确认，2026-07-30）

- **字幕枚举两处硬编码清单**（catalog 要消灭的）：`apps/web/src/routes/_app.brand-template.tsx:75-79`（5 preset 数组）与 `_app.projects.$id.clips.$clipId.tsx:481-489`（Select 硬编码 SelectItem）。TS 类型 `CaptionStylePreset` 是手写联合（`packages/clip/src/types.ts:12`）。
- **Clip.tsx 原语已隐含分离**：`captionEntrance()`（`packages/clip/src/Clip.tsx:79-108`）隔离 entrance；karaoke 是渲染处 accent 开关；layout 隐含为"只渲染 activeLine"（`:341-369`）。`revealFrame` 目前只对 activeLine 计算（`:223-230`），stack 需按行计算。
- **Python 校验镜像**：`schemas.py:1343` `caption_style_preset: Literal[5 值]`——catalog 收编后 Python 只校验 id 成员，行为不下沉。
- **dub 链路在跑**：`run_dub_clip`（`node_runners.py:1775-1808`）= morph 语义——`synthesize_dub()` 产新 spec → 原地写 `output.render_spec` → PENDING → `_fan_out_renders`。`synthesize_dub`（`tools/dubbing.py:22+`）：字幕轨翻译 + 声纹克隆（样本优先级 VOICE_SAMPLE > 带 words 的 AUDIO > VIDEO；克隆结果缓存 `sample.meta.voice_id`，MiniMax 克隆 ~168h 临时）→ dub mp3 上传 → 新 render_spec。
- **dub registry 条目**：`registry.py:177-186`，`summary_template="Dubbed {n} clips · {lang}"`，`node_kind="dub"`，`requires=("media",)`。`STEP_RUNNERS["dub"]` 已挂（`node_runners.py:1826`）。
- **compile_graph mode① full run**（`orchestrator.py:161+`）：`preprocess(1) → persona_bootstrap(2) ∥ director_understand(3) → [checkpoint(4)] → director_plan(4|5) → 逐槽 executor（seq 10+，spec.slot + slot_index）`。clips 单槽去重已由 `ordered_slots` 保证。
- **modifier 目标解析**：`_modifier_target_clips`（`node_runners.py:1719`）——`spec.target_output_id` 优先，否则 `_target_clips`：`node.inputs` 上游步骤的 `output_refs`（同 run）→ 项目存量 clips 兜底。**同 run 内 clips_pipeline → dub 的边只需 inputs 指对，目标解析已免费**。
- **render 扇出时机**：clips_pipeline 建 output 即扇出 render 步骤（`node_runners.py:1242-1258`，output `render_status=PENDING` 供 render worker 认领）；fork 语义下原声 clip 渲染一次、dub 派生行各渲染一次，**无双渲染问题**（morph 才有）。
- **Output 模型**（`tables.py:259-286`）：`type`/`language`/`provenance`（默认 "real"）/`payload`/`files`/`source_ref`(JSONB nullable)/`render_spec`/`render_status`/`score`/`publishing`/`workflow_step_id`——fork 派生行全部字段有座。
- **任务书全链路**：`InferredIntent`（`schemas.py:502-588`）全字段有默认值（前端构造部分 prior 合法）；`GenerateRequest.slots`（`:1460+`）；`TaskSpec.outputs`（`orchestrator.py:85`）+ `autonomy`；pin-merge = `merge_explicit_slots`（chat/service.py），`/intent` 路由 `projects.py:303-310`。
- **composer 提交流程**（`HomeComposer.tsx:161-248`）：建项目 → 上传素材 → `POST /projects/{id}/intent {prompt, brand_template_id}` → `?overlay=intent`。prompt 是组件内 useState——卡片预填需最小的状态提升。
- **stills/图片视频与本期的边界**：R1 只交 stacking preset（视觉效果），voice_gen/stills 配方是 R2，不在本期。

## 2. 设计论证（评审沉淀区）

### 2.1 caption preset catalog（RECIPES §3 落代码）

**单点定义住 `packages/clip/src/captions.ts`（新文件）**：

```ts
export const CAPTION_PRESETS = {
  "clean-bottom":      { layout: "single", entrance: "none",     wordHighlight: false },
  "karaoke-highlight": { layout: "single", entrance: "none",     wordHighlight: true  },
  "fade-in":           { layout: "single", entrance: "fade-in",  wordHighlight: false },
  "pop-in":            { layout: "single", entrance: "pop-in",   wordHighlight: false },
  "slide-up":          { layout: "single", entrance: "slide-up", wordHighlight: false },
  "stacking":          { layout: "stack",  entrance: "fade-in",  wordHighlight: false, maxLines: 5 },
} as const;
export type CaptionStylePreset = keyof typeof CAPTION_PRESETS;
```

- **类型由 catalog 推导**（`keyof typeof`），`types.ts` 手写联合删除——新增样式 = catalog 一行，类型/校验自动跟随。
- **Clip.tsx 读 catalog 不再分支 preset id**：`layout` 分支（single = 现状；stack = §2.2）+ entrance 查表 + wordHighlight 开关。preview/render 同源纪律不变（一个分支双端生效）。
- **Python 侧**：`schemas.py` Literal 加 `"stacking"` + 注释指向 catalog（行为唯一事实源在 packages/clip；Python 只做成员校验）。
- **libass 纪律**：catalog 每个原语值注释其 libass 映射（stack = 每行一个 event，start=揭示时刻、end=片尾或滑出点、逐行下移 `\pos`）。新原语值入库前必须过此检查（写入文件头注释，作为后续维护者的门禁）。
- **前端两处硬编码清单改从 catalog 派生**：clip editor Select 与 brand-template preset 数组 → `Object.keys(CAPTION_PRESETS)` + i18n 标签键 `captionPresets.<id>`（en.ts 先行 zh.ts 镜像）。web 已依赖 `@repurposer/clip`（clips 编辑器 route 引用 ClipSpec 类型），import 路径现成。

### 2.2 stacking preset（RECIPES §3.2）

- **渲染语义**：按行分组（复用 `groupLines`，7 词/行）；每行有 revealFrame（把现有单 activeLine 的 revealFrame 计算重构为 `lineRevealFrame(line)` 按行可用）；当前帧可见集 = revealFrame ≤ frame 的行，**取最后 maxLines 行**（滑动窗口，最老行离场不淡出动画——v1 从简，离场动画归后续）；每行 entrance = fade-in（复用 `captionEntrance`，各行按自己的 revealFrame 播）。
- **布局**：容器锚定顶部（默认 `y≈0.14`，可被 `caption_position` 覆盖——Position 语义从"单行锚点"自然延伸为"堆叠容器锚点"），行向下流式排列（flex column + gap）。
- **颜色**：v1 全部 captionColor 均匀（不做旧行 dim——未请求的样式不加；dim 归后续若策展需要）。
- **SRT 导出不受影响**（caption_track 不变）；brand 的 color/size/font 照常生效。

### 2.3 dub fork 语义（RECIPES §4.1 的核心新增）

**机制词不变、用途住 spec（N-19）**：节点 kind 仍 `dub`，runner 仍 `run_dub_clip`；`spec.fork: true` 触发派生语义——

| | morph（现状，chat 路径） | fork（本期，配方路径） |
|---|---|---|
| 触发 | `spec.target_language`，无 fork 键 | `spec.target_language` + `spec.fork: true` |
| 行为 | 原地改写 source output 的 render_spec | **新建派生 Output 行**，source 行不动 |
| 渲染 | 重渲染自身 | 派生行 PENDING 扇出渲染；source 行渲染不受影响 |

**派生行字段**：`type="clip"`；`language=target_language`；`provenance="generated"`（声纹合成音频，披露诚实——EU AI Act 方向，ROADMAP 披露元数据行的先头兑现）；`render_spec` = `synthesize_dub` 产物；`source_ref` = source 行 source_ref 拷贝 + `derived_from_output_id`；`workflow_step_id` = 本 dub 节点；`score`/`publishing` 拷贝 source 行；`render_status=PENDING` → `_fan_out_renders` 扇出。

**morph 路径零改动**：chat 的 dub_clip/translate_clip 任务列表走原路。

### 2.4 任务书 dub_languages（全栈同名字段，宪法 §1）

- **定义**：`dub_languages: list[str]`（ISO 码；空列表 = 无配音）。不是 IntentSlot 字段——dub 是跨产物修饰不是产物类型（slot 五类型不动）。
- **链路**：`InferredIntent.dub_languages`（ComposerIntentAgent 学"配音成德语和法语"识别，**仅当有媒体素材时产出**——与 clips 同门 gating）→ `GenerateRequest.dub_languages` → `TaskSpec.dub_languages` → run.context 原样落库。
- **compile_graph mode①**：slots 扇出后，若 `dub_languages` 非空：必须有 clips 槽（无则 /generate 422 镜像 + ComposerIntentAgent 不产出）→ 记录 clips 节点索引 → **每语言一个 dub 节点**（`inputs=[clips_idx]`，`spec={target_language, fork: true}`，seq 续排）。每语言一节点 = 打勾流逐语言亮起 + 逐节点计量 + 独立重试。
- **pin-merge 规则**（与 slots 的 explicit 哲学同款）：`/intent` 重推断时，**prior 非空即 prior.dub_languages 全量为准**（面板是用户看过之后的唯一事实源）；prior 为 None 用新推断值。`merge_explicit_slots` 不动，dub_languages 合并单独一行。
- **422 镜像**：/generate 校验 `dub_languages` 非空 → slots 含 clips 且项目有可渲染媒体（复用 `has_renderable_media`）。

### 2.5 卡片层（RECIPES §7 落代码）

- **数据**：`apps/web/src/lib/recipes.ts`——`RecipeCard` 类型（RECIPES §7.1 schema）+ R1 单卡数据（dub 卡 `status: "live"`；分镜/图片视频/风格 `reserved` **不渲染**，数据留座）。dub 卡：`promptTemplate`（en/zh 各一）、`slotsPrior=[{type:"clips", explicit:true}]`、`dubLanguages:["de","fr","es"]`、`params.music=false`、preview（poster + 成片视频 URL，P3 收获后填）。
- **点击链路**（RECIPES §7.2 零分叉）：点卡 → 预填 composer prompt → 用户上传素材 → 发送时 `/intent` body 加 `prior: { outputs: slotsPrior, dub_languages }`（InferredIntent 全字段默认值使部分构造合法，§1 已核实）→ pin-merge → 审阅面板确定性呈现 → dock Start → `/generate` 携带 dub_languages。
- **composer 最小改动**：`HomeComposer` 加 `recipe?: RecipeCard | null` prop；`useEffect` 监听 recipe 变化 → `setPrompt(template)` + 暂存 slotsPrior/dubLanguages（state）；`handleGenerate` 的 /intent body 条件携带 prior。状态提升止于 `_app.home.tsx`（卡片区与 composer 的共同父级），不进全局。
- **审阅面板加配音行**（`GenerationOverlay` 计划卡区）：语言 chips + 每 chip 删除（删空 = 无配音）；**不可加**（加语言走 chat refine，R1 不做面板内编辑）；`planSummary` 加 dub 句；i18n `recipes.*` + `planSummaryDub` 等键 en/zh。
- **布局**：composer 区下方卡片区（grid，移动端折行）；卡片 = poster 图 + 标题 + 一句承诺 + 输出 chips；遵守 CLAUDE.md（rounded-lg、无 ring/border、shadow-lg/edge-glow、lucide 图标、文字非加粗）。
- **预览资源纪律**：公开可读（`apps/web/public/recipes/` 或对象存储公开前缀），禁登录态 asset 端点。

### 2.6 先后手（鸡生蛋解）

dub 卡预览视频需要 dub 能力先兑现。期内顺序：**P2（后端 dub fork）→ 用 demo talk 跑真管线收获预览成片 → P3 卡片填 preview 上线**。demo talk 从桶里 `demo/` 树恢复（RECIPES §0，开工先人工核实；恢复失败则先用任一真实演讲素材代替并在验收注明）。

## 3. 后端改动点

1. `apps/api/app/models/schemas.py`：`caption_style_preset` Literal 加 `"stacking"`（注释指 catalog）；`InferredIntent.dub_languages: list[str] = []`；`GenerateRequest.dub_languages: list[str] | None`。
2. `apps/api/app/chat/intent.py`：ComposerIntentAgent prompt 加 dub 语言识别规则（仅媒体素材；ISO 码；与 clips gating 同规则）。
3. `apps/api/app/chat/service.py`：`/intent` pin-merge 加 dub_languages 规则（prior 非空全量为准）。
4. `apps/api/app/pipeline/orchestrator.py`：`TaskSpec.dub_languages: list[str] = []`；compile_graph mode① dub 扇出（每语言一节点，inputs=[clips_idx]，spec.fork）；无 clips 槽 + dub 非空 → ValueError（路由转 422）。
5. `apps/api/app/pipeline/routes/projects.py`：/generate 422 镜像（dub 无 clips 槽 / 无可渲染媒体）；TaskSpec 构造携带 dub_languages。
6. `apps/api/app/pipeline/node_runners.py`：`run_dub_clip` fork 分支（§2.3 派生行字段表）；morph 路径不动。
7. `packages/clip/src/captions.ts`（新）：`CAPTION_PRESETS` + 推导类型 + libass 映射头注释；`types.ts` 手写联合删除改 re-export。
8. `packages/clip/src/Clip.tsx`：catalog 驱动渲染；`lineRevealFrame()` 重构；stack layout 分支。

## 4. 前端改动点

1. `apps/web/src/lib/recipes.ts`（新）：RecipeCard 类型 + R1 数据。
2. `apps/web/src/components/home/RecipeCard.tsx`（新）+ `_app.home.tsx` 卡片区（composer 下）；recipe 状态提升止于 Home。
3. `HomeComposer.tsx`：recipe prop + prompt 预填 + /intent prior 携带。
4. `GenerationOverlay.tsx`：审阅面板配音行（chips + 删除）；planSummary dub 句；`AnswerRequest.intent`/`/generate` 链路携带 dub_languages（面板编辑整本书送入的既有机制）。
5. `_app.projects.$id.clips.$clipId.tsx` + `_app.brand-template.tsx`：两处 preset 硬编码清单 → catalog 派生 + i18n 键。
6. `apps/web/src/lib/types.ts`：前端 InferredIntent/RunContext 类型镜像加 dub_languages。
7. i18n：`recipes.*`、`captionPresets.*`、`planSummaryDub`、配音行键 en.ts 先行 zh.ts 镜像；`stepKinds.dub`/`stepper.dubbing` 若缺补齐。

## 5. 命名审计（NAMING §5 触发）

新名词登记（通过后进词汇表）：

| 中文 | 英文 | 定义 | 不是什么 |
|---|---|---|---|
| 配方卡 | `RecipeCard` | 首页能力演示卡：承诺 + 输入槽位 + slots prior + preview | 不是模板市场、不是内容流 |
| 配音语言集 | `dub_languages` | 任务书级字段：本 run 要的配音语言清单（空 = 无配音） | 不是 IntentSlot 字段（修饰非产物类型） |
| 派生 | `fork` | dub 节点的用途标记（spec.fork）：新建派生产物行而非原地改写 | 机制词仍 dub（N-19 用途住 payload）；不是 git fork |
| 派生来源 | `derived_from_output_id` | 派生行 source_ref 内的溯源指针 | 不新建表列（住 JSONB） |
| 字幕样式目录 | `CAPTION_PRESETS` | 字幕样式注册表：id → 原语组合 | 不是自由样式（preset 枚举纪律不变） |
| 布局/进场/词级高亮 | `layout` / `entrance` / `word-highlight` | 字幕样式三原语 | — |
| 堆叠 | `stacking` | catalog 成员：新行淡入、旧行驻留、滑动窗口 | — |

判例自检：§1 全栈同名（dub_languages 五处同形）；§4（空列表 = 无配音，不加布尔）；§5（catalog 应用层注册表，零迁移）；N-19（fork 用途住 spec，机制词 dub 不变）。

## 6. 分期与验收

| 期 | 内容 | 依赖 |
|---|---|---|
| **P1** | caption catalog 收编 + stacking preset（§2.1/§2.2，前后端） | 无 |
| **P2** | dub_languages 任务书全链路 + compile_graph 扇出 + run_dub_clip fork（§2.3/§2.4） | 无（与 P1 并行可） |
| **P3** | 卡片层 + demo talk 预览收获 + dub 卡上线（§2.5/§2.6） | P2（预览成片来源） |

验收（e2e 真实管线，无测试套件纪律；改 pipeline 代码重启常驻 worker 再验）：

1. **P1 catalog**：5 个旧 preset 渲染行为逐一对拍重构前（同 spec 导出 MP4 视觉一致）；两处前端清单显示 catalog 全成员（含 stacking）；新加一行假 preset 注册项能出现在清单（验证"填注册项即得"后立即移除）。
2. **P1 stacking**：构造含 stacking 的 clip-spec → editor preview 与导出 MP4 一致：新行淡入、旧行驻留、超过 maxLines 滑窗；caption_position 覆盖生效；brand 颜色/字号生效。
3. **P2 拓扑**：dub_languages=["de","fr"] + clips 槽的 run → 图含 clips 节点 + 2 个 dub 节点（inputs 指 clips 节点）；无 clips 槽 + dub → 422。
4. **P2 fork**：demo talk 实跑 → 原声 clips 正常 + 每语言 N 条派生行（language 正确、provenance=generated、derived_from_output_id 指源、source 行 spec 未被改写）→ 派生行渲染完成可播、音轨是配音、字幕是译文；节点摘要 "Dubbed 5 clips · DE" 逐语言亮起；metering 落 cost。
5. **P2 pin**：/intent 推断出 dub 后，面板删法语 → Start → run.context dub_languages 无 fr。
6. **P3 卡片**：点 dub 卡 → composer 预填 → 上传素材 → 审阅面板 clips 槽 explicit + 配音行三语言 → Start → run 图同验收 3 → 产物齐。匿名落地页同卡可见（预览公开可读）。
7. **清理**：验证项目/产物清理（常驻 worker 抢跑纪律）；dev 库消息/产物回基线。

## 7. 禁止行为（Prohibited Behaviors）

1. **禁**字幕样式绕过 catalog 加一次性分支；新原语值未过 libass 映射检查禁入 catalog。
2. **禁** morph/fork 混淆——chat 路径（无 spec.fork）行为必须零变化；禁把 fork 做成默认。
3. **禁** dub_languages 进 IntentSlot 或新建表列（任务书级 JSON 字段，全栈同名）。
4. **禁**配方承诺靠 LLM 重新推断——卡片必须 explicit 槽 + dub_languages prior 钉死。
5. **禁**上 reserved 卡（点亮纪律）；禁卡片预览走登录态 asset 端点。
6. **禁**绕过 `orchestrator.create_run`；dub 扇出只准在 compile_graph mode① 内追加（mode② 任务列表路径不动）。
7. **禁**新表/新队列认领源（派生行走 outputs 表现有 render_status 认领）。
8. **禁**前端第二处硬编码 preset 清单残留（收编后 catalog 是唯一来源）；i18n 禁硬编码文案。
9. **禁**旧行 dim、离场动画等未请求样式进 stacking v1。
10. **禁** composer 加块/加 pill（卡片预填是唯一入口改动；CLAUDE.md composer 契约不动）。
