# Task: 轨道模型——clip-spec 轨道化（锚定存储 + 泳道编译产物 + TRACK_REGISTRY）

> **Status**: 已完成（2026-08-18 落地收口——架构批六项改动全落 + harness 复核；crop_track/speaker_map/insert_broll 等能力线按 PROGRESS 第三周表推进）
> **Base branch**: `main`
> **Architecture reference**: `docs/RENDERING.md`（§3 契约 / §4 隐式轨道解剖 / §8 轨道模型——本简报的母文档，随 ADR-044 转正）；ADR-016（契约锁定）；ADR-032（Operation Model）；ADR-044（轨道模型）
> **Naming reference**: `docs/NAMING.md`（§5 枚举注册表 / §6 行话黑名单 / §8 准入即登记；N-38 裸 track 判例）
> **Owner**: TBD

---

## 1. Context

clip-spec 是系统里最后一个"走一步加一步"的架构面：图内核（NodeBase）、能力层（OP ∪ SKILL 双注册表）、产物层（outputs 派生）都已完成各自的"注册表时刻"，唯有渲染契约仍是**每条轨一个手写字段 + N 处消费方特判**——08-14 translation_track 落地实测要摸约 7 处（双端 schema / Clip.tsx 分支 / `_absolutize` / 尺寸规则 / C2PA / ops 寻址），全靠人记，这就是"每加功能前后打架"的力学来源：每个消费方各自重新推导一遍 spec 的结构知识，推导不齐就打架。

设计判据（2026-08-17 讨论收敛）：**操作集闭包**——registry 合法 op/skill 的任意序列（用户聊 N 轮）产出的 spec 仍可表示、可渲染、可继续改。判据的验收物 = **用户真实剪辑顺序 12 项操作走查**（附录 §8 全表）：7 项今天已通、1 项缺登记（reorder_segments op）、4 项（异源插入 / 过渡 / 文字层 / 贴图层）挂在同一次采购上。

形态拍板：**锚定 = 存储格式，泳道 = 编译产物**（存法 C）——位置不落库，输出时间由烘焙缝一次 fold 派生；双真相禁令（锚与绝对坐标不得平级共存于同一行数据）。存法消去推理（A 两病 / B 双主写不存在 / C 两全）与泳道翻案条件归 ADR-044 备选方案节。

**2026-08-17 用户拍板两条**（对本简报的修订）：

1. **允许破坏性更新**——旧数据与旧规划不构成约束，以目标（操作集闭包）为主。"向后兼容"措辞随之清除：静态 `crop` 是缺省语义不是兼容包袱；segments widen 不为存量 JSON 留扭曲默认；§4 禁令一的理由换血（兼容性理由作废，收益证伪才是理由）。
2. **P2 契约提前至本批**——12 操作闭包不等技能排期：segments widen / layers / 锚 / 过渡枚举 / ops 寻址 / 泳道投影与 P0 同批落地。**技能化仍在排期另一侧**：insert/B-roll 技能、LLM op 词汇、checks 首批住户随功能线（08-19 起，见 §7）。

## 2. Current Functional Status

### 已在（本迭代的地基，全部现状代码实证）

- **隐式多道已存在**（RENDERING §4 解剖表）：主轨 `source`+`segments`（源时间轴）/ 数据轨 `caption_track`·`translation_track`（源时间轴）/ 块轨 `music`·`dub`·`title`·`brand.intro/outro`（输出时间轴）/ `crop` 静态单值。
- **时间轴二分已是事实**：`_track` 字段 = 源时间轴经 segments 映射；块字段 = 输出时间轴。映射双向换算集中在 `Clip.tsx` 的 `timeline` 累加 + `sourceTime` 反映射两行。
- **烘焙缝已存在**：`pipeline/rendering.py::_absolutize`——渲染前 fold 的唯一发生地，泳道投影的家。
- **注册表先例已跑通**：`captions.ts` CAPTION_PRESETS（catalog 住 packages/clip、TS 类型由此推导、Python 只校验成员）——轨道注册表的双端形态照此办理（漂移教训在案：`operations/registry.py` 的 set_caption_style Literal 曾缺 `stacking`——轨道表带对账脚本，不裸奔）。
- **写纪律已就位**：render_spec 一切修改经 operations 表 + 快照 undo（ADR-032）；ops 双注册表分层（ADR-033）。
- **规格纪律已在**：样式枚举 + CSS ∩ libass 子集（保 FFmpeg 后路）。
- **排期已在**：第三周 08-17~18 = 本升级（纯地基）；08-19 起 = crop/追踪能力线（crop_track 契约 / speaker_map / reframe_clip）。

### 不在

