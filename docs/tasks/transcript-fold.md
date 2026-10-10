# Transcript 折叠 — 施工合同

> Status: **施工中（2026-10-09 开工）**。母法 = `docs/DECISIONS.md` ADR-113；形态原型 = `scratch/transcript-fold-proposal.html`（v5，真实数据渲染 + 交互 demo）。
> 取证母本 = 项目 `1aeb9787-a5a4-489e-ab4e-b7057164a610`（xy_1.mp4 · 5:40 · 945 词 · 48 cue · 成片 = 源 2:59–3:45）。

## 1. Product Goal

transcript = 视频的内容层，不是节点。用户可见结果：① 画布每素材少一列（素材卡 + 成片卡，一条 video 边）；② 素材卡 = 视频 + 时间条 + 文本流，点句子跳画面；③ 成片卡 = 完整视频 + 视频轨 + 文字轨，hover 片段块点亮素材源区间；④ 编辑转写写资产层，单一座位。

## 2. Current State（核验于 2026-10-09 HEAD + dev 库实证，行号会漂移）

- 转写节点：`graph_fill.py:363 stamp_transcript_node`（docstring 自证 LEAF face），出生两座 = `assets.py:61-70`（chat 贴文）+ `graph_fill.py:929`（plan-path ensure）；翻转座 = `asset_processing.py`（create=False）。
- 存储复制：graph spec `text`/`cues`/`cued_text`/`edited_text`/`text_edits`；真相 `assets.transcript`/`extracted_text` + `meta.words`。
- cue 一派生四处：`graph_fill._transcript_cue_rows`（落库，零消费者）/ `chat/perception/executes.py` search_transcript / `tools/clips/node.py` prompt 装配 / `transcript.py:group_cues`（唯一律本体）。`_fmt_cue_time` 在 `graph_fill.py:1688`。
- fallback 分裂：`transcript or extracted_text`（graph_fill:391 / executes.py:1085 / plan_turn.py:324）vs 反向（`asset_processing.py:180` / `step_context.py:202` / `node_runners.py:339`）。
- 编辑链：`POST /{project_id}/graph/edit-text`（`projects.py:896`）→ `EditTextOp`（`graph_store.py:117-139`）→ `apply_wiring_ops` 写 `spec.edited_text`；LLM 面提及 = `turn_tools.py:116-119` + `schemas.py:891`；响应模型 `schemas.py:3635`；前端通道 = `onTextEdit`（flow/types.ts:244 / FlowView / FlowNodeCard / ResultsCanvas / projects.$id.index.tsx）。
- 读面：`projects.py:_read_face`（document → text×manual）+ `/graph` 的 task_book 读面过滤先例（`projects.py:434-446`）+ asset dossier join（`projects.py:741-753`）。
- 产物读面：`OutputResponse.render_spec: ClipSpec` 全量已在（`schemas.py:3429`）；dossier 盖戳先例 = spec_prompt/model_facts（`projects.py:684-717`，/results 同族座位）。
- 端口：`FlowNodeCard.tsx:1936 NodePorts`（28px 圆外置，`bottom` 锚定角落栈，常数两镜像 = `layout.ts` cornerStackedInPorts/declaredHandles）。
- 卡面：素材卡 = `ThumbCard`（FlowNodeCard.tsx:324，inline muted-loop video + factsbar）；文档卡 = DocumentCard（transcript 分支 :519-636, :783）；产物卡 = GraphCard（~1717）。
- 帧预留：server = `graph_store.py:_frame_of` / `_KIND_FRAME_CLASS`（asset 280×260 等）；client 镜像 = `layout.ts`。

## 3. Work Items

### W1 — 存储地基（migration + schema + 一法一座）

- Alembic migration：`assets.edited_transcript`（Text nullable）。**同迁移搬家**：存量 transcript 节点的 `spec.edited_text` → 回填 `assets.edited_transcript`（按 spec.asset_id join，最新一条 text_edits 的顶值为终态——edited_text 即当前 overlay），随后**硬删** `document/transcript` 节点行 + 其边（task_book 先例：读面过滤 + 迁移删行）。
- `tables.py` Asset + 列；`schemas.py` AssetResponse 不动（transcript 走独立端点，§W2）。
- `transcript.py` 加 `display_cues(words) -> (rows, truncated)`：rows = `[{start, end, text, label}]`，label = `_fmt_cue_time` 从 graph_fill 搬入（**一法一座**，graph_fill 的 `_transcript_cue_rows`/`_fmt_cue_time` 删除）。
- `app/pipeline/assets.py` 加 `asset_text_content(asset)` = `transcript or extracted_text`（唯一座）；三处反向 reader 改正（asset_processing / step_context / node_runners）。

