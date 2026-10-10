# 卡面解剖 v4 — 施工合同

> Status: **代码层收口（2026-10-10）**——验证待用户自跑（§5）。母法 = `docs/DECISIONS.md` ADR-115；形态原型 = `scratch/media-card-anatomy.html`（信息秩三分定稿，真实数据 + 交互 demo）。
> 取证母本 = 项目 `1aeb9787-a5a4-489e-ab4e-b7057164a610`（xy_1.mp4 · 5:40 · 945 词 · 48 cue · 成片 = 源 2:59–3:45）。
> 提交：`5092834`（track_stack 数据面 + 纯测试）/ `d99065b`（NLE 检视轴 + 锚点 + 两镜像）/ `34b075c`（素材卡阅读型）。

## 1. Product Goal

两型卡各自成立：**素材卡 = 读**（一体环内媒体 + 转写稿，舞台钉死画幅零黑边，时间轴化作舞台底缘 3px 检视皮）；**成片卡 = 检视**（完整视频 + NLE 时间轴——轴头评分 / ruler / 分块视频道 / 连续字幕道 / 修饰道 / 跨道播放针）。信息秩三分：L0 结构常驻、L1 读数 hover（一座 HoverChip，浮于行上永不盖字）、L2 详情点击（既有 OutputInspector / lightbox 座位）。

## 2. Current State（核验于施工前 HEAD `060a943`，行号会漂移）

- 素材卡四症：`ThumbCard` 媒体区无环裸奔（`FlowNodeCard.tsx`）；媒体 `flex-1` 与转写稿区 `flex-1` 均分高度（画幅挤压）；cue 行 hover chip `absolute bottom-0.5` 盖字；24px 条码时间条（cue 块 `bg-muted` 无结构）。
- 成片卡「track 在哪」：`TrackStackSection` 双 24px muted 道 + 截断残字，无 ruler / 无道高 / 无道头；评分徽标占舞台左下。
- 数据面：`track_stack.py build_track_stack`（video_lane / text_lane / modifiers）已在；`OutputResponse.track_stack` 盖戳两座（/graph + /results）已在。
- 锚点：`trackVideoPortBasePx`（`layout.ts`）+ `NodePorts` 镜像已在（ADR-113 §5 视频道 Y-center）。
- 播放器 chrome 客户端时间座：`lib/utils.ts formatDuration`（lightbox 同座）。

## 3. Work Items

### W1 — track_stack 数据面（commit `5092834`）

- `video_lane` 块补 `out_label`（产出轴预格式化区间，`fmt_cue_time` 一座）。
- 新增 `ruler: [{t, label}]`：≤10 主刻度 nice step（1/2/5/10/15/30/60/120/300/600），次刻度 = 主/5（亚秒则弃），`t=0`/`t=total` 恒带标签，label=None = 纯几何次刻度。
- 纯测试 `tests/test_track_stack_pure.py` 11 条（分段拼接 / hidden 跳过 / donor 覆盖 / 词心归属 / clamp / 拉丁补空格 / 刻度步长 / 修饰存在）。

### W2 — NLE 检视轴（commit `d99065b`）

- `TrackStackSection` → `NleAxis`：轴头行（评分撤下舞台，右端裸分，Top pick 闸门律不变；非 tracked 解剖保留舞台徽标——`MediaProductRegion hideScore`）+ ruler（服务端刻度，点击 seek）+ 34px 视频道（primary 填充真剪辑块，`Film` 图标 + 「片段 N · 源区间」截断，hover = L1 chip + 血缘琥珀，click 拨头）+ 22px 字幕道（连续块零内嵌文字，hover chip 载句 + 区间）+ 修饰道（音乐/配音存在面居文字道下）+ 跨道播放针（timeupdate ~4Hz，含三角头）。
- **HoverChip 一座**：portal 到 body、overlay-surface、浮于锚行上方、pointer-events-none、横向 viewport 夹持。
- 锚点：`trackVideoPortBasePx(pagerPx, modifierLanes)` 新解剖公式；`nleModifierLanes` 取全版本最大道数（翻页不重坐）；`declaredHandles` / `NodePorts` 同批。
- 常数两镜像：`NLE_AXIS_PX = 116`（pad 6 + head 16 + ruler 22 + 视频道 34 + gap 4 + 字幕道 22 + pad 12）取代 `TRACK_STACK_PX = 96`——`layout.ts` ↔ `graph_store._NLE_AXIS_PX` 同批；修饰道 26px/道运行时进媒体 flex，出生预留不携。
- i18n en/zh 双写（trackSegmentTitle / trackSegmentOut）。

