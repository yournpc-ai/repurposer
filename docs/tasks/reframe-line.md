# Reframe 能力线（智能分镜）实施简报

> Status: **施工中**（2026-08-19 开工；08-18 拍板，ADR-045）
> 排期锚：`docs/PROGRESS.md` 第三周（08-19 ~ 08-20）；决策：`docs/DECISIONS.md` ADR-045；轨道地基：ADR-044 + 08-18 冷审修复批。

## 1. Context

两个真实素材形态（用户确认静态访谈机位）：

- **双人同屏静态访谈 → 竖屏单人切换**（谁说话切谁）——`demo/uploads/xy_1.mp4` 已策展
- **单人中景动态追踪**（登台演讲，人在台上走动）——`demo/uploads/xy_2.mp4` 已策展

轨道模型地基已交付：crop 轨已登记（`fields=("crop",)`，owner = 出生技能），crop_track 进场 = TS 分区一项 + Python TrackDef 一条 + 一个采样器。模型选型已拍板（ADR-045）：**YuNet（MIT）vendor 入仓**，SCRFD 非商用权重禁用。

## 2. Current Functional Status

已有：

- `crop` 静态单值（出生默认，transform 实现）——crop_track 的退化形态
- whisper 词级时间戳（faster-whisper 自托管，`tools/asr.py`）
- MiniMax M3 多模态 client（`app/clients/minimax.py`）
- TRACK_REGISTRY 双端 + 一轨一写者 422 + 派生轨失效声明
- `Asset.meta` 落素材级事实的先例（`language`）

缺口：无检测引擎、无话轮归属、无 crop_track、无 reframe 技能、无防眩晕约束。

## 3. 改动点（本批 = 08-19 ~ 08-20）

1. **双验证 spike 结论（前置闸）**——双路对照：`xy_1` 上 YuNet 检出率 + 嘴部能量归属准确率；`xy_2` 上 YuNet 追踪连续性。结论数据入 PROGRESS；未过按回退口径（演讲短片卡先出静态中裁版，go/no-go 最坏 10-30）。
2. **`tools/vision.py` 引擎缝**——YuNet 权重 vendor 入仓（`face_detection_yunet_2023mar.onnx` 232KB + MIT LICENSE 并置）+ `opencv-python-headless` + asr.py 同款懒加载进程缓存；输出 = bbox + 5 点关键点。
3. **speaker_map PROCESSOR**（VIDEO/AUDIO 第二处理器，接 ASR 后）——形态闸门（whisper 话轮密度 + 1~2 次 M3 网格判多人/访谈）→ 全量归属（嘴部 ROI 帧差能量主，M3 模糊仲裁辅）；落 `Asset.meta.speaker_map = {form, speakers, turns}`。
4. **crop_track 契约双端落地**——`TRACK_FIELDS` + `TrackDef` 各一项；schema（`[{t, x, y, scale}]` 稀疏决策关键帧，源时间轴）；渲染采样器（固定 smoothstep ~8 帧，keyframes 族第一个渲染件）；Python 孪生 + parity 抽帧逐值相等。空轨 = 静态 crop 语义不变。
5. **防眩晕写侧约束**——最短驻留 / 死区 / 最大转速，参数以真实访谈片反复看调（初值：驻留 ≥1.2s、能量比阈值 1.6×、切提前 ~0.2s）。
6. **reframe_clip 技能包**——三模式 `interview_split` / `speaker_track` / `static_center` + `auto`（按 `speaker_map.form` 选模）；NAMING §7 评审登记（reframe_clip 与三模式名皆为候选）；`TrackDef.owner` 登记 crop 轨；估价按素材时长；对话可调用走 task_list。
7. **08-20 双人访谈端到端验收**——`xy_1` 进 → 竖屏单人切换 clips 出，说话人切换正确。

## 4. Prohibited Behaviors

- **禁 InsightFace/SCRFD 预训练权重及任何 HF repack**（非商用学术许可）；禁蒸馏其权重产伪标签。
- **禁人脸识别**（身份判定）；只有位置与嘴部运动，全程不出网。
- **禁 M3 逐帧追踪**（贵且抖）；M3 只做形态归类 + 模糊话轮仲裁。
- **禁 crop_track 稠密逐帧数据**；禁防眩晕参数进契约（渲染常量 smoothstep，写侧约束归技能工序 + checks）。
- **禁 LLM 提议绝对时间码**（ops 载荷实体引用不变）；六 op 继续 `llm_visible=False`，本批不开放 LLM op 词汇。
- **禁 tools/ 进工序**（引擎缝豁免仅 vision.py，ADR-045 第 1 条）；禁 ReAct；总 agent 不变。
- **禁 checks 字段先注册空座位**——回归必须与消费方同一次提交（冷审纪律）。
- 渲染件只进 packages/clip；CSS ∩ libass 子集纪律不动；ADR-016 L3 边界不动。

## 5. 验收

- spike 双路对照数据入档（YuNet 检出率 / 嘴部能量归属准确率 / 追踪连续性）。
- crop_track 双端 parity 抽帧逐值相等；采样器空轨退化 = 静态 crop 像素级一致。
- 对 AI 说"把这条换成分镜模式"就变；成片切换不晃眼（最短驻留生效）。
- 双人访谈端到端：真实素材进 → 竖屏分镜 clips 出，说话人切换正确。
- harness 44 剧本零回归；tsc（clip+web）+ compileall + 双启动自检绿。

## 6. 分期与排期锚点

- **08-19**：本简报 §3 第 1~6 项（spike 结论先行，闸住后续形态）
- **08-20**：端到端验收 + 修复
- **08-31**：本人含量门禁 v2（speaker_map 第二消费方，PROGRESS 第五周）
- **需求池**：insert_broll（spike 结论后，layers 家族第一个技能住户）；checks 首批住户随 reframe 包回归（crop 不出人脸框 / 驻留达标 / 字幕不溢出）

## 7. 模型选型记录（ADR-045 全案）

| 角色 | 选型 | 许可 | 形态 |
|---|---|---|---|
| 人脸检测引擎 | **YuNet** `face_detection_yunet_2023mar.onnx` | MIT | vendor 入仓（232KB），`tools/vision.py` + `opencv-python-headless` |
| 话轮切分 | whisper 词轴（存量） | MIT（faster-whisper） | 间隙 ≥0.6s 断轮 |
| 话轮归属 | 嘴部 ROI 帧差能量（主） | 自研工序 | 静态机位专用 |
| 模糊仲裁 / 形态归类 | MiniMax M3（存量 client） | 云服务（既有姿势） | 每片 1~5 次封顶 |
| 翻案阶梯 | MediaPipe（Apache-2.0）→ 购 SCRFD 商用授权 → 自训 | — | 条件见 ADR-045 Alternatives |
