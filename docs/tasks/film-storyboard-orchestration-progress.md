# Film 编排与持续修改——当前进度

> Status: 人工试用与定点收尾（2026-10-25）。本文件是 Film/MG **实现与验证状态**的当前快照；状态覆盖更新，不追加会话或批次记录。技术契约读 [总设计](film-storyboard-orchestration.md)，剩余工作、验收与上线条件读 [execution](film-storyboard-orchestration-execution.md)，全局优先级读 [PROGRESS §0](../PROGRESS.md)。
>
> 状态口径：**已落码 ≠ 纯测试通过 ≠ 真实旅程通过 ≠ 人工视听通过 ≠ 可上线**。未运行的检查必须写“未运行”。

## 0. 当前阶段与下一入口

- **当前目标**：由用户进行真实 Chat / 制作人工试用，按反馈做定点修复；不为追求分支一次全绿而扩大架构，也不把本地可试用写成已上线。
- **当前形态**：网页源与文字源共用版本、编辑、音频、单体 `LaunchFilm.run`、render/probe 与计费链；`film_prepare` / `film_narrate` / `film_assemble` 均为 PLANNED。当前有 8 种 scene 类型；REPEATED_VIEW / PADDING_SCENE 仍是硬违例。
- **本地与生产**：生产编辑门默认关闭；`FILM_EDITS_ENABLED`、warmup、进程加载版本和 env 必须在下次开工时重新核对，本地启用不等于生产上线。
- **下一入口**：按 [execution §1.1 A–D](film-storyboard-orchestration-execution.md) 组织授权/版本、严格动画、Chat/Run 工作段与恢复、网页/MG/采集验收。agent 不擅自发起付费验证；获得单独授权后先设 `MINIMAX_WARMUP_ENABLED=false`，所有真实模型 HTTP（含 warmup）计入预算。

## 1. 能力 × 当前证据

