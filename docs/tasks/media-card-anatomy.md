# 素材/成片卡解剖与 Transcript 存储——剩余合同

> Status: 代码层已落；目标环境迁移、真实卡面验收、深浅主题与受影响仪式链仍开放。卡面解剖归 ADR-115，transcript 存储归 ADR-113；本文合并剩余迁移与验收，不保留施工批次。

## 1. 当前卡面契约

- **素材卡 = 阅读**：media + divider + transcript 在同一个 `rounded-lg ring-foreground/10` 环内；medialess 不渲染空媒体槽。舞台画幅固定，媒体 flex 吸收剩余空间，object-cover 不靠黑边撑形。
- **StageSkin**：舞台底缘 3px 检视皮显示 cue 比例、停顿留白与播放针；hover 可变粗，点击只 seek，不自动播放声音。编辑 overlay 存在时没有可靠源时间轴，隐藏检视皮并显示纯文本；恢复原文后回归。
- **成片卡 = 检视**：完整视频 + NLE 轴；轴头评分/ruler、34px 分块视频道、22px 连续字幕道、修饰道与跨道播放针。字幕道不在块内塞残字，详情经 hover chip，点击只 seek。
- **信息秩**：结构 L0 常驻；读数 L1 由唯一 HoverChip 浮于行上、portal 到 body、overlay-surface、不盖字；详情 L2 进既有 inspector/lightbox。空间不足用折叠/点击，不用 hover 藏结构。
- **血缘**：只有 cross-highlight；视频入边锚视频道 Y-center。不得新增边类型或把边落到卡内子元素。
- **镜像常数**：`NLE_AXIS_PX=116` 与 `graph_store._NLE_AXIS_PX` 同批；修饰道 26px/道，`trackVideoPortBasePx` / `nleModifierLanes` / `declaredHandles` / `NodePorts` 同步。legacy/raced 帧由 flex 吸收，可能有 contain slivers，不做破坏性重排。
- 数据行的时间 label 与 cue 分组由服务端单一规则供给；`formatDuration` 只用于播放器 chrome。NLE 轴永不增加拖拽、加轨、删轨、转场等 authoring 手势。

## 2. Transcript 存储与迁移

- transcript 是资产内容，不是 graph node。`assets.transcript` / `extracted_text` 与 `edited_transcript` overlay 是存储座；源 words/timestamps 不可变。
- cues 在读取时由唯一服务端规则派生，永不持久化；`transcript ?? extracted_text` fallback 只有一个 owner。
- 资产级 GET/PUT transcript endpoint 是编辑入口；overlay 编辑零 run、零 credit，不是 wiring op。graph-spec 不复制 text/cues/cued_text，不双写 legacy nodes。
- 目标环境迁移必须先把 legacy `edited_text` 移到资产 overlay，再删除 legacy transcript nodes/edges；迁移后证明无 legacy 行、无双写形态。执行前先 dry-run/备份与回退核对，不能只做代码层推断。
- 粘贴生成的文本资产必须如实标来源与估算能力，不伪装 ASR 词级时间戳。

## 3. 当前验收

自动检查：当前纯函数/track-stack/product-graph 套件、受影响旅程、工具目录变化对应 prompt_gate、web tsc 与相关纯 node 测试。

live 使用项目 `1aeb9787-a5a4-489e-ab4e-b7057164a610` 或等价取证夹具：

1. 图关系为两个节点/一条视频入边；素材卡 48 cues、5:40 badge、StageSkin 与 cue/seek 一致，hover chip 不盖字。
2. 成片为源 2:59–3:45；NLE ruler、一个视频块、六个无内嵌文字的字幕块、跨道针与源区间 cross-highlight 正确，视频 port 对齐。
3. 硬刷新后皮/轴/锚点逐区一致；draft 未跑时为诚实的 muted 空道，产物着陆后修饰道与锚同拍更新。
4. overlay 保存后隐藏时间皮，恢复原文后回归；legacy 96/236 帧不溢出，锚点不漂移。
5. 深色/浅色主题都走查；粘贴资产、medialess 资产与处理状态不制造假时间轴。
6. 迁移后 legacy transcript nodes/edges 为零，overlay 在刷新后保持，旧 Output 与产物可读。

## 4. 延期与未决问题

以下只登记，不授权现在实施：

- transcript 编辑是否进入 Operation Model；
- edited-transcript 驱动 re-cut；
- 粘贴资产的估算词轴；
- 时间轴 drag-select；
- modifier-lane 的内容面与 port 化；
- 竖屏卡压缩折叠与其他 recipe 卡面形态。
