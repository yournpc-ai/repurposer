# craft anatomy 证据表（期 0 解剖，2026-08-22）

> Status: 原始证据层（期 0 产出，尺子先行——期 2/期 3 施工顺序由本表决定）
> 方法：`apps/api/scripts/craft_anatomy.py`（三源测量：clip-spec 契约 + ASR 词轴 + MP4 实渲）× `apps/api/scripts/run_anatomy_matrix.py`（四张 live 卡 × demo/uploads 策展集 + xy_1/xy_2 全片真跑，诚实默认皮肤 brand=null，验证 run 用完按 FK 序清）。
> 判片纪律：帧目录按 take 隔离 `<label>-<content_md5[:8]>`（`data/anatomy/frames/`）；烘焙 demo URL 的内容哈希与实测 md5 逐一对齐（`reframe-vertical-7bcbb54e` ↔ md5 `7bcbb54e…` 等四例全中）。
> 先验口径：简报 §2.1 全部数值 = 编辑部惯例先验，**本表产出校准值前不作验收标准**（简报 §6.3）。verdict 的 gap/ok 一律对照先验读出，不是验收结论。
> 链形标注：materialize 链（整条源）的切频/收束/死寂记 source-inherited，不归产品账。
> 样本：subs / image-video 各 1 轮；highlight / reframe 各 2 轮（第二轮 = 修正后测量口径；两轮 LLM 选段不同，系统性发现跨轮一致才下判）。

## 0. 跑批矩阵与产物

| 卡 | 素材 | 链 | 产物 |
|---|---|---|---|
| multilingual-subs | `xy_2_15s.mp4`（15s 方幅登台） | materialize → translate zh 双语 + translate fr + dub es（全 fork） | 4 clips，14.7s |
| image-video | `demo-article.md` + 3 张 teasers 照片 | understand → plan → align_stills → select_clips ×3 → add_music | 3 stills clips，13.7 / 18.8 / 16.9s |
| highlight-clips | `xy_2.mp4`（780s 登台全片） | understand(11 论点/10 金句) → plan → select_clips ×3 → reframe auto→follow | 3 clips，32.0 / 48.6 / 30.0s |
| reframe | `xy_1.mp4`（全访谈） | understand(5 论点) → plan → select_clips ×3（92s/70s/113s 段） → reframe auto→switch | 3 clips，42.2→92s 段 / 26.6→70s 段 / 60.9→113s 段 |

## 1. 头条结论（四层归因汇总）

**"图片轮播+浮字"的解剖学 = 决策层只到 what，契约没有 timeline 字段，渲染只能均分。** 图文视频的 clip plan（钩子/金句/选段）质量可读；失败全部发生在 plan 之下——clip-spec 的 stills 族没有 dwell/motion/emphasis 任何一个字段，渲染端 `splitFrames` 均分是唯一行为。**缺层归因被三源数据坐实：storyboard（WHAT）与 clip-spec（怎么渲）之间没有 timeline 创作者。**

talking-head 侧的同构发现：select_clips 的选段决策可读（钩子句/分数/边界可辩），但**贴词切零气垫 + 尾停 0s + 强调事件恒 0 + 感知重取景恒 0**——四条系统性缺口全部落在"逐拍决定无 owner"上（locate_span 常量 + 无强调机制 + 无注意力复位机制），与 DAG/工具纪律无关。

**数据层健康**：ASR 词轴、speaker_map、视觉检出（眼位全程在轨）全部在线；缺的是 prosody（韵律）与 visual_anchors——期 1 供给。

## 2. 图文视频家族（image-video 卡，stills）——用户点名痛点