| 能力 | 当前实现与边界 | 验证状态 / 未验证项 |
|---|---|---|
| 网页源 film | 贴 URL → 采集/讨论 → 分镜 → 授权 → 单体制作 → 修订；首稿不直接承诺精确时序/样式；web 导演尚无 composite，patch 无元素新增 op | 有代码层与既有真实读取证据；后续改动后的端到端与 S11 未重跑 |
| 文字源 film | 用户原文或创作需求；逐字 / 改编；words + composite；子句 manifest、`CopyRef.span`、`group_chars` | 一次真实文字源设计尝试在 25,077 ms 后由 draft active→failed：无 assistant 内容、`terminal=None`、`run_id=None`，失败消息为“没能为那个页面写出忠实的短片文案——换一页文案更清楚的，或告诉我先突出什么。”（原始证据：`apps/api/scratch/t2a-acceptance/transcript.md`）。**当前代码重跑仍开放**；旧失败不是已确认的现行缺陷，也不是成功旅程 |
| composite 组合幕 | 通用 video/image/text 元素；源区间、输出窗、rect/fit/z、独立文字时序、keep_audio；节拍对齐跳过组合幕两侧切点，时长校验失败使用时间设置提示 | 仅文字源出生；≤6 元素/幕、文字 ≤4 行；无变速/循环/补帧/重播。分镜/输出规格定向纯测试与 check_gates 通过；真实失败分镜离线构建通过（13 幕、1425 帧）；edit wiring/text source 扩展检查有 7 项失败，修改前隔离基线同样失败；未重跑真实制作或人工视听 |
| 精确动画与文字样式 | enter/exit/motion 时间参数；words/lines 双单位；rise/fade/slide；严格逐行纯滑动由 `interval>=duration` 表达；align/size/accent_style；背景恒透明度；Fade 罩按元素退让 | **slide 的真实动态像素与逐行帧级验收未做**；容量检查是估算，不是字体排版测量；真实模型稳定生成合法参数未验 |
| 结构化编辑 op | `update_scene`、`update_element`、`reorder_scenes`、`remove_scene`、`set_music`、`set_voiceover`、`set_subtitles`；原子批次与 change_set；patch 顶层互斥、最小合法示例与 copy 字符/行数/文字片显示单位限制在真实 wire schema 可见，数字由校验常量现场投影；完整句子可按语义分行，保留原文不得为过校验截断或删改 | `set_aspect` 不存在；`update_element` 不能换素材；多处修改须一次原子批次；定向 schema/真实校验测试与单次隔离真实模型首次合法调用已通过，但完整 Chat 旅程、多次模型样本与过期 base_ref 真实旅程未跑 |
| 同回合纠正、失败停止与条件保护 | 同回合有界纠正不是产品总修订轮数上限；同签名第 2 次设计拒绝即停、同回合累计第 3 次设计拒绝必停；失败台账只由完全等价 patch 成功销账；unmet_condition / copy_drift 押住 auto 开工 | 每回合失败预算不是 R8-M 统一嵌套 LLM 上限；真实模型侧停止、活动终态和 dock 呈现未验；签名/相等不证明用户目标完成 |
| 当前稿 / 旧 Output 读取 | `get_output_spec` 双形；run provenance 恢复基准；原版 Output 保留 | 画幅变体仍是 PLANNED；长设计回合中流失败的分镜可见性缺口仍挂单（`on_row_append` 无调用点） |
| 素材发现 | `list_project_media` 分页、ids 选读、@钉选提首；真实时长探测 | 40 行打印帽需分页/选读；不能把截断当不存在；复杂浏览器操作不在当前能力内 |
| 修订完整呈现与制作确认 | patch 返回系统变化摘要 + 共享呈现座的完整当前保存版；普通修订 `answer`，review-only 不问开工，明确“改完直接做”才进提案 | **真实 LLM/制作旅程未跑**；全量 pytest、check_gates、prompt_gate、剧本矩阵未跑；人工矩阵归 execution §1.1 A |
| Chat Film 版本执行与形状三态 | `edit_graph` 的 Film edit_prompt/generic run 在提交前拒绝，通用 dispatcher 后挡；EditGraph 制作意图接入内部 proposal；开放重稿的 target_seconds/scene_count/group_chars 省略继承、null 清除、给值覆盖 | 尚需隔离项目验证“确认版 = 实际 run 版”、旧 pending 正常消费，以及清除分组后的模型与成片事实；不复放事故项目 |
| 多轮授权与 Start | production_intent 出生事实；累计方案呈现；作品首稿未持久化呈现时所有 Start 失败闭；auto 不另加首稿 approval dock，ask、费用与条件原因仍走通用确认戳；Start pill 复用 sendChat，下一轮 LLM 才调 `start_run`；review hold、shortfall、drift、费用与 Start 版本绑定分别校验 | auto 无首稿 dock、ask Start 发普通消息与下一轮开工已落码，提示词、回复和 Start gate 未改；更新后的 pytest / tsc 未运行，首条“直接做”、auto/ask、后续版本、Start 后制作与其他守卫的真实旅程仍待验收 |
| 音频三面与旁白复用 | 默认无配音；voiceover/music/keep_audio 独立；显式 off 不被默认重开；项目级旁白 store | 实际成片音轨未独立试听；voice 设计期钉版、STOCK_VOICES、试听未实现；本地音频速度派生未实现 |
| Chat 活动、轮询恢复与 WorkSegment | chat live Thinking/里程碑不可展开，首字实际释放或真实终态原位收 Worked；RunTaskList 与 chat 共用 `WorkSegmentRow`；run 按 RUNNING → REVIEWING → SETTLED 原地过渡，匹配 delivery 首显才收段；chat inline chip 复用同一 settled 边沿，REVIEWING 不提前挂载；轮询恢复按 `seq` 决定准入与落位，run review 不补 activity 且只接当前 run 的 delivery/failure，挂载回放按行 id 去重 | 既有 `runWorkSegment` 与恢复/时间线定向纯测试通过；本轮 chip 与 Start 改动后的 web tsc / 纯测试未重跑，live SSE、迟到 delivery、断网/停止恢复与历史回放的人工逐拍视觉仍开放 |
| 交付回合与 Chat 产物卡准入 | `run_completed` 使用独立零读 `delivery_agent`；代码先裁决 failed/partial/delivered，模型只写对应分支；film/clip 须 render completed 且视频文件存在才进入 delivered 事实与产物卡；仅已交付 film 做一致性对账 | **真实 LLM 的全未交付/部分/成功回复与浏览器空卡消失未验**；prompt_gate、剧本矩阵、全量 pytest 未跑；真实重试渲染/上传未执行 |
| 回答入口与 begin 拒绝 | 回答/brief 先耐久提交；结构化 begin refusal；重复 begin 以 TerminalRefusal 终止而非误报能力缺失 | 原“逐字全片”入口真实旅程未复测；已答 dock 浏览器持久化未验；同步测试未运行 |
| 执行与计费 | 单体 LaunchFilm + 真实单步 Tasks；render/probe；Output/work_id；hold→capture→release | R5/R6 宏阶段未实现；R8-M 统一 10 次调用上限未实现且是上线缺口；并发发布与完整上线条件未收口 |

