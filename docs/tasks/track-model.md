# Task: 轨道模型——clip-spec 轨道化（锚定存储 + 泳道编译产物 + TRACK_REGISTRY）

> **Status**: 立项（2026-08-17 设计收敛，待 ADR 过会；P0 随第三周 crop_track 契约同批施工）
> **Base branch**: `main`
> **Architecture reference**: `docs/RENDERING.md`（§3 契约 / §4 隐式轨道解剖 / §8 轨道模型方向——本简报的母文档）；ADR-016（契约锁定）；ADR-032（Operation Model）
> **Naming reference**: `docs/NAMING.md`（§5 枚举注册表 / §6 行话黑名单 / §8 准入即登记；N-11 裸词违规同型判例）
> **Owner**: TBD

---

## 1. Context

clip-spec 是系统里最后一个"走一步加一步"的架构面：图内核（NodeBase）、能力层（OP ∪ SKILL 双注册表）、产物层（outputs 派生）都已完成各自的"注册表时刻"，唯有渲染契约仍是**每条轨一个手写字段 + N 处消费方特判**——08-14 translation_track 落地实测要摸约 7 处（双端 schema / Clip.tsx 分支 / `_absolutize` / 尺寸规则 / C2PA / ops 寻址），全靠人记，这就是"每加功能前后打架"的力学来源。

同时三股需求正朝这个面涌来：crop_track 关键帧轨（第三周 spike，08-18 契约落地）、reframe_clip 分镜（双子卡）、layers（B-roll / 双机位访谈 PiP）。**现在不做轨道化，三条线各自再长三个特判；现在做，它们成为注册表的前三个真实住户。**

设计判据（2026-08-17 讨论收敛）：**操作集闭包**——registry 合法 op/skill 的任意序列（用户聊 N 轮）产出的 spec 仍可表示、可渲染、可继续改。十二项典型剪辑操作走查结论：7 项今天已通、1 项缺登记（reorder_segments op）、4 项（异源插入 / 过渡 / 文字层 / 贴图层）挂在同一次采购上。

形态拍板：**锚定 = 存储格式，泳道 = 编译产物**——位置不落库，输出时间由烘焙缝一次 fold 派生；双真相禁令（锚与绝对坐标不得平级共存于同一行数据）。

## 2. Current Functional Status

### 已在（本迭代的地基，全部现状代码实证）

- **隐式多道已存在**（RENDERING §4 解剖表）：主轨 `source`+`segments`（源时间轴）/ 数据轨 `caption_track`·`translation_track`（源时间轴）/ 块轨 `music`·`dub`·`title`·`brand.intro/outro`（输出时间轴）/ `crop` 静态单值。
- **时间轴二分已是事实**：`_track` 字段 = 源时间轴经 segments 映射；块字段 = 输出时间轴。映射双向换算集中在 `Clip.tsx` 的 `timeline` 累加 + `sourceTime` 反映射两行。
- **烘焙缝已存在**：`pipeline/rendering.py::_absolutize`——渲染前 fold 的唯一发生地，泳道投影将来的家。
- **注册表先例已跑通**：`captions.ts` CAPTION_PRESETS（catalog 住 packages/clip、TS 类型由此推导、Python 只校验成员）——轨道注册表的双端形态照此办理。
- **写纪律已就位**：render_spec 一切修改经 operations 表 + 快照 undo（ADR-032）；ops 双注册表分层（ADR-033）。
- **规格纪律已在**：样式枚举 + CSS ∩ libass 子集（保 FFmpeg 后路）。
- **排期已在**：第三周 08-18 行 = `speaker_map` 分析节点 + `crop_track` 关键帧轨契约。

### 不在

- 轨道注册表（TRACK_REGISTRY）与两条启动自检。
- 关键帧数据轨的 schema 形态（crop_track 是第一个）。
- segments 的异源能力（`asset_id` 缺省主源）。
- 层轨（layers）、锚（anchor）、过渡枚举（transition）。
- 每轨确定性工艺检查项（checks）的家。

## 3. 改动点

### P0 —— 随 crop_track 契约同批（第三周）

1. **词汇表 + 判例登记**（NAMING §2/§3）：轨道 `track`（裸用违规，必须带家族限定——新判例，N-11 同款）/ 主轨 main track / 段 `segment` / 数据轨 data track / 层 `layer` / 锚 `anchor` / 过渡 `transition` / 块轨 block track。讨论期占位词 lane / blocks / junctions / placements 不采用。
2. **TRACK_REGISTRY 骨架**：catalog 住 `packages/clip`（TS 类型推导），Python 侧只校验成员（CAPTION_PRESETS 同款双端纪律）。每条轨一份 `TrackDef`：`family`（sequence|data|layer|block）/ `timeline`（source|output|derived）/ `owner`（唯一写者技能）/ `mutex` / `provenance` / `url_fields` / `checks`。现有 8 条轨平移登记。
3. **两条启动自检**（对账 = ⊆ 代数同款）：① spec 顶层字段 ⊆ 注册表，每字段恰好一条轨；② **phantom track**——注册一条假轨，渲染 / 寻址 / 合规 / 计价自动接管、消费方零改动。
4. **crop_track = 第一个 data 轨关键帧住户**：`family=data, timeline=source`（按 sourceTime 采样，`Clip.tsx` preview=render 同一采样函数），owner = reframe 线；静态 `crop` 作缺省向后兼容（RECIPES §4.3 已定方向）。
5. **消费方改 fold 注册表**（随登记逐步）：`_absolutize` 读 `url_fields`；C2PA 分类器读 `provenance`（ADR-026）；estimate 读轨声明。