- 轨道注册表（TRACK_REGISTRY）与两条启动自检（本批）。
- 关键帧数据轨的 schema 形态（crop_track 是第一个；**08-19 线随能力同批**——注册表 + 分区自检落地后，它 = 一条登记 + 一个采样器，忘登记则启动自检直接红）。
- segments 的异源能力（`asset_id` 缺省主源）与段 id（本批）。
- 层轨（layers）、锚（anchor）、过渡枚举（transition）——契约 + 渲染件本批；技能化入口随功能排期（§7）。
- 每轨确定性工艺检查项（checks）的家（本批建家；首批真实住户随 reframe 技能包，§7.2）。
- LLM op 词汇开放、层的画布标记卡呈现（随技能批，§7.3）。

## 3. 改动点（本批 = 08-17~18，ADR-044 同批）

1. **词汇表 + 判例登记**（NAMING §2/§3）：轨道 `track`（裸用违规，必须带家族限定——N-38，N-11 同款）/ 主轨 main track / 段 `segment` / 数据轨 data track / 层 `layer` / 锚 `anchor` / 过渡 `transition` / 块轨 block track，另登记 `TRACK_REGISTRY` / `crop_track` / `speaker_map`。讨论期占位词 lane / blocks / junctions / placements 草稿阶段死亡，不进任何文档。
2. **TRACK_REGISTRY 骨架**：catalog 住 `packages/clip`（TS 类型由 catalog 推导 + 类型级分区断言），Python 镜像只校验成员 + 消费声明（双端对账脚本守门漂移）。`TrackDef` = `family`（sequence|data|layer|block）/ `timeline`（source|output|derived——只声明不实现，remap 全库一个函数）/ `owner`（唯一写者技能）/ `mutex`（dub⇄原声）/ `pairs`（translation⇄caption，既有耦合入档）/ `provenance` / `url_fields` / `checks` / `fields`（spec 顶层字段分区——自检①的承重墙）。现有 8 轨平移登记 + `layers` 轨（layer 家族首条）。
3. **两条启动自检**（挂 `assert_runners_registered`，API/worker 双进程 + harness 同跑）：① spec 顶层字段 ⊆ 注册表，每字段恰好一条轨；② **phantom track**——注册一条假轨，烘焙缝 / 寻址 / 合规 / 计价自动接管、消费方零改动（作 fixture 留存；"渲染"腿的本批语义 = 烘焙缝 `_absolutize` 接管；渲染件注册随真实住户进场）。
4. **消费方 fold**：`_absolutize` 读 `url_fields`；provenance 写点（C2PA 分类路径，ADR-026）读轨声明；estimate 的 `output_seconds` 走注册表驱动的时长镜像。
5. **remap 单函数化**：源↔输出时间换算全库只有一处（TS `sourceTimeAtOutputTime` / `outputTimeAtSourceTime` + Python 同名镜像）——泳道投影与（08-19 的）crop_track 采样器共用。crop_track 契约本体（schema + 采样器 + Clip.tsx 接入）归 08-19 能力线（§7.2）。
6. **segments widen**：段 = `{id, asset_id?（缺省=主源）, url?（异源段随写解析，source 同款先例）, start, end, hidden}`；异源插入 = 带 asset_id 的段（ADR-029 虚拟产物段同源入座）；段可带 provenance（混合时间轴 C2PA 免费）。段 id 新写必带，存量行读容忍（首个时间轴 op 落地时整体回填——旧行无层无锚，回填无损）。
7. **锚 + layers + 过渡枚举**：锚三形态（段锚 `{segment_id + 源偏移}` / 边锚 `{head|tail + 偏移}`——intro/outro 本质即边锚块 / 比例锚 `{ratio}`）；`layers` 条目 `{id, kind, anchor, rect, z, source_ref?, media?, provenance(必填)}`，kind 枚举注册守门（broll / text_callout / pip / motion_graphic）；`transition` 挂段进场边（none/fade/dip，2-3 封顶），换序随段走。ADR-016 L3 注记修订为"枚举可、画廊不可"。
8. **泳道投影 fold + 渲染件**：投影单函数（TS 单家 + Python 镜像）——sequence + layer 家族 → 扁平泳道（绝对输出时间 + z 序）；data 家族不投影（按 sourceTime 采样）；块轨本就输出时间轴。渲染器只吃投影/采样，永不读锚；投影永不落库、永不进快照。`Clip.tsx` 按 family 分派渲染件：层渲染件一支按媒体类型分派（video / image / text，四 kind 共用）、段进场边过渡渲染、多源段渲染（per-segment src）。
9. **ops 闭包**：`reorder_segments` / `insert_segment` / `set_transition` / `add_layer` / `remove_layer` / `move_layer` 登记入 OP_REGISTRY（**LLM 词汇本批不开放**，随技能批）；op 载荷 = 实体引用（段 id / 锚 / 枚举），LLM 永不提议绝对时间码；寻址 = （轨, item_id, op) 对注册表校验；**一轨一写者，撞轨 = 编译期 422**（fork 豁免——派生行各有其 spec）；**派生轨失效声明**（dub 依赖主时间轴——时间轴 op 经注册表枚举失效轨并告知，不产生"合法的谎"）。