独立字幕：Film 场景持久化 `SubtitleTrack` / `SubtitleCue`，`set_subtitles` 支持创建、整体替换与删除，读面返回完整轨道。旁白与字幕独立，旧 `captions` 字段不兼容；clip 家族不在此次命名变更范围。后端定向测试、渲染 schema 测试、typecheck 与 check_gates 已运行；本地无音频双语字幕样片已渲染并检查关键帧。两个既有 Start stamping 测试仍被首稿 review_hold 门禁拦截；真实模型编辑、确认和交付旅程仍待验证。

## 2. 当前未验证项

验收步骤与证据包统一定在 [execution §1.1](film-storyboard-orchestration-execution.md)；本节只保留状态，不另写第二份操作矩阵。

### 2.1 真实 Chat、授权与恢复

1. auto/ask 两档：正常制作意图、无制作意图、unmet_condition、copy_drift；首条“直接做”也只能先完整呈现首稿。auto 无其他确认债时不显示首稿 approval dock，用户看后以“就按这版做”等普通消息放行；ask 可显示 dock，Start 只发送同类消息，下一轮 LLM 才创建 run。
2. 过期 `base_ref` 的 digest 拒绝、SSE 断流后的世界状态与恢复。
3. 普通修订只落版不制作；随后明确重制；同回合“改完直接做”；review-only；drift/shortfall/review hold/费用与 Start 版本绑定不被削弱。
4. 在当前代码重跑纯文字零媒体真实 LLM 设计、制作与交付；先归因上述已失败尝试是否仍复现，再验证更快节奏、逐字保真与真实成片。
5. 更快节奏、子句/group_chars、同回合纠正、8 幕目标、前 7 幕不变、末幕两行严格纯滑动、显式清除旧分组、连续不同非法参数第 3 次拒绝、实际 run 严格执行刚呈现版本。
6. “逐字全片”原入口、回答/brief 回填耐久、首次 begin 拒绝终止重试、已答 dock 刷新呈现。
7. live SSE / WorkSegment / run-delivery / 修订 answer 流逐拍观察；覆盖部分失败、全败、60s 无回复、迟到回复与历史回放。
8. 真实断网、用户停止与 Start 普通消息的恢复：已落库回复接回、窗口内无回复显示 `connectionLost`、刷新归档补齐，以及 answer 流静默死管收口；单测与本地模拟不能替代。

### 2.2 回归闸与基线归因

9. 最新全量 pytest 未运行；check_gates 在此前工作区通过，本轮 Home / Start / chip 改动后未重跑。Film/Chat 定向纯套件中两个 Start stamping 用例均被 `start.review_hold` 拦截，需在首稿审阅合同下单独归因；它们不是本次编辑约束测试的失败，旧全量结果也不能当作当前结果。
10. 多批 prompt/工具声明变化后的 prompt_gate 未终跑；需授权与配额，入口显式关闭 warmup。
11. 剧本矩阵全量与 S11 网页链在本迭代后未重跑；真实付费面另行授权。画幅变体若实施还需 S11b。
12. 当前工作区含多批未提交成果和并行修改；定向证据不等于 clean HEAD 全量基线。不得为放行放宽校验或断言。
13. 最近一次全量 web 纯测试为 251 项中 250 通过，唯一失败是 `recipeFamilies` 的 Ads 族供货断言仍期望仅 `saas`；本轮 Home 已按 `text-short` / `product-demo` 两个子 tab 更新注册表与断言，但尚未重跑，不得记为已转绿或全绿。

