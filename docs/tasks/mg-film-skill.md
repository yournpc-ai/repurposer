# MG film skill 批（刀 B，最高优先级插入批 · 4 天冲刺版）

> Status: 待开工（2026-10-13 拍板插入；工期压缩至 4 天 = D1 10-14 ~ D4 10-19，延期清单见文末）。架构母法 = ADR 随批短式落档 DECISIONS.md（film-spec 第二家族 + 引擎族注册表 + skill 接入装配线）；关联 = ADR-028（双链并列，禁第二条编排链）/ ADR-026（AI 标识分类器）/ ADR-016（clip-spec 零改动承诺）。
>
> 已验证基座 = spike：`apps/render/scratch-spike/`（capture→storyboard→render 全链，26s/780 帧/45.5s ≈1.75×实时）。本批 = spike 转正，不是再探索。
>
> 范围纪律：只做**刀 B（全幅生成，film-spec）**。刀 A（overlay 词汇扩展）归需求池，验收后按"一行扩展配方类型"逐个上架（锚点基建 ASR/speaker_map/beat_map 已在）。

## 拍板要点（讨论已收敛）

- 引擎 = 基座；skill = 族内变体（词汇表 + spec 预设 + prompt 段落 + validator）；配方卡 = 入口实例（brief 模板 + 输入需求 + demo），1:N。用户自建 skill = 参数+模板（非代码），归运营端排期，本批不做。
- node face 不变：`graph_nodes.type` 仍 `video`、`prototype` 仍 `generator`；区分活在 `spec.tool`（skill 名）与节点内部 spec 家族（film-spec vs clip-spec）。
- 同事仓库定位 = R&D 实验室；**引擎组件库永远人工写**（agent 不编译不执行 LLM 生成的渲染代码）。engine.html+seek 方案不引入，不养第二套渲染器。
- v1 只做 16:9（LinkedIn/机构站 = 定位主渠道）；竖屏变体后补。
- skill 接入装配线（后续新 skill 的规程）：四器官拆解（词汇表/spec 契约/编排 prompt/执行器）→ **四问分诊**（引擎族已存在？魔法在 prompt 还是引擎？词汇重合度？**输入、失败恢复与交付生命周期能否复用？**——同族 ≠ 输入/交付生命周期自动相同）→ 同族新卡 0.5~1d、新引擎族 4~5d；拆解过堂必查三横切面：**输入与来源契约 / 验证与失败契约 / 交付与生命周期契约**。
- 世界级架构对齐点（与同事 skill 包同形但全生产化）：SKILL.md 行业标准形态（Claude Code skills 同构）/ tools = 能力唯一家 / registry→prompt 单源投影 / grounding validator 确定性门 / 诚实降级 / 队列+计价+多租户安全（SSRF 守卫、代理纪律）。

## D1（10-14）：render 转正 + 网页采集资产化（纯移植日，W8 验收并行 ⚠️）

- 新建 `apps/render/src/film/`：组件库自 scratch-spike 转正（6 组件 + Fade + accentize）+ storyboard zod schema（**边界校验保持最小**——形状校验；语义接地是编排侧 validator 的座位，不双写）。
- `apps/render/src/server.ts`：`spec.family === 'film'` → film bundle/renderMedia；否则现行 clip 路径（**clip-spec 路径零改动**）。POST 信封（spec/out_subdir/basename/outputs）= 两家族共享最小信封，family payload 各自 zod；**family dispatch 覆盖 preview/retry/revision/recovery 全生命周期，不只首渲**。帧数/时长上限入配置。
- 新建 `app/tools/research/capture.py`：富采集（title/meta/h1-h3/按钮/链接结构化抽取 + headless Chrome 截图），**复用 `web.py` 既有 SSRF 守卫（`_host_blocked`）与代理纪律（`trust_env`）**；dev-server HMR 禁用 virtual-time-budget（spike 取证）。Chrome 调用收敛为一个 `CHROME_PATH` 解析 helper（spike/render/worker 不各写一遍）。**显式多 URL**：capture 接受 N 个 URL → 每页一个 web_page 资产（同一 processor 循环，零新机制）；SSRF 守卫升**浏览器级**——顶层导航 + 重定向 + 子资源统一策略（协议白名单 / 私网与保留地址 / DNS 解析后重验 / 请求数·字节·时间上限 / 隔离环境无凭证）。**D1 上午先跑真站 smoke**：headless Chrome 在 worker 环境的字体/代理/沙箱稳定性。
- 新建 `app/pipeline/web_capture.py` processor（采集编排 + meta/存储回写，`extraction.py`/`prosody.py` 同族）；`asset_processing.py:PROCESSORS` 注册 web_page 链；`assets.py` 新建 `create_web_page_asset_from_url()`（与 `create_transcript_asset_from_text` 同座）。
- `app/models/schemas.py`：`AssetType` 加 web_page + meta schema（research 清单 + 截图 key）；素材卡最小面（截图缩略 + 文案计数）。
- 采集范围 = 用户显式给出的 URL（可多个，每 URL 一资产）；**自动 discover（根页抽站内链接）本批不做**——无关页混入会稀释 grounding 清单，归需求池；无 agent 可调 read_web_page tool——URL 消息入口即资产化，临时问答由既有 research 节点兜底。