### W2 — 转写节点退役 + 读面端点 + 编辑写口搬家

- `graph_fill.py`：`stamp_transcript_node` 整删 + 三个调用点清理（assets.py 贴文出生 / plan-path ensure / asset_processing 翻转）。资产级联删除的 transcript 分支（graph_fill.py:346-360 victims）同删。
- `projects.py /graph`：transcript 节点 + 其边读面过滤（`type=="document" and spec.role=="transcript"`，task_book 先例同构）。
- 新端点 `GET /{project_id}/assets/{asset_id}/transcript` → `AssetTranscriptResponse{text, edited_text, cues[], truncated}`：text = `asset_text_content`（overlay 并存时两处各归其位——text 恒为源层，edited_text 为 overlay）；cues 经 `display_cues` 读面派生（无 words → cues=null + truncated=false，paste 资产诚实无时间面）。
- 编辑写口：新端点 `PUT /{project_id}/assets/{asset_id}/transcript`（body `{text: str | null}`——null = 清 overlay 回源层）写 `edited_transcript`，零 run 零积分；**旧链整删**：`projects.py:896 edit-text` 端点 + `EditTextOp`（union + handler + prompt catalog 行）+ `schemas.py:3635` 响应模型 + `turn_tools.py:119` 的 edit_text 措辞 + `schemas.py:891` 描述。operations 账不进（ADR-113 §7 挂账）。
- 前端旧链整删：`onTextEdit` 通道五座（flow/types.ts / FlowView / FlowNodeCard / ResultsCanvas / projects.$id.index.tsx）+ DocumentCard transcript 分支（readCueRows / cued_text fallback / 卡内编辑）。

### W3 — track_stack 读面投影（成片卡数据）

- 新纯模块 `app/pipeline/track_stack.py`：`build_track_stack(render_spec) -> TrackStack | None`：
  - `video_lane`：非 hidden segments 按序 → `[{out_start, out_end, src_start, src_end}]`（out 时间 = 累计拼接）。
  - `text_lane`：caption_track 词（源时间）→ 按 segment 归段（词心落在 seg 内）→ **每段内** group_cues（切段 = 硬断句）→ 时间平移到产出轴 → `[{out_start, out_end, text, label}]`（label = 产出时间 m:ss–m:ss，`display_cues` 同族格式化）。
  - `modifiers`：`{music: bool, dub: bool}`（render_spec.music.enabled / dub 非空）——v1 只携存在性，修饰轨内容面后续批。
  - 零 segments 或非 clip 族 → None。
- `OutputResponse.track_stack: TrackStack | None = None`（None = 非 clip / 无轨——读容忍）；盖戳座位 = /graph 的 outputs join（projects.py:754-761 区）+ /results（spec_prompt 同座）。schemas.py 保持干净，不 import pipeline。

### W4 — 前端素材卡 transcript 区

- `lib/api.ts`：`fetchAssetTranscript(projectId, assetId)` / `putAssetTranscript(...)`。
- `ThumbCard` 解剖扩展（results canvas 且 asset.type ∈ video/audio/transcript/past_material）：媒体区（现状）→ **时间条**（cue 块 ∝ 时长、停顿留白、播放头）→ **cue 流**（定高 200px 内滚、hover 显时 chip）→ factsbar。数据 = mount 时 `fetchAssetTranscript` 一次性拉取（surface 级 cache by asset_id；编辑保存 / processing_stage 变化后 invalidate）。
- **seek 交互族**：cue/条块 click → 卡内 video ref `currentTime = cue.start`（现有 inline muted loop 不动，seek 只拨头）。paste/transcript 型 = 无媒体区无时间条，纯 cue 流/文本面。
- **编辑**：cue 流 header 的 ✎ → 纯文本 textarea（`edited_text ?? text`，时间永不进 textarea，C4）→ 保存走 PUT → 本地 invalidate + 乐观回显（永不回闪）。
- **帧预留**：素材节点 text-yielding 族帧高 += transcript 区常数（`graph_store._frame_of` asset 分支 + `layout.ts` 镜像——一条律两镜像，ADR-112 黑边教训）。
- i18n en/zh 双写（transcript 区标题 / cue 计数 / 编辑态 / truncated 诚实标记）。

### W5 — 前端成片轨道栈 + cross-highlight + 锚点

