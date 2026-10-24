# Film 编排与持续修改——会话级施工清单

> Status: 待执行。总设计唯一事实源 = `docs/tasks/film-storyboard-orchestration.md`（v3.1），本文只组织任务、不重复设计全文；每轮引用总设计章节号。
> 交接模板 = `docs/tasks/film-storyboard-orchestration-handoff.md`。

## 0. 全局约定

- **每轮格式**：目标与范围外 / 前置 / 模块与接口 / 任务 / 验收 / 停止点与移交。每轮应尽量在一次上下文窗口内完成；**第一次 compact 后只收尾当前小项 + 验证 + 交接**，不赶新任务。
- **交接纪律**：实际施工状态落盘到 `docs/tasks/film-storyboard-orchestration-progress.md`（当前轮次/完成项/变更文件/验证结果/未验证项/风险/flag 状态/工作区修改归属/下一轮准确起点），每轮收尾更新；新会话读它即可继续，不依赖聊天搬运。handoff.md 只存模板，永不预填。
- **仪式链按改动面执行**：pytest 受影响套件 + check_gates 每轮必跑；触及 prompt 面加 prompt_gate；触及 web/render 加 tsc/vitest；触及旅程加剧本矩阵对应座。**完整回归只在 R9**。
- **授权边界**：不付费生成、不部署、不改生产数据、不碰原事故项目 14fa16b6。**本地/stub 验证优先**；剧本矩阵等真实 LLM/TTS/渲染调用属付费面，**不在默认授权内**——需要时另列范围与预算请求授权后执行。各轮验收中的「剧本座/S11/真实旅程」项在获授权前以 stub/纯测试替代并标「未运行（待授权）」。
- **「翻牌」定义**：清单中的 flag 切换（链 flag / compose flag）仅指**本地/测试环境**的配置或代码默认值切换；线上部署与生产配置修改不在本期授权范围。
- **文档同批义务**：代码改动当批同步登记——新表/内部节点入 MODULE_ARCHITECTURE §4/§7；ADR 修订随批落档 DECISIONS.md；现行法文档在 R9 收口。
- **拆分预案**：标注「拆分预案」的轮次若明显超大，在预案点切开移交，不勉强赶完。

## 0.5 轮次总览与依赖校正

| 轮 | 内容 | 前置 | 估时 |
|---|---|---|---|
| R1 | G0：异常日志与连接检查 | 无 | 1d |
| R2 | 版本、scene ID、编辑操作 | R1（软） | 1.5d |
| R3 | Chat 作品读取与图片机制 | R2；首日 = 图片 spike | 1d |
| R4 | 旁白复用与画幅变体闭环 | R2；首日 = 旧作品 provenance 抽查 | 1.5d |
| R5 | 宏执行阶段拆分、Tasks 与恢复（**链 flag 默认关，本地/测试可开**） | R4；首日 = 注册链兼容验证 | 2d |
| R6 | 结算边界与失败注入矩阵（**默认值切换**，本地/测试） | R5 | 1d |
| R7 | 自由编排恢复（compose flag 测试开、默认关） | R2 | 2.5d |
| R8 | 字段级修复与全局重试预算（compose 默认值切换） | R7 | 1.5d |
| R9 | 全链验收与收尾 | 全部 | 1.5d |

合计 ≈ **13 个工作日**（总设计 11d + 逐轮验证开销 2d，据实不重估批内容量）。

**依赖校正（相对总设计 §13 的三处调整）**：

1. **阶段拆分与结算不同轮，但链黑暗落地**——R5 只落链（flag 默认关，本地/测试可开；代码默认路径仍单体），R6 落 capture 单座改造 + 注入矩阵后**才切换默认值**。不变式：任何中间版本都不会出现「链已启用而 capture 口径未改」的状态（错误收费行为零窗口）。R2–R4 的编辑/变体 run 走单体节点，结算语义 = 现状单步座，天然正确。
2. **旁白复用断言分段收口 + 编辑路径内部测试期**——R2/R3 落地的编辑 ops 与读取机制**保持内部测试状态**（纯测试/剧本可达；能力菜单与交付建议不开放，不接临时用户流程）；interim 旁白策略为全量重合成（仅为内部测试口径，不作为开放依据）；复用 store 随 R4 接入合成路径（单体 narrate 段先用，R5 的 narrate 节点沿用同座），**R4 完成读取+复用+变体闭环后统一启用本地完整编辑路径**，闸 6/7/8 的复用腿同此收口。
3. **compose 默认启用后置到 R8 末**——R7 落码自由编排但默认仍槽位道（director mode flag，本地/测试可开），字段级修复就位 + S11 绿后 R8 切换默认值；避免无字段修复时代的低一次通过率进入默认路径。