### 2.3 视听与界面事实

14. 白闪、橙色强调、纯淡入、Fade 罩所有权、推拉/居中/字号档，以及 slide 的无渐变/无模糊入场与逐行顺序时序，需在真实动态成片中检查。
15. 实际音轨独立试听：配置、probe 或“静音探针通过”不等于听过成片；旁白/音乐/原声分别核对。
16. Tasks 命名：组合片进行中“生成文字短片”的准确性需真实界面观察；终态中性名称已有回放证据。

### 2.4 早期尾项与长片边界

17. **139s 案例**：超过当前 120s 帧帽；需决定调整后端/render/超时/费用全链并验收，或明确不承诺，不得静默截断。
18. **zymix 75–95s 分镜丰富度 demo 锚**：最后记录仍为“在跑”，没有完成证据；需重新取证，不继承旧进程状态。
19. **早期 Film/MG 验收**：MG live、E1/E2/E3 与分镜旅程的仪式链/剧本尾项统一在 execution §1.1 与当前回归窗口核销，不恢复旧冲刺清单。
20. **fc13 真实对话与成片**：CopyRef.span/group_chars 的纯函数冒烟不等于真实用户旅程通过。
21. **UI D4 / flora parity 末验**：锚卡、活动行与 chat 自足的旧验收记录未全部销号；剩余合同见 [UI 任务](flora-parity-ui.md)。

## 3. 当前风险、阻塞与上线边界

1. **并发发布是硬阻塞**：patch 的读取→提交窗口尚未用真实竞态证明不会覆盖版本；未关闭前只能在经验证的隔离演示环境运行，不得宣称多用户正式上线。
2. **R8-M 未收口**：当前是 1800s 墙钟 + 候选界 + chat loop 上限 + Film 设计每回合拒绝预算；统一 10 次 LLM 调用硬上限未实现，这是独立上线条件。R8-F 可条件延期，但不能吞掉 R8-M。
3. **上线清单未闭环**：双链计费/授权、alembic（含 film_narrations）、env/flag 默认值、vendored 字体、默认音乐在对象存储与渲染镜像两侧、可执行回退、上线后双链冒烟均需逐项核对。生产配置和部署另行授权。
4. **证据基线不是干净 HEAD**：下一位先查 `git status` 与真实代码，禁止用 reset/checkout/stash 制造基线；旧“全绿”不能转信。
5. **中流可见性缺口**：`on_row_append` 分镜发布座仍无调用点；长设计回合中流失败时的可见性不得宣称已修复。
6. **付费预算纪律**：真实 LLM/TTS/采集/付费渲染先列范围与预算并获授权；所有真实模型 HTTP 包括 warmup。
7. **服务状态需重新取证**：真实手测前必须核对 API/worker/render 的实际加载状态；不能只凭源码和 tsc 推断正在运行的版本。

## 4. 已拍板但未实现 / 条件触发项

这些需求没有因最小闭环或文档清理而取消，也不因列出就自动授权施工。完整范围与验收唯一归 [execution §2～§4](film-storyboard-orchestration-execution.md)：

- 画幅变体 `set_aspect` 与 S11b/旧作品正腿回归；
- Home 真实样片替换（当前只展示 Text Shorts / Product Demos；Product Demos 三张布局占位仍待对应真片；见 [Home 状态](home-creation-entry-refresh.md)）；
- `typeface` 字体枚举；voice 设计期钉版、真实 voice_id 读取、STOCK_VOICES 与可播放试听；
- 网页动态录屏采集；R5/R6 宏阶段、恢复与链式结算；
- R8-M 统一预算（上线必需）与 R8-F 完整字段级修复（条件触发）；
- R7 residual、本地音频速度派生，以及需明确用户案例后再议的复杂浏览器操作与知识视频专项。