| 规则 | 先验 | 实测（3 clips） | 归因 | 校准方向 |
|---|---|---|---|---|
| 图停甜区 | 均停 2.4–4.8s；永不 <1.3s / >4s | **均分 4.53 / 6.23 / 5.6s——全部超 4s 上限**，图间无差异 | 契约：spec 无 dwell 字段；决策者：plan 无图片编排；数据：3 图喂 13–19s 片段填不满甜区（素材贫困无人对账） | 期 2 剪辑师产出真分布后校准 |
| 切在意义上 | ±200ms | **0/6 切点在 ±200ms 内**（最近 0.75–5.3s） | 契约：均分切点零词轴感知 | 校准后应 ≥80% |
| 运动带原因 | KB 1.05–1.20×/段、交替方向 | **0 运动事件** | 契约：stills 无运动字段（功能不存在） | 期 2 新增字段时定取值域 |
| 强调隔离 | ≥60% 强调词获强调 | **0 强调事件** | 契约无机制 + 数据无强调词（期 1 供给） | 待期 1 emphasis_words |
| 结构呼吸 | 每 12–18s 复位 | **0 复位**（片长 13.7–19s） | 契约 | — |
| 音频闪避 | BGM -18~-22dB；人声 -14±1 | gain_db=-18 ✓；输出 -17.2~-18.1 LUFS（music-only） | 渲染：music-only 产物是否同取 -14 = 先验适用性问题 | music-only 基准单列 |
| 视觉钩子匹配 | 首图 ≤0.6s + 主体对应首强调短语 | 首图 t=0 ✓（构造性）；**主体匹配无机制**（图序=上传序） | 决策者：图序无人管 + 数据：无 visual_anchors（期 1 供给） | — |
| 字幕节奏 | 短语式 ≤2 行 32–42 字符 | 7 词/行，行停 2.69–2.79s（估算轴） | 渲染展示常量 groupLines=7；规则注明风格二选一属皮肤层 | 短语式成立；karaoke burst 是另一皮肤预设 |

**人工判（主观项）**：钩子可读（"The next industrial race isn't about buzzwords." 开片即论点重构），收束有 call——**决策层 WHAT 不背锅**；轮播感全部来自 plan 之下的均分执行。

## 3. talking-head 家族——subs 卡（materialize 整条源，4 fork）

| 规则 | 实测 | 归因 |
|---|---|---|
| 钩子延迟 | **0.0s ✓**（ES dub 0.1s） | 数据：片源自带钩子；materialize 无 lead-in 可验 |
| 钩子有料（人工判） | 开场句 = 登台开讲，非全片密度最高句——subs 卡卖整条+字幕，钩子职责不在此链 | 链职责边界（先验适用性） |
| dead air | 1 处 0.78s @10.5s | source-inherited |
| 强调跟韵律 | **0 强调事件 vs 能量峰 3–4 个/片** | 契约无机制 + 数据无韵律（期 1 供给） |
| 字幕节奏 | 7 词/行；行停 EN 3.08s / FR 2.73s / ES 2.39s；字幕确译；双语对照轨在 | 渲染展示常量 |
| 响度 | -16.17（EN/ZH/FR）/ -15.73（ES dub）LUFS | 渲染归一在产线；与 -14 目标的口径差 → §5 校准 |
| 眼位/脸宽 | 0.570 / 0.023——source-inherited（不裁决） | 素材自身构图 |

## 4. talking-head 家族——highlight / reframe（select_clips → reframe）

| 规则 | 先验 | 实测（两轮 × 3 clips） | 归因 | 校准方向 |
|---|---|---|---|---|
| 钩子延迟 | ≤300ms | **0.0s 全绿**；但=贴词切的另一面（见下行） | 契约：locate_span 对齐词界 | — |
| 思维边界切 | 前垫 100–150ms、尾垫 150–200ms；边界 ±180ms | **pre_pad / post_pad 系统性 0.0s**（6/6 片）；切点前后本有 0.46–1.66s 停顿可用——**气垫存在，契约不取** | **契约**：locate_span 把选段秒数吸附到词界，零 padding 参数——零气垫是构造性的 | 期 2 beat plan 带 pad 字段（先验 100–150/150–200ms 待实测耳校） |
| filler/死寂 | >600–800ms 停顿与 filler 移除 | 死寂 0.68–2.32s 保留（每片 1–4 处；**2.32s 死寂进了"高光"片**）；filler 0 | 决策者：select_clips 不做片内清理（remove_filler 工具存在但不在卡链）；契约：链构成问题 | 死寂上限先验 0.6–0.8s 与实测分布吻合 |
| 强调跟韵律 | 强调对齐音高/能量峰 | **0 强调事件 vs 能量峰 7–29 个/片** | 契约无强调机制 + 数据无韵律（期 1 供给） | 期 1 prosody 落地后测对齐率 |
| 字幕节奏 | 短语式 32–42 字符 | EN 行中位 32.5–40 字符（p90 45–46 微超）；ZH 行 13–16 字符 | 渲染 groupLines=7 常量 | 先验是 EN 口径；zh 等价带待校准（14 字/行实测可读） |
| 切频包络 | 无静态镜头 >8–10s | **max_static 21.6–70.1s**；**感知重取景：follow 卡 3 片 keyframe 微漂移 0.003–0.022 → 0 次感知级**；switch 卡 deltas 0.67–0.74 → 感知正确；一片 70s 零关键帧全静态 | 契约/层缺：防眩晕写侧约束把 follow 压成亚感知（正确的设计），但**注意力复位无其他机制**（无 zoom 强调/无 B-roll/无切镜节奏层）——静态不是 reframe 的错，是缺层的症状 | 先验应按"感知重取景"口径测（deltas ≥0.05），不是 keyframe 计数 |
| 收束 | 尾帧停 ≥1.8s | **0.0s 系统性**（尾垫 0 = locate_span 同源性） | 契约 | 期 2 beat plan 尾拍字段 |
| 眼位 | 35–45% 帧高 | **0.388–0.410 全在轨 ✓** | 数据+契约健康（reframe 竖向构图有效） | — |
| 脸宽 | 30–50% 帧宽 | **访谈 0.250 / 登台 0.121，两轮稳定** | 先验口径问题：30–50% 是特写 talking-head 数；产品点名卖"大型中景"（RECIPES §4.3） | **校准：访谈 0.25±0.02 / 舞台中景 0.12±0.01 入先验带**；是否该更近 = 产品判断（走查裁决），非解剖结论 |
| 选段长度 | （规则外观察） | reframe 卡选出 70–113s 长段（访谈答案自然长度） | 决策者：count=3 下 clip_writer 取完整问答 | 长段 + 无复位机制 = 死寂感的放大器 |