### W3 — 素材卡阅读型（commit `34b075c`）

- **一体环**：media + divider + 转写稿区同入 `rounded-lg ring-foreground/10` 一环；medialess 素材不渲染空媒体槽（转写稿即卡身）。
- **舞台钉死**：转写稿区固定解剖（divider 1 + 头 20 + cue 流 150 帽 + pads 20），预留 `TRANSCRIPT_SECTION_PX` 236→197 / `ASSET_TEXT_ONLY_H` 278→266（两镜像同批）；媒体 flex-1 只吃预留，object-cover 零黑边。
- **舞台检视皮**（StageSkin）：3px 白纱底 + cue 段∝（停顿留白）+ 播放针，hover 变粗 8px，click 拨头，scrubber 读数（`m:ss / m:ss`，formatDuration 播放器 chrome 座）入 L1 chip；血缘区间段亮琥珀。
- **cue 流**：时间 chip 上浮行外（HoverChip），播放中行 `bg-accent` 点亮，编辑面不动（overlay 写口 C4 不动）；滚动即收 chip。
- **时长角标**：舞台右下（让开变粗的检视皮）。
- 数据通道升卡级 `useAssetTranscript`（皮与流共读一份；cache by asset_id；processing 翻转 invalidate；保存乐观回显）。

## 4. Prohibited Behaviors

- 禁前端自建**数据行**时间格式化 / 自建 cue 分组镜像——label 全部服务端预格式化（ruler 刻度同法）；`formatDuration` 只许出现在播放器 chrome（检视皮 scrubber / 时长角标 / lightbox）。
- 禁给 NLE 轴加任何编排手势（拖 / 加轨 / 删轨 / 转场）——只读 + seek（L3）。
- 禁 hover 揭示结构层（道 / 转写稿流 = L0 常驻）；空间不足的答案 = 折叠 + 点击展开（缓做项），永不是 hover。
- 禁新增边类型 / 边落卡内子元素——血缘只有 cross-highlight 一座（ADR-113 §6 不动）。
- 禁动 clip-spec 契约字段（track_stack 是读面投影，ADR-016 不动）。
- 帧/锚常数禁单边改——`graph_store` ↔ `layout.ts` 一条律两镜像同批。
- 「文本驱动 seek」不许自动播放出声——muted ambient 律不动，seek 只拨头。
- 修饰道 port 化 / 内容面、竖屏卡压缩折叠、medialess 空媒体槽以外的 recipe 面形态——后续批。
- L1 chip 禁内联绝对定位盖字（一律 portal + 浮于行上）；禁手写 backdrop / shadow（overlay-surface 一座，in-flow 面零 shadow）。

## 5. Acceptance

1. **取证母本回放**：项目 1aeb9787 素材卡 = 一体环 + 舞台检视皮（48 cue 段 + 针）+ 时长角标 5:40；点 cue / 皮 → 拨头；hover cue 行时间 chip 浮于行上不盖字。成片卡 = 轴头 88 分 + ruler（0:00–0:45 五步主刻度）+ 视频道 1 块「片段 1 · 源 2:59–3:45」+ 字幕道 6 块零文字 + 跨道针；hover 片段块 → chip（产出 0:00–0:45 · 源 2:59–3:45）+ 素材卡源区间琥珀亮；视频入边锚视频道 Y-center。
2. **刷新恒等**：硬刷新后卡面逐区一致（皮 / 轴 / 锚点）。
3. **draft 等待态**：未跑 tracked 节点 = muted 空道（轴解剖出生即在）；修饰道随产品着陆出现，锚同拍移位。
4. **edit overlay**：保存 overlay 后检视皮隐藏（无诚实时间轴）、cue 流回纯文本面；恢复原文后皮回归。
5. **Legacy 帧**：旧预留帧（96/236）不溢出——媒体 flex 吸收，锚点座位不动。
6. 纯测试基线零 regression（含新 11 条）；tsc 零 error。
7. 用户自跑：取证母本 live 验收 + 深浅双主题走查。

## 6. 工期估算

W1 ≈ 0.5d · W2 ≈ 1.5d · W3 ≈ 1.5d —— 合计 **~3.5 工作日**（velocity 80% 口径）。依赖：Transcript 折叠批（W1~W6 未提交 WIP）先代收为基底（`ef49698`），避免锚点补丁漂移。