**早期验证项归位**：MiniMax tool-role 图片 spike → R3 首日；旧作品 provenance 完整率抽查 → R4 首日；注册链兼容定点验证 → R5 首日；结算注入矩阵 → R6 本体。阻塞证据出现再报告，不把未知写成已验证。

---

## R1 — G0：异常日志与连接检查

- **目标**：SSE 回合异常全堆栈日志；engine 连接活性；机制级回归。
- **范围外**：事故项目复跑/改记录；任何 film 行为改动。
- **前置**：无。
- **模块与接口**：`app/chat/routes.py:652` 回合异常座；`app/models/database.py:12-16` engine（总设计 §4）。
- **任务**：① 异常座补 `logger.exception`（带 project/turn 上下文，用户文案经 `_failure_detail` 的行为不变）；② engine 增 `pool_pre_ping=True` + `pool_recycle`；③ 测试：注入回合内异常 → 日志含堆栈；连接被关闭后请求自愈。
- **验收**：两测试绿 + pytest 受影响套件 + check_gates。
- **停止点/移交**：无 film 改动；R2 可直接开。

## R2 — 版本、scene ID、编辑操作

- **目标**：场景稳定 id；编辑 ops（`update_scene`/`reorder_scenes`/`remove_scene`/`set_music`/`set_voiceover(false)`）原子应用座；change_set 四类变化；版本形状扩展（created_via/change_set/constraints_choice，读容忍）；观察返回文本视图清单；授权新法落地；能力文案收窄；edit 报价分叉（实际板秒数 + interim 全量 tts_chars）。总设计 §7.1/§7.2/§7.4/§11。
- **范围外**：`set_aspect`（R4）；复用 store（R4）；图片携带（R3）；compose（R7）；validator 语义分层（R7，本轮 validator 现状规则不动）。
- **前置**：R1（软依赖，排障用）。
- **模块与接口**：`models/schemas.py`（FilmScene 各型 + `DesignStoryboardArgs.edits`）；`tools/film/storyboard.py`（film_design_state / digest / validate 签名）；ops 应用新座（建议 `tools/film/edits.py`）；`chat/propose_turn.py` / `plan_turn.py` 的 `_design_storyboard` 分支；LaunchFilm 消费侧不动（digest 门禁现状）。
- **任务**：① scene id 读容忍 + legacy 位置派生升级；② ops pydantic 联合 + 应用座（有序、原子、失败零落库、保留原版）；③ change_set 计算（moved/edited/retimed/presentation/music/warnings）；④ `_design_storyboard` edits 分支（base 解析 → 应用 → 校验 → 新版本 + change_set 呈现）；⑤ ADR-134 修订落地 + DECISIONS 落档；⑥ 注册表能力文案收窄（只列已实现 ops）；⑦ edit 报价分叉。
- **验收**：纯测试（ops 应用/保留 digest/原子失败/reorder 仅序变/change_set 分类）；闸 2（edit 零导演）、6/7 的 digest 腿、12、15、19 的 R2 范围；C/D/E 旅程剧本形态断言（E 音频窗腿 interim 写实 = 全量重合成）；仪式链按面。
- **停止点/移交**：编辑路径保持**内部测试状态**（能力菜单/交付建议不开放，无临时用户流程）；闸 6/7/8 复用腿 → R4；set_aspect → R4；图片 → R3；R4 闭环后统一启用本地完整编辑路径。**拆分预案**：①-④（契约+应用座+纯测试）/ ⑤-⑦（chat 接线+授权+报价）。
- **注意**：aspect 仍在内容指纹内（参数两分随 R4）；本轮能力文案收窄后系统不再主动建议变体，用户自发画幅请求走诚实「暂不支持」；事故的「重呈现被指纹顶回重设计」路径由 R4 变体链覆盖（以闸 2/3 实证为准，不作绝对化承诺）。