## 4. Prohibited Behaviors

- **禁止**把 spec 重构为 `tracks:{}` 容器（收益已在评审中证伪——快照 undo + LLM 不写 spec 的地基上"全量常驻空轨"无收益；扁平 spec + 注册表索引提供全部归属能力。2026-08-17 破坏性授权后本禁令与兼容性无关，是纯目标判断）。
- **禁止**双真相：同一行数据里绝对坐标与锚平级共存；泳道只是编译产物，永不可写、永不落库、永不进快照。
- **禁止** LLM 提议绝对时间码——op 载荷 = 实体引用（段/锚/枚举），坐标计算永远归代码（LLM 提议、代码裁决的编辑侧延伸）。
- **禁止** NLE 自由轨语义进 spec（任意增删道 / 同道重叠 / 转场画廊 / 关键帧自由编辑）；kind 全部枚举注册表守门。
- **禁止**用户面出现轨道概念（UI 永不见轨；层条目呈现为"这段配了画面"标记卡，随技能批）。
- **禁止** `overlay` 一词用于视频层（已归 UI 浮层：GenerationOverlay / overlay-surface——避让 N-27 同型一词两义）；视频层统一用 `layer`。
- **禁止**每轨多写者：一条轨一个 owner 技能；撞轨 = 编译期 422，不做运行时合并。
- **禁止**绕过注册表给单轨加特判分支（NAMING §5 / CHAT_ARCH §4 扩展门纪律同律）。

## 5. 验收

1. 两条启动自检绿：spec 字段 ⊆ 注册表对账；phantom track 全链接管（烘焙缝 / 寻址 / 合规 / 计价零消费方改动，fixture 留存）。
2. remap 单函数：grep 证明源↔输出时间换算全库只有一处（TS）+ 镜像（Python）。
3.（归 08-19 线验收）crop_track 双端 parity：`<Player>` 与渲染服务同一采样函数，抽帧对比一致（parity 回归同款测法）。
4. **十二操作走查表（附录 §8）全项 ✅**——结构级：每操作可表示（契约座位）/ 可渲染（渲染件 fixture 实证）/ 可继续改（op 注册 + 快照 undo）；技能化入口随 §7 排期，不在本批验收面。
5. 剧本测试（S1–S45）零回归；改 pipeline 代码必重启常驻 worker。
6. ADR-044 落档，RENDERING §8 转正式契约。

## 6. 分期与排期锚点

| 期 | 内容 | 挂点 |
|---|---|---|
| 本批 | 本简报 §3 全部（契约层 + ops + 渲染件 + 两条自检） | 第三周 08-17~18 |
| P1 | **`crop_track` 契约双端落地**（schema + `crops.ts` 采样器 + Clip.tsx 接入 + parity 抽帧验收）+ checks 首批住户（crop 不出人脸框 / 最短驻留 / 防跳切缓动，写进技能 procedure 不等 Phase 3）+ `speaker_map` 节点与上游登记 + 素材形态归类 | 08-19 起 reframe 线（spike 双验证前置闸，未过则静态中裁回退） |
| 功能批 | insert/B-roll 技能化 + LLM op 词汇开放 + 层的画布标记卡呈现 | 随功能排期（§7.3 登记，PROGRESS 需求池待排） |

排期纪律：本迭代是 crop_track / reframe / 分镜双子卡三条已排期线的**随行文书**——契约层 08-17~18 一次做完；能力层随 08-19 起的排期。

## 7. 配套 agent / skill / tool 层（2026-08-17 补录——五句小白语录 × 六步拆解评审的收编）

**边界先行：总 agent 不变。** chat loop / PlanAgent / ChatIntentAgent 零改动；单次调用 + 预装配上下文、禁 ReAct 的纪律辩护到底（成本、可评审、确定性全在这）。**skill 按用户语言命名和切分，不按轨道切分**——「说到工厂时配工厂画面」是一个技能，「插入 layer」不是；轨道是内部坐标系，永不上用户话术面。

