# Task: Synthetic Talk Video — 生成端 v1（文字稿 + 照片 → 发言视频）

> **Status（2026-08-05 修订）**：**声音路径后置**——R2 图片视频卡已按无声口径先行交付（照片轮播+字幕+音乐，走 `align_stills` 阅读节奏时间轴 + stills 短路径，RECIPES §4.2）。本简报的 `voice_gen`/`synth_visual`（TTS + 合成主片）设计整体留档，随第 5 周声纹线（PROGRESS 第 5 周）重启；重启时按当时的 registry/DAG 现状重核 §2 前置假设（本简报写于意图层单面化之前，`PlanNodeKind`/`NODE_RUNNERS`/`_compute_ui_step` 等名已漂移为 `SKILL_REGISTRY`/`STEP_RUNNERS`/stage 提示）。
> **Base branch**: `main`（backend-module-restructure 已落地，路径已按新包结构核对）
> **Architecture reference**: `docs/AGENT_ARCHITECTURE.md` §12；ADR-029（双链并列）
> **Naming reference**: `docs/NAMING.md`（`voice_gen` / `synth_visual` 按 §5 注册零迁移）
> **Status**: 后置（声音路径随第 5 周声纹线重启，见上条 2026-08-05 修订）
> **Owner**: TBD

---

## 1. Context

Landing 副标题已承诺 "give it… just the transcript and some photos from a talk… and it produces clips"，但后端做不到：clips 要求可渲染媒体源（`HomeComposer` 本地拦截 + `/generate` 422 镜像）。外部反馈（投资人）直接追问此路径——**承诺与产品自相矛盾，本任务兑现承诺**。

战略定位（STRATEGY §2.2 终态）：identity-driven 虚拟产物——用**用户的**声纹、照片、文风生成，不做 Factory 通用生成。用户痛点真实存在：大多数演讲没有录像，这类演讲者目前进不了门。

架构地基（ADR-029 已定，本任务不新决策）：生成 = RunPlan 新 node kind，与 clip 链共享 plan_nodes / worker / 计量 / 步骤清单；产物 `provenance=generated`；主轨生成物**不是 clip、不进 clip-spec**。

**v1 形态 = 确定性合成**（无唇形数字人）：声纹 TTS + 照片动态合成（Ken Burns / 逐句字幕 / 波形 / 品牌框），全确定性、零新 provider、成本可忽略。唇形同步 avatar 是 v2（外部 provider，ADR-029 框架已留位）。

## 2. Current Functional Status

### 已在

- `tools/voice.py`：`clone_voice()`（声纹克隆）+ `synthesize()`（T2A）+ `extract_audio()`——Step 1 全部零件。
- `tools/asr.py`：词级时间戳 ASR——合成音频回配时间戳的现成机械。
- Remotion 渲染服务 + `pipeline/rendering.py`：spec → MP4 黑盒。
- `Asset.provenance` / `outputs.provenance` 字段：谱系标记已在（ADR-030）。
- Speaker 画像：声纹挂载点（`clone_voice` 结果挂 Speaker）。
- PlanNodeKind 注册表守门（D6）：新 kind 注册零表迁移。

### 不在

- `voice_gen` / `synth_visual` 节点 kind 与 runner。
- 合成视频的 Remotion composition（照片 + 音频 + 字幕 + 品牌）。
- clips 输入校验对"文字稿 + 照片"组合的放行（前后端）。
- composer 的声音录入 / 声纹缺省引导。

## 3. Target Functional Status

用户在 composer 上传**演讲文字稿 + 照片（+ 10 秒声音样本或已存声纹）**，勾选 clips：

1. run 拓扑自动带生成前缀链：`preprocess → voice_gen → synth_visual → director_plan → clips_pipeline → …`
2. `voice_gen`：文字稿 → Speaker 声纹 TTS → 音频 asset（`provenance=generated`）。
3. `synth_visual`：照片 + 音频 + 逐句字幕 + brand → Remotion 新 composition → **合成发言视频 asset**（`provenance=generated`，`source_ref` 指向文字稿 asset 与 Speaker）。
4. 合成音频走现有 ASR 回配词级时间戳（TTS 音频干净，对齐近乎完美）——`clips_pipeline` 对素材是拍的还是合成的**零感知**。
5. 之后全链路复用：director / clip 选段 / clip-spec 渲染 / 文案产物 / Distribution——下游零改动。
6. 步骤清单新增两步（`cloning_voice` / `synthesizing_video`），用户看得见"正在合成你的发言视频"。

## 4. Implementation Plan

### 4.1 节点注册（D6，零迁移）