## R3 — Chat 作品读取与图片机制

- **目标**：`get_output_spec` film 分支（当前版本事实 + 候选视图清单）；读工具结果带图机制；预算帽与超预算显式报错。总设计 §7.2 读取座。
- **范围外**：导演侧视觉扩容（R7 的 `page_media_inputs`，不同座位）。
- **前置**：R2（读取对象 = 新版本形状）。**首日 = MiniMax tool-role 图片 spike**（实测探针；不支持则走 synthetic user 消息兜底——与导演 media inputs 同构的已验证形态）。
- **模块与接口**：`chat/perception/executes.py:489`；`agents/base.py:286-291` 纯文本通道（机制改动点）；chat loop 装配（`intent.py`）。
- **任务**：① spike 并落档结论（支持与否 + 选定形态）；② 图片携带机制（预算 ≤12 张 640px + 单张 1280px 高清按需；超预算显式报错不静默丢图）；③ get_output_spec film 分支（版本/digest 前缀/逐场 id·类型·秒数·视图·取景文本·旁白状态/音乐/画幅 + 视图清单带图）。
- **验收**：纯测试（投影形状/预算帽/超预算报错）；一条真实读图旅程 smoke（编辑模型读到图并正确点名视图——人工核验，标未运行则不宣称）。
- **停止点/移交**：spike 阴性不阻塞——兜底即定型。

## R4 — 旁白复用与画幅变体闭环

- **目标**：`film_narrations` 表 + 原子占位并发律 + 复用接入合成路径；参数两分（aspect 出内容指纹）+ delta 分类器；`set_aspect` op + 逐 aspect 取景重查；变体 run（新 Output 同 work_id）；provenance 按需收割；变体报价；S11b 剧本座。总设计 §7.2/§7.6/§9.4/§10.1/§10.2/§12 主旅程后半。
- **范围外**：宏阶段拆分（R5）——复用 store 本轮接入单体 narrate 段，同座后被 R5 的 narrate 节点沿用。
- **前置**：R2。**首日 = 旧作品 provenance 完整率抽查**（prepared_storyboard/spec captions/语音配置字段存在性——决定按需收割的可行面，未运行项销号）。
- **模块与接口**：`tools/film/narration.py`（合成前查 store/占位/落定/适配重 derive）；新表迁移 + MODULE_ARCH §4 登记；`storyboard.py` `canonical_film_params`（aspect 出集）+ delta 分类 + 变体版本生成 + 取景几何钳位；run/context aspect 呈现参数消费（`orchestrator.py:432` 白名单现状座位）。
- **任务**：按总设计 §10.1 并发五律（原子占位/有界接管/owner 双条件/过期不得覆盖/staging 重 derive）与 §7.6 取景重查逐项实现。
- **验收**：闸 1、2（变体零导演）、3、13（变体计费腿）、16（正常并发一次 TTS/接管 owner 隔离/过期结果不覆盖/结算幂等/staging 重 derive——口径以总设计闸 16 为准）；闸 6/7/8 复用腿收口（含不可适配注入分支）；S11b 变体旅程 + 旧作品同构 fixture 变体旅程（不动原事故项目；付费面按 §0 授权边界）；仪式链按面。**编辑路径本轮闭环后统一启用本地**。
- **停止点/移交**：执行链仍单体。**拆分预案**：store+并发测试先行 / 变体后行。

## R5 — 宏执行阶段拆分、Tasks 与恢复（链黑暗落地）