1. **tools 层：本批零新增**。泳道投影 / remap 是 pipeline 镜像函数（NAMING §1 双端同名纪律），不进 tools/。
2. **08-19 线（reframe 能力批）**：`crop_track` 契约双端落地（`family=data, timeline=source`，`{t, x, y, scale}` 关键帧按 sourceTime 采样，空轨 = 静态 `crop` 缺省——本批地基交付后此项 = 一条登记 + 一个采样器）。`speaker_map` 内部分析节点（素材级、asset-hash 复用、`NodeBase.internal` 声明、不进 SKILL_REGISTRY）——**顺手把素材形态归类（访谈 / 独白 / 多人）升为素材级事实**，喂计划层与工艺分发（语录评审裁决①的"缺语义归类"在此补上）；视觉判定 agent 声明随节点（AGENT_ARCH 先例）。`reframe_clip` 过 NAMING §7 评审登记；checks 首批住户（crop 不出人脸框 / 最短驻留 / 防跳切缓动）写进技能 procedure，不等 Phase 3 verify 框架（裁决⑤——reframe 是第一个"失败 mode 肉眼才看得出"的技能，工序自检必须同批出生）。spike 双验证（说话人识别 + 中景追踪）是前置闸，未过按 PROGRESS 回退口径走静态中裁版。
3. **insert_broll 技能线（layers 家族第一个技能住户）**：语录④「我讲到增长数据那块，画面切到我的幻灯片」——知识专家最强的 B-roll 场景（自己的幻灯片/截图，`slide_pages` 已存在）；原缓议理由（"talking-head B-roll 价值低"）只覆盖 stock B-roll，**排期理由修订在案，排在 reframe spike 之后**（PROGRESS 需求池待排）。全链拆解（语录评审已锁定）：(a) spec `layers` 座位（本批已落）；(b) 技能 = LLM 只做语义定位（"哪句讲了增长数据"），机械工序取该 cue 的输出时间窗 + 从 SLIDES 素材 slide_pages 选页 → layer 条目；(c) 渲染件（本批已落）。
4. **计划层对素材盲**（语录评审①，"该修"项）：正解 = 素材理解前移（director_understand 挪上传时跑——素材级 + hash 复用天然支持；代价 = 每次上传烧一次 LLM，哪怕素材从没被用）；折中 = 上下文装配层塞 transcript 首段摘录（机械、零 LLM）。**本简报收折中版**（挂第三周 08-21 缓冲行），正解进 PROGRESS 需求池。
5. **SSE 收官散文回合**（语录评审⑥）：run 收官时在打勾流 recap 之外追加一个 assistant 收官回合（"做好了 3 条短片，第 2 条最强因为……；下一步建议：……"）——一次调用、成本极小，是"到来即彷徨"用户的闭环接住点（STRATEGY §5）；不是进度（不违 ADR-041 打勾流唯一进度面），是收尾。进 PROGRESS 需求池。

## 8. 附录：12 操作走查全表（操作集闭包的验收物）

| # | 用户语言（真实剪辑顺序） | 内部落点 | 本批前 | 本批后 |
|---|---|---|---|---|
| 1 | 上传素材 → 视频轨出现 | `source` + `segments`（主轨，唯一持剪辑语义） | ✅ | ✅ |
| 2 | 搜索/替换/调整音乐 | `music` 块轨；add_music / set_music | ✅ | ✅ |
| 3 | 生成/重生成字幕、调样式 | `caption_track` 数据轨 + preset 枚举守门 | ✅ | ✅ |
| 4 | 字幕多语言 | `translation_track` 数据轨 + translate_clip（fork 派生） | ✅ | ✅ |
| 5 | 重排片段顺序 | segments 数组换序（输出 = 数组序，remap 逐段组合） | 🔶 缺登记 | ✅ `reorder_segments` op |
| 6 | 替换素材 | 时段窗不可跨素材迁移 → 技能链在新素材上重跑（语义重锚；ADR-040 配方=提示词原生支持） | ✅ | ✅ |
| 7 | 插入其他画面 | **语义分流，用户永不感知**：盖（原声继续）→ `layers` 条目 `{kind:"broll", anchor}`；切（声画都换）→ 主轨带 `asset_id` 的段。"剪两段、尾段后移"这个操作不存在——输出轴派生，插入后尾部自动正确 | ❌ | ✅ segments widen + layers |
| 8 | 过渡淡入淡出 | 段进场边 `transition:{kind: fade|dip, duration}`，枚举封顶，换序随段走 | ❌ | ✅ |
| 9 | 文字轨置顶 | `layers` 条目 `kind:"text_callout"`（锚 + rect + z） | ❌ | ✅ |
| 10 | 小动画/贴图 | `layers` 条目 `kind:"motion_graphic"` | ❌ | ✅ |
| 11 | 增删轨道 | 层条目增删 op（`add_layer` / `remove_layer` / `move_layer`——载荷 = 锚引用非时间码） | ❌ | ✅ |
| 12 | 配音/换声 | `dub` 块轨（与原声互斥，注册表声明） | ✅ | ✅ |

反复修改（语录里的"其他可能性会一直重复"）= 闭包判据本身：ops 永远动锚定面，聊 N 轮不漂移，快照 undo 不变。