- `GraphCard`（video×editor）解剖：媒体区 → **视频轨**（lane：片段块 = track_stack.video_lane，label `片段 N · 源 m:ss–m:ss`）→ **文字轨**（lane：字幕句块 = text_lane，∝ 产出轴、停顿留白）→ factsbar。**两条轨常驻解剖**（draft/running = muted 空轨行——等待态座位，FLORA 空态先例）；修饰轨（音乐/配音）有内容才出现。
- 点句块/片段块 → 卡内 video `currentTime = out_start`。
- **cross-highlight**：ResultsCanvas 持 `lineageHover: {assetId, srcStart, srcEnd} | null`；成片卡片段块 hover 上报；素材卡时间条/文本流重叠区间琥珀色亮起。FlowView props 穿线（`onLineageHover` / `lineageHover`）——唯一跨卡通道，禁泛化。
- **锚点律**：`NodePorts` 视频入锚座位 = 视频轨 Y-center——`bottom = FACTSBAR_PX + TEXT_LANE_ROW_PX + VIDEO_LANE_ROW_PX/2 − 14`（14 = 半圆）；常数入 `layout.ts` 两镜像（`TRACK_LABEL_PX` / `TRACK_LANE_PX` 入帧高预留同一批）。非轨道卡（text/table/asset）角落栈不动。
- **帧预留**：video×editor 节点帧高 += 双轨常数（`graph_store._frame_of` generator 解剖 + `layout.ts graphNodeSize` 镜像，同批两镜）。
- i18n en/zh（视频轨/文字轨/片段标签）。

### W6 — 文档收口

- `docs/CHAT_ARCHITECTURE.md` §5（转写节点退役 + 素材卡内容层 + 轨道栈 + 锚点律）+ §9（edit_text 退役）。
- `docs/UI_GUIDELINES.md` §9（卡面解剖两新族 + 锚点律修订）。
- `docs/MODULE_ARCHITECTURE.md` §7.1（graph_fill 行删 stamp_transcript_node）+ §4（assets.edited_transcript 归属注记）。
- `docs/NAMING.md` 词汇行：内容层 / 时间条 / 轨道栈（检视）/ cross-highlight / 锚点律。
- `docs/PROGRESS.md` §0.2 状态回填。

## 4. Prohibited Behaviors

- 禁把 transcript 正文 / cues 以任何形式再写进 graph_nodes.spec（复制三件套整类灭绝）。
- 禁前端自建时间格式化 / 自建 cue 分组镜像——`display_cues` / `group_cues` 是唯一律，前端只渲染。
- 禁给轨道栈加任何编排手势（拖 / 加轨 / 删轨 / 转场）——只读 + seek（L3）。
- 禁新增边类型 / 边落卡内子元素——血缘只有 cross-highlight 一座。
- 禁动 clip-spec 契约字段（track_stack 是读面投影，ADR-016 不动）。
- 帧/锚常数禁单边改——`graph_store` ↔ `layout.ts` 一条律两镜像同批。
- 存量 transcript 节点行：迁移硬删（edited_text 先搬家）；禁保留双写兼容形态。
- 「文本驱动 seek」不许自动播放出声——现有 muted ambient 律不动，seek 只拨头。
- 禁扩 scope：估算词轴（paste 资产）、改稿驱动重剪、拖选选段、修饰轨内容面、编辑入 operations 账——全部后续批。

## 5. Acceptance

1. **取证母本回放**：项目 1aeb9787 画布 = 2 节点 1 边（素材 + 成片，video 边锚视频轨 Y-center）；素材卡点 cue → 视频拨头；成片卡双轨（视频轨 1 段 2:59–3:45 + 文字轨 6 句）；hover 片段块 → 素材卡源区间琥珀亮。
2. **刷新恒等**：硬刷新后卡面逐区一致（transcript 区 / 轨道栈 / 锚点位置）。
3. **paste 资产**：无时间条无 cue chip，纯文本面；编辑保存 → 刷新后 overlay 仍在（写 assets.edited_transcript）。
4. **Legacy 愈合**：旧 transcript 节点行迁移后消失，edited_text 出现在资产 overlay。
5. 纯测试基线零 regression + `test_product_graph_pure` 不受影响（transcript 边本就不入 rank）；prompt_gate 全探针 PASS（turn_tools 措辞面变了）。
6. 用户自跑：chat_scenarios 受影响座 + live 验收。

## 6. 工期估算

W1 ≈ 1d · W2 ≈ 1.5d · W3 ≈ 1d · W4 ≈ 2d · W5 ≈ 2.5d · W6 ≈ 1d —— 合计 **~9 工作日**（velocity 80% 口径）。依赖：ADR-112 在飞批（graph_fill/graph_store/FlowNodeCard 同文件）先提交，避免锚点补丁漂移。