- **目标**：`film_prepare`/`film_narrate`/`film_assemble` internal 节点 + 编译期展开 + 阶段持久化 + Tasks 宏行真实显示 + 恢复语义。**链 flag 默认关（本地/测试可开），代码默认路径仍为单体；单体逻辑平移，零行为新意**。总设计 §9 全节。
- **范围外**：capture 口径改动（R6——本轮若启用链将错收费，flag 必须保持关）；compose（R7）。
- **前置**：R4（复用 store/版本形状）。**首日 = 注册链兼容定点验证**（编译展开对图形状/出生地门/画布投影/render 认领链——阻塞证据再报告）。
- **模块与接口**：`pipeline/graph.py:239-242`（internal 先例）；`orchestrator.py:627-631`（materialize_source 注入先例）+ `execute_step`；`graph_fill.py`（画布投影/Tasks 行）；`render_ownership.py`；`run_review.py:45` 映射改读链尾；`tools/__init__.py` 注册面不动。
- **任务**：① 三内部节点（internal=True）+ 单体 run() 逻辑按 §9.2 表分家平移；② 编译期展开 + launch_film 注册形态保持；③ 阶段持久化（执行计划/音频引用/spec）+ 恢复重跑只重做失败及下游；④ Tasks 宏行（状态/耗时/成本/复用计数摘要）；⑤ 报价等价（链 estimate Σ ≡ 单体公式）。
- **验收**：闸 4、5、17（flag-on 测试环境）；单体路径全回归绿（生产形态不变）；仪式链按面。
- **停止点/移交**：链保持 flag 关移交 R6。**拆分预案**：逻辑平移+链跑通（持久化最小）/ 恢复与 Tasks 细化。

## R6 — 结算边界与失败注入矩阵（默认值切换）

- **目标**：内部阶段 `capture=False` + assemble 链合计 capture 单座；失败注入矩阵；链 flag 默认值切换（本地/测试启用；部署与线上配置不在本期）。总设计 §9.2 计费边界段 / §10.3。
- **范围外**：计费政策本身；estimate 公式（等价已在 R5 断言）。
- **前置**：R5。
- **模块与接口**：`orchestrator.py:1352` capture 座；`platform/billing.py:277+` capture_step（prior 减法幂等现状）。
- **任务**：① capture=False 接线（步骤成功处按声明跳过，assemble 捕获链合计——链累计不得重复汇总成本）；② 注入矩阵测试（prepare/narrate/assemble/render 四点 × 拆分前基线 worktree / 拆分后，stub TTS/render 零付费）：按用户口径比较**净扣费相等、hold 释放/退款相等、无重复收费**（步骤结构不同的钱包行形可以不同，不要求逐行相同）；③ flag 默认值切换；真实旅程冒烟属付费面，获授权前标「未运行（待授权）」。
- **验收**：闸 13 全量 + 闸 14（注入矩阵）；切换后 S11 形态绿（付费面，待授权）。
- **停止点/移交**：无。

## R7 — 自由编排恢复

- **目标**：`DraftStoryboard` v2（稳定 scene_id）+ `resolve_draft` 编译座；约束四层 validator（L1/L2 硬、L3 用户要求、L4 配方默认 agent 可覆盖并呈现 `constraints_choice.source`；REPEATED_VIEW/PADDING_SCENE 降 warning；EMPTY_CHAPTER 实质 = ui walk 或 plate；素材数重构）；导演全 shots 视觉（预算帽）；`film_director.j2`/SKILL.md 重写；骨架降配方工艺 + worker 兜底边界重申；导演 estimate 界更新。**compose flag 测试开、默认关（本地/测试）**。总设计 §7.3/§7.4/§7.6/§8.1。
- **范围外**：字段级修复机制（R8）——本轮修复仍是候选级有界打回（现状形状）；旁白帽的修复通道统一随 R8 收口（本轮=候选级违例）。
- **前置**：R2（scene_id/版本形状）。
- **模块与接口**：`storyboard.py`（schema/resolve/validate/orchestrate）；`page_media_inputs`（全 shots）；`prompts/film_director.j2` + `skills/launch-film/SKILL.md`；director mode flag（configs/env 一座）。
- **任务**：按 §7 契约逐项；prompt/pack 重写遵守 prompt 法（现在时现行法、无日期无 ADR 叙事）。
- **验收**：纯测试（schema/resolve/分层 validator/warning 分级/constraints_choice 记录）；prompt_gate 重跑；flag-on 的 S11 形态绿；闸 9、18 的 EMPTY_CHAPTER/质量提醒腿；一次通过率 n=3 冒烟读数（观察非闸）。
- **停止点/移交**：字段级修复 → R8；compose 默认值切换 → R8 末。**拆分预案**：schema+resolve+validator / prompt+pack+视觉。