## D2（10-15）：编排 tool + grounding validator + prompt 面（唯一真未知日）

- **上午先通链**：fixture storyboard（手写）过 validator → render → 产物，全链绿灯后再接 LLM。
- 新建 `app/tools/film/`（`__init__.py` + `storyboard.py`）：编排 tool = LLM 写 storyboard → **grounding validator**（屏上字符串逐条命中 research 清单；相机焦点 [0,1]³ 越界拒；场景枚举闭合；**内容约束**：单屏字符上限 / 场景数上下限 / 每场景时长范围 / 重复文案拒 / 必需镜头属性齐全）→ spec 落节点（`spec.tool='launch_film'`, `spec.family='film'`）→ 经既有 render pipeline 入队（**禁第二条编排链**）。**打回有界**：重写 max 2 次（3 候选），耗尽 → failed 终态 + **结构化错误码**（UNSUPPORTED_SCENE / TEXT_NOT_GROUNDED / INVALID_FOCUS / DURATION_INVALID / CONSTRAINT_VIOLATION），同 spec 重试幂等，禁盲重试。
- **时长 = 确定性帧分配**：LLM 只给受限时长意图；整数帧由代码分配（固定 fps、场景 min/max 帧、总帧 = Σ 场景帧、片尾最短时长、总时长范围校验）；渲染完成后 probe 校验真实时长/分辨率/流。
- 新建 `app/skills/launch-film/SKILL.md`——pack 指令包（eager-validated 机制零改）：场景词汇语义 + grounding 纪律 + 二源律命名（storyboard `name` LLM 起，null 读容忍——打字机双牙）。**一部法一个座位：craft 约定只住 pack，`film_storyboard.j2` 只写输出 schema 与接地指令，禁复述**。
- 新建 `app/prompts/film_storyboard.j2`；`plan.j2` / catalog 行注册（registry↔prompt 一致性纯测试同步）；`agents/contexts.py` 挂 `packs=["launch-film"]`。
- **能力菜单注册（"你会做什么"复用面）**：film tool 在 `app/tools/__init__.py` 注册表带 `capability_menu_lines` 菜单行——一处注册三座自流（intent_router / chat_intent / trigger）。菜单行 = 用户语言动词组（"给一个链接，生成发布短片"），**禁在 `_capability_answer.j2` / `_identity_menu.j2` 手写 MG 条目**。
- `app/pipeline/orchestrator.py`（~777 媒体 422）：按 spec.family 分叉——film 族豁免 source-media，改验 web_page 资产在场**且 status=ready**（资产就绪门：pending = 等处理完成、failed = 诚实拒路）。
- `chat_intent_system.j2` / `intent_router.j2`：含 URL 消息指引一句（LLM 判定，**禁长度/正则启发式**）。

## D3（10-16）：计价 + 配方卡 + e2e（集成日，周五 checkpoint）

- 简式估价：`workflow_steps.estimate` = storyboard 秒数 × 费率 + 编排 tokens 平项（**逐次尝试计价**，失败不扣费）；**hold→capture→release 幂等键复用既有计费座——重跑 / 失败释放不双扣**；产物 `provenance=generated`，ADR-026 分类器骑既有通道零新码。
- 配方卡：`apps/web/src/components/recipes/` 注册 + `en.ts`/`zh.ts` + demo/ 前缀真片（本批管线实渲一条上传）。**v1 不加 tab 机制——MG 卡直接进现有配方行**。
- e2e 打通（贴链接 → 资产 → 方案 → auto 开工 → 三节点血缘 → 成片）+ prompt_gate 复跑（骑既有探针，注册即扰动：条目从简）。

## D4（10-19）：回归座 + 仪式链 + 验收