**渲染抖动注记**：reframe 第二轮首跑 3/3 render 瞬时失败（同 spec 手工重放 200——网络抖动类，与 08-14 Google Font 超时同族），重置 PENDING 后全部自愈。渲染服务零重试 = 需求池「渲染服务源站限速韧性」同族问题，本表不展开。

## 5. 先验校准区（解剖产出）

1. **字幕双轨制成立**：karaoke burst（1–3 词/200–800ms）与短语式（7 词/行、EN 32–40 字符中位）是两个皮肤预设各自的正确形态，不作 gap；补字符数测量（已入脚本）。zh 行字符带待补语料校准。
2. **脸宽先验分档**：特写 talking-head 30–50%（原值）；访谈 reframe 实测 0.25±0.02；舞台中景 0.12±0.01。后两档入先验表（期 2 剪辑师的构图目标值）。
3. **响度口径**：全线产物 -15.7 ~ -18.1 LUFS，系统性低于 -14 目标 1.5–4 dB。渲染黑盒的归一目标/混音结构待查（渲染服务内部，ADR-016 不破）；music-only 与带人声产物基准分列。
4. **切点气垫**：先验 100–150/150–200ms 待耳校；实测基线 0/0（构造性）。期 2 落地后同表复测。
5. **感知重取景口径**：keyframe 计数不作数，|Δx|+|Δy|+relΔscale ≥ 0.05 才算一次（本期 0 校准）。
6. **死寂上限**：先验 0.6–0.8s 与实测病灶分布（0.68–2.32s）吻合，维持。

## 6. 期 2/期 3 施工顺序建议（证据驱动）

- **期 2 剪辑师首接 stills 被数据再次确认**：图文视频家族的契约缺口最多（dwell/motion/emphasis/图序四个字段全缺），且是用户点名痛点。
- **talking-head 的低成本快赢随期 2 同批**：locate_span 加 pad 参数（前垫/尾垫/尾停）= 契约小改、收益直接（"机器人跳剪"与"就这么没了"两症状的根）。
- **期 3 质检环的确定性检查 = 本脚本指标集**（scripts/craft_anatomy.py 晋升 app 侧 verify 节点消费方）；judge 只管主观行（钩子有料/收束/图序匹配）。
- **数据层期 1 补齐即可用**：prosody（强调声学半）、emphasis_words 语义半、visual_anchors、filler_regions——全部已在期 1 范围，无需新地基。

## 7. 脚本与复跑

- `apps/api/scripts/craft_anatomy.py`——三源测量引擎；`--selftest` 校验音频链（1kHz 满幅正弦 → -3.00 LUFS，BS.1770 手卷实现过校验）。
- `apps/api/scripts/run_anatomy_matrix.py`——四卡矩阵跑批（worker + render 需在跑；FK 序清理，`--keep` 留档；渲染瞬时失败自动终止，重置 PENDING 可续）。
- 证据 JSON：`data/anatomy/<card>.json`（decision_layer 全量 + 每片 metrics + 嵌入 render_spec 供离线复算）。