## R8 — 字段级修复与全局重试预算（compose 默认值切换）

- **目标**：`FilmViolation` 结构化（scene_id/field/actual/bound 双载）；schema 字段层并入定点通道（pydantic loc 映射；仅 JSON 不可解析才有界整篇重生成 ≤1）；定点修复调用 + 系统合入 + 受影响约束重查 + 整体一致性；全局预算单座（1800s 墙钟 + **总 LLM 调用硬上限**，嵌套 schema 修复不刷新计数——口径以总设计 §8.2.7 为准）+ 无进展三判据 + 错误分类（系统错误不进导演）；compose flag 默认值切换（本地/测试）。总设计 §8.2/§8.3。
- **范围外**：edit 路径（R2 已结构化回 chat loop）。
- **前置**：R7。
- **模块与接口**：`storyboard.py` orchestrate_storyboard / FilmViolation；`agents/base.py:267-284` schema 修复座（LLMSchemaError 透出结构化 loc）。
- **任务**：按 §8.2 九项逐项。
- **验收**：闸 10（双层注入修复不漂移）、11（预算单座/无进展停止）、18 的旁白帽腿；翻牌后 S11 绿；修复墙钟观察读数（n=3 冒烟）。
- **停止点/移交**：无。

## R9 — 全链验收与收尾

- **目标**：完整仪式链 + 剧本矩阵全量 + A/B 人工视觉验收 + 观察指标读数 + 旧作品变体回归 + 文档收口。
- **任务**：① 仪式链全量（pytest/check_gates/prompt_gate/剧本矩阵/tsc/vitest）；② §14 二十闸终跑；③ A/B 人工视觉验收（linear.app / zymix.ai / 一新站；逐幕中点帧+相机到达帧接触表+全片动态看片；记录结论，人工属性如实标注）；④ 观察指标读数（一次通过率/修复轮次/墙钟/token——n=3 仅冒烟口径）；⑤ 文档收口：CHAT_ARCHITECTURE（film 旅程现行法）/ MODULE_ARCHITECTURE（表与内部节点登记核齐）/ DECISIONS（新 ADR + ADR-134 修订注齐）/ RENDERING（spec 面如有变化）/ PROGRESS 批次登记；⑥ 未验证项逐条销号或转挂账。
- **停止点**：收尾完成即停；G5 餐馆素材适配不在本期，另立批。

## 验收映射（总设计 §14 二十闸 → 轮次）

| 闸 | 内容 | 收口轮 |
|---|---|---|
| 1 | pending 清空 ≠ 失去作品 | R4（R2 部分） |
| 2 | 重呈现/变体零导演调用 | R2（edit）+ R4（variant） |
| 3 | 原片保留、变体独立 | R4 |
| 4 | Tasks 宏行与真实执行一致 | R5 |
| 5 | 阶段失败落真实阶段、恢复不重做 | R5（R6 复核） |
| 6 | 一幕换图缩短旁白其余不变 | R2（digest 腿）+ R4（复用腿） |
| 7 | 重排：场 digest 不变/整板变/音频复用限定 | R2（digest 腿）+ R4（音频腿） |
| 8 | 换音乐双形 | R2（帧/cue 腿）+ R4（音频窗腿） |
| 9 | 未指定时长 agent 自主结构 | R7 |
| 10 | 字段级修复双层覆盖 | R8 |
| 11 | 多层重试不重置预算、无进展停止 | R8 |
| 12 | 无专用路由组合修改 | R2 |
| 13 | 计费回归（变体实扣/台账平衡/旧作品同政策） | R4 + R6 |
| 14 | 结算边界注入矩阵（净扣费/释放/重复收费口径） | R6 |
| 15 | 授权回归 | R2（R9 复核） |
| 16 | 旁白并发（正常并发一次 TTS/接管隔离/结算幂等） | R4 |
| 17 | 注册链兼容 | R5（R9 复核） |
| 18 | 约束契约（EMPTY_CHAPTER 实质/旁白帽通道） | R7 + R8 |
| 19 | 不承诺未支持能力 | R2（R9 复核） |
| 20 | 仪式链 + S11/S11b + 旅程剧本座 | 逐轮按面 + R9 终跑 |