`PlanNodeKind` 注册两个新 kind + `NODE_RUNNERS` 两个 runner：

| kind | runner 职责 | 产物 |
|---|---|---|
| `voice_gen` | 取文字稿 asset 文本 → Speaker 声纹（无则先 `clone_voice` 样本）→ `synthesize()` → 音频 asset 落库；TTS usage 经 metering 落 `plan_nodes.cost` | audio asset |
| `synth_visual` | 照片 assets + 音频 + 字幕（文字稿对齐）+ brand → render 服务新 composition → 视频 asset；**规则质检**：音画时长一致 / 字幕对齐率 / 分辨率达标 | video asset |

### 4.2 compile_graph 输入组合 gating（模式①扩展）

clips 的合法输入从"有 video/audio/image"扩展为：

```
有 video/audio  → 现有链（无前缀）
有 transcript + image（无 video/audio）→ [voice_gen → synth_visual] 前缀 + 现有链
纯文字 → 文案链（clips 不进图，现状不变）
```

拓扑推导纯函数，无 LLM 参与（CHAT_ARCHITECTURE §1 原则 1）。

### 4.3 Remotion 新 composition

`apps/render` 新增 `SyntheticTalk` composition：照片序列（Ken Burns 推拉/切换）+ 音频轨 + 逐句字幕（brand caption 样式）+ 品牌框（logo/CTA/intro-outro）。复用现有 brand 烘焙管线；**它是主轨生成物，不是 clip——不进 clip-spec 契约**，渲染调用走独立 spec 通道（参考 dub 的既有先例）。

### 4.4 校验放宽（前后端镜像）

- 前端 `HomeComposer`：`clipsNeedMedia` 条件放宽为"有媒体文件，或（文字稿 + 照片）"；demo 视频自动拉取逻辑修正——已附文字稿+照片时不拉 demo（走生成链），空 composer 才拉。
- 后端 `/generate`：422 校验同步放宽。

### 4.5 Composer 声音入口

- Speaker 已有声纹 → voice_gen 直接复用，UI 无新元素；
- Speaker 无声纹 → composer 附件区接受音频样本（10s+），或在 pill 上标"需声音样本"引导；v1 不做录音 widget（上传文件即可）。

### 4.6 步骤清单

`_compute_ui_step` 映射新增：`voice_gen` → `cloning_voice`、`synth_visual` → `synthesizing_video`；i18n 新增两条（en/zh）。

## 5. Acceptance

1. 端到端：文字稿 + 3 张照片 + 声音样本 → clips × 5 产出，每条可选段、可渲染、可进 editor。
2. 谱系：合成 video/audio asset `provenance=generated`；产出 clips 的 `source_ref` 可回溯到合成 asset；`outputs.provenance` 链路完整（供 ADR-026 分类器）。
3. 计量：`voice_gen` 节点 `cost` 非空（TTS usage）；`synth_visual` 渲染成本落账。
4. 步骤清单：合成两步可见且进度合理；失败时错误文案可读。
5. 回归：实拍视频路径零行为变化（同输入同产出 diff，沿用 runplan Phase 1 验收口径）。
6. 规则质检生效：音画时长差 > 阈值 / 字幕对齐率不达标 → 节点 failed 且错误可读。

## 6. Prohibited Behaviors

- **禁止**接外部 avatar / 唇形同步 provider（HeyGen / D-ID / Hedra / Hailuo）——那是 v2，ADR-029 框架已留位。
- **禁止**建 variant gate / `suspended` 状态 / candidate-pin 机制——v1 单产出，review 页即人工 gate。
- **禁止**合成主视频进 clip-spec 契约（ADR-029：主轨生成物不是 clip）。
- **禁止** LLM judge / verify 节点——质检用规则（时长、对齐率、分辨率），LLM 质检是 Phase 3。
- **禁止**新增"生成模式"字段进 `InferredIntent`——输入组合可推导，intent 保持薄。
- **禁止**为 v1 做录音 widget——文件上传足够。

## 7. Risks

| 风险 | 缓解 |
|---|---|
| TTS 不返回词级时间戳 | 走现有 ASR 回配（§3.4），零新依赖 |
| 合成视频"一眼假"损害品牌感 | v1 定位 audiogram/动态幻灯形态，字幕+波形+品牌框为主视觉，不伪装真人出镜 |
| MiniMax TTS 多语言质量 | 验收 §5.1 覆盖 en + 一门欧洲语言（de 或 fr） |
| 声纹缺失阻塞生成 | composer 前置引导（§4.5），无声纹不建 voice_gen 节点（presence-gating，ADR-029 同款） |