- `scripts/chat_scenarios.py`：S11 旅程座（URL → 卡 → 分镜方案 → 渲染 → 产物节点；只锁形态不锁文案）。
- **产物文件校验闸**：渲染成功态 = 文件存在 + 大小非零 + probe 可读（时长/分辨率/流合法）——复用既有渲染完成校验座，film 路径同门，未过校验不算成功。
- **并发冒烟**：2–3 并发渲染跑一遍（45.5s = 单机基线，非产能承诺）；worker 渲染并发上限 + 超时 + 临时文件清理入 worker 配置。
- **失败分类台账**：分阶段通过率统计（schema / grounding / 约束 / 渲染 / 文件校验），读数供归因，不归因一律"模型能力"。
- 纯 pytest 新增：grounding validator 纯套件 / capture 抽取纯套件 / registry↔prompt 枚举一致性同步；check_gates。
- 验收（live 用户自跑）。**UI 一日包同日施工，见 `tasks/flora-parity-ui.md`。**

## 验收口径（用户视角）

贴一个链接（或 @web_page 资产）说"做一条发布短片"→ agent 读网页、出分镜方案（文案全部可回溯到页面原文）→ auto 档直接开工 → 画布三节点血缘（web_page → generator → video）→ 成片可播可下载，估价贴与实扣一致。移动端交付走查 = 承接句 + 收据行 + 锚卡可点播（规格与谓词真值表见 `tasks/flora-parity-ui.md` 锚卡条目；桌面零锚卡零承接句为对照组）。

**能力问答面**：live 问"你会做什么 / what can you do"→ 回答里出现 MG 族作品（动词组、用户语言、零工具名），且与配方卡、计划路由同源——改注册表任何一行，三处回答同步变。

**四条放行闸**：资产 ready 才编排 / validator 打回有界（耗尽 = failed 终态 + 错误码）/ 产物文件 probe 校验过才算成功 / 计价·重跑·失败释放幂等。

## 禁止事项

1. **禁第二条编排链**：film 骑既有 run/graph/worker/计价，ADR-028 原样承重。
2. **禁 LLM 写/改渲染组件**：组件库人工拥有；LLM 只产 storyboard JSON。
3. **禁工具名上屏**：活动行走工序词表；icon ≠ 工具名。
4. **禁启发式 URL 判定**（长度/正则）；意图 = LLM 判定。
5. **无真 demo 不成卡**（卡点亮律）；一卡只承诺一个产物（禁打包文案）。
6. **禁一部法两座说**：craft 约定只住 pack；render 侧不二次接地校验。
7. 打字机双牙：storyboard 任何散文/命名字段 = null 读容忍 + 信封到达后 paceSettledProse 节拍释放。
8. spec.family 路由只读 spec 自身字段，**禁读节点类型/名称推断**。
9. **禁盲重试**：validator 打回有界（max 2），耗尽落 failed 终态 + 结构化错误码；同 spec 重试幂等。
10. **禁无文件校验的成功态**：产物文件未过 probe 校验（时长/分辨率/流）不算成功。
11. **SSRF 边界 = 浏览器级**：导航/重定向/子资源同一策略，禁只守顶层 URL。

## 延期清单（本批明确不做，归需求池/后续批）

自动 discover（根页抽站内链接——显式多 URL 已够，自动抽取归需求池）/ 竖屏变体（16:9 先行）/ 帧级精细估价（秒级简式已够）/ prompt_gate film 独立探针族（本批骑既有探针 + 复跑）/ ADR 全文（短式落档）/ queue chip 等 UI 件（见 UI 简报延期节）/ 刀 A overlay 词汇扩展 / 用户自建 skill。

## 风险

- **双未知改标**：① D1 = headless Chrome 在 worker 的稳定性（字体/代理/沙箱/长跑）——缓解 = D1 上午真站 smoke，炸了就地用 spike 环境差异二分；② D2 = LLM 编排一次通过率——缓解 = D2 上午 fixture 通链、LLM 下午并行调；grounding validator 打回率 >30% 时先收 vocabulary 提示再调 prompt。
- D1 与 W8 验收并行：移植件体力密度高，冲突时 D1 内容溢入 D2 上午。
- 时长漂移与 validator 死循环已由确定性帧分配 + 有界打回覆盖（D2）；渲染并发由 D4 冒烟 + worker 上限覆盖；剩馀产能外推（45.5s 单机基线）永不当承诺。

## 验证仪式链

纯 pytest（新增三套见 D4）→ check_gates → prompt_gate（D3 复跑）→ chat_scenarios（S11 新座 + 全量回归）。live 验收用户自跑。