### P1 —— 随 reframe 技能包同批

6. **checks 首批真实住户**：crop 不出人脸框 / 最短驻留 / 防跳切缓动——**确定性断言写进技能 procedure，随技能出生，不等 Phase 3 verify 框架**。
7. `speaker_map` 产物登记为 crop_track 的上游（素材级，asset-hash 复用）。

### P2 —— 第一条 insert / 双机位 / B-roll 技能进排期时，一次做完

8. **segments widen**：`asset_id?`（缺省 = 主源）——异源插入 = 带 asset_id 的段；向后兼容，非破坏渐宽。
9. **层轨 `layers` + 锚**：条目 `{kind（枚举注册：broll / text_callout / pip / motion_graphic）, anchor, rect, z, source_ref?, provenance}`；锚三形态——段锚（`{segment_id + 源偏移}`，段删级联删并告知）/ 边锚（`{head|tail + 偏移}`；intro/outro 本质即边锚块）/ 比例锚（预留）。
10. **过渡枚举**：`transition` 挂段的进场边（none/fade/dip，2-3 封顶），换序随段走；ADR-016 L3 注记按"枚举可、画廊不可"修订。
11. **ops 寻址升级**：`(track, item_id, op)` 对注册表校验；`add_layer` / `remove_layer` / `move_layer` / `reorder_segments` 登记入 OP_REGISTRY。
12. **泳道投影 fold**：烘焙缝在 `_absolutize` 同处把锚定 spec 编译为扁平泳道（绝对时间 + z 序）喂渲染器——渲染器 / FFmpeg 后路只吃投影；投影永不落库、永不进快照。

**顺序纪律两条**：用真实住户压出注册表形状（不许抽象先行）；**先锚后物**（P2 内 9 的锚模型先于任何层条目落地——顺序反了就要迁移漂移的尸体）。

## 4. Prohibited Behaviors

- **禁止**把 spec 重构为 `tracks:{}` 容器（破坏性格式迁移；收益已在评审中证伪——快照 undo + LLM 不写 spec 的地基上"全量常驻空轨"无收益）。
- **禁止**双真相：同一行数据里绝对坐标与锚平级共存；泳道只是编译产物，永不可写。
- **禁止** LLM 提议绝对时间码——op 载荷 = 实体引用（段/锚/枚举），坐标计算永远归代码（LLM 提议、代码裁决的编辑侧延伸）。
- **禁止** NLE 自由轨语义进 spec（任意增删道 / 同道重叠 / 转场画廊 / 关键帧自由编辑）；kind 全部枚举注册表守门。
- **禁止**用户面出现轨道概念（UI 永不见轨；层条目呈现为"这段配了画面"标记卡）。
- **禁止** `overlay` 一词用于视频层（已归 UI 浮层：GenerationOverlay / overlay-surface——避让 N-27 同型一词两义）；视频层统一用 `layer`。
- **禁止**每轨多写者：一条轨一个 owner 技能；撞轨 = 编译期 422，不做运行时合并。
- **禁止**绕过注册表给单轨加特判分支（NAMING §5 / CHAT_ARCH §4 扩展门纪律同律）。

## 5. 验收

1. 两条启动自检绿：spec 字段 ⊆ 注册表对账；phantom track 全链接管（渲染 / 寻址 / 合规 / 计价零消费方改动）。
2. crop_track 双端 parity：`<Player>` 与渲染服务同一采样函数，抽帧对比一致（parity 回归同款测法）。
3. remap 单函数：grep 证明源↔输出时间换算全库只有一处（TS）+ 镜像（Python）。
4. 十二操作走查表 P2 完成后全 ✅（异源插入 / 过渡 / 文字层 / 贴图层各有座位）。
5. 剧本 harness（S1–S4x）零回归；改 pipeline 代码必重启常驻 worker。
6. ADR 过会：以本文 §1–§4 为蓝本出 clip-spec 契约扩展 ADR（ADR-016 级），过会后 RENDERING §8 转正式契约。

## 6. 分期与排期锚点

| 期 | 内容 | 挂点 |
|---|---|---|
| P0 | 词汇表 + 判例 + TRACK_REGISTRY + 两条自检 + crop_track 住户 + 消费方 fold | 第三周 08-18 行（crop_track 契约），同批过 ADR |
| P1 | checks 首批住户 + speaker_map 上游登记 | reframe 技能包（第三周 spike 双验证之后） |
| P2 | segments widen + layers + 锚 + 过渡枚举 + ops 寻址 + 泳道投影 | 第一条 insert / 双机位 / B-roll 技能进排期时触发，一次做完 |

排期纪律：本迭代不是独立项目，是 crop_track / reframe / 分镜双子卡三条已排期线的**随行文书**——不开独立工期；P2 触发前只写契约不预建。
