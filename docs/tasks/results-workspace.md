# results-workspace 实施简报——结果工作面：终态承接、网格⇄舞台、配方检视 overlay

> Status: 📋 立项（2026-08-06，未施工）。施工窗口（**闭环链**，2026-08-06 二次拍板重排）：**第 2 周**（配方检视 overlay + composer 回填）→ **第 3 周**（结果网格重构 + chips + 终态不跳转网格版）→ **第 4 周**（工作面：chat 列 / 舞台 / 检视器 / 双 modal 退役）→ **第 5 周**（三档重跑接线 + 活图 spike，09-03 go/no-go 裁决）。dub 为全程载体卡。
> **2026-08-07 Flow 基座修订（ADR-036，用户拍板）**：只读图渲染扶正为共享基座 **FlowView**——原话"这一期先只暴露只读图，但该连线的连线、该有的节点是节点；只能通过 chat 修改，不变"。D6 overlay 规格修订（扇出主视觉 + FlowStrip 取代手风琴）；屏 3 "进度网格"升级为 **run 进度图**（编译期定死的死图 + SSE 状态动画，升正排产，不再是 spike）；第 5 周 spike 收窄为**全史血缘板**；禁令 #10–#14 追加。
> **2026-08-08 D6 二次修订（用户拍板，ElevenCreative 配方 modal 证据）**：overlay = **检视 tabs + 发射区**——左区固定为发射区（上传暂存为主角 + 产出预设 chips 可见 + 收起态可编辑预填 prompt + 发送按钮），右区 tabs（示例 = 扇出+预览 / 流程 = FlowStrip 画布），单屏不滚动，手风琴退役。**发射区 = composer 发送机构的挂载**（同一发射台的第二个停放位：同一 useProjectLaunch 路径——建项目 → 上传 → 跳项目 → 首条 `/chat`），不是平行表单；overlay 零推断 / 零 prior / 零生成，生成永远在 chat 之后。**两跳删除**（Remix → 回 composer 折返退役，屏 1.5 退役）。**入口分工定案：composer = 通用 / 多种 / 复杂 / 自定义提示词的组合式需求；配方卡 = 预设快捷需求。**修改通道定案：预设可见 = chips，修改唯一入口 = 预填文本 / chat（chat 恒胜），overlay 永不含参数控件（禁令 #15）。A 形态否决精确化：否决的是"modal 自建输入槽 + 生成按钮直接跑 run"（绕开 chat 主线），不是发射机构的位置。
> 依据：STRATEGY §5（闭环优先 / 顾问姿态）；CHAT_ARCH §3.3 / §8；ADR-028 / ADR-032 / ADR-033 / **ADR-035**（DAG 用户化三切）；**RECIPES §7.1（配方=数据 schema——overlay 即其渲染器）**；PROGRESS 第 2–5 周闭环链；竞品证据 2026-08-06 评审（DECISION_MATRIX §F——Lovart 类单产物工作面 ×2、flow 类画布+流程智能体 ×2、ElevenCreative 配方 modal、图片编辑 modal、gallery 检视 overlay，共七组截图）。
> 用户裁决（2026-08-06，五条）：
> ① **精修的对象模型是图，界面是语言**——隐藏画布，意图识别把用户语言翻译成图操作；图的用户化只剩"懂"（说明书/溯源），永不为"改"现身。
> ② **终态不跳转**——run 收官不打 toast 关窗，就地落成结果面。
> ③ **配方 = 检视 overlay + composer 回填**（B 形态），否决自带生成按钮的表单 modal（A 形态）：composer 保唯一发射台，overlay 只读。**同日补：配方 = 数据包**（base+flow+prompt+example_assets+example_outputs，RECIPES §7.1），overlay = 该数据包的渲染器。**2026-08-08 修订（D6 二次，见文首）**：overlay = 检视 tabs + 发射区（composer 发送机构挂载，同一发射台第二停放位）；否决精确化为"禁 modal 直接跑 run"。
> ④ **DAG 三切**：静态配方流程图 = 采纳；可操作画布 = 永久拒绝；运行期活图 = spike + 小白复述测试，第 5 周 09-03 裁决。
> ⑤ **排期 = 闭环链**：本简报全部内容 + Recipe schema + dub 数据实例，08-07 起连续四周攻坚（PROGRESS 第 2–5 周）；分镜/生成产物线后移为"扩展配方类型"行。

## 0. Context

用户到来即彷徨的第三步此前没有东西接：overlay 终态 toast + 关窗把用户扔到结果页网格；看（ClipDetailModal）与改（ChatModal）双 modal 接力；分数理由藏 tooltip；动作全收 "···" 菜单；完成后无下一步引导。竞品评审结论：行业收敛到"chat 前门 + 结构可见 + 单一连续面"，但画布上的操作镀铬（接线/节点模型货架/节点运行按钮）服务操作员画像，与"到来即彷徨"的知识专家画像冲突。**我们到达同一山顶的路径是：chat 为脊柱，产物为中心，图为说明书。**

关键架构事实（本简报的底座）：mention 注册表（asset/output/transcript_segment/workflow_step/recipe）= 节点寻址方案；RunPlan = 图内核；registry = 操作词汇表；outputs 经 `workflow_step_id` 挂图。**工作面不是移植别人的形态，是把已有架构渲染出来。**

## 1. 设计决策

| # | 决策 | 要点 |
|---|---|---|
| D1 | **终态不跳转** | run 终态：打勾流收官为 RunCard 聚合行 + 产物缩略条；中央区从进度网格翻成结果网格；无 toast、无自动关窗（第 3 周先落**网格版**——run 收官就地落结果页网格；第 4 周随工作面达完全体） |
| D2 | **中央区状态机** | **run 进度图**（2026-08-07 修订，ADR-036：run 拓扑编译期定死 = 死图 + SSE 状态动画，取代原"进度网格"）→ 结果网格（类型分段）⇄ 舞台（焦点单产物 + 检视器）。否决"顶部产物栏"：单类型形态假设，装不下 N 类 × M 条 |
| D3 | **流=档案 / 网格=当前 / 舞台=焦点** | 消息流 = 各轮记录卡（RunCard 终态产物条，历史可点击 → 拉回舞台检视）；网格 = `outputs` 当前态物化视图（无 run 分组逻辑）；舞台焦点规则 = 刚被碰的产物自动上焦点 / 点任意记录卡切换 |
| D4 | **chips 双级派生** | 网格模式 = 批次级（"全部加法语版"）；舞台模式 = 产物级（"翻译成法语 / 去口头禅 / 再来一版"）。零 LLM，按焦点产物类型 + 状态 + 配方确定性派生；顾问姿态"永给唯一下一步"的呈现层 |
| D5 | **配方身份贯穿三站** | dock 抬头（配方名 + 所需素材）/ 打勾流皮肤（步骤名 = 配方工艺名）/ 下一步 chips（配方感知）。**禁产物徽章**（2026-08-06 拍板）。实现：`RECIPE_REGISTRY` 注册项加 display 字段，run.context 带 recipe_id |
| D6 | **配方检视 overlay = 检视 tabs + 发射区**（2026-08-08 二次修订） | 点卡面 → 全屏 overlay。**左区 = 发射区**（固定）：title / promise / tags + 素材需求提示 + 上传暂存区（主角——素材是配方唯一的空格）+ **产出预设 chips 可见** + 收起态可编辑预填 prompt（recipe chip + promptTemplate）+ 发送按钮。**右区 = 检视 tabs**（单屏不滚动，**图只画一次**——ElevenCreative 证据：示例平铺输入/输出，流程才是图）：示例 = 输出/输入平铺卡（自动静音循环 + 单张发声开关，零边零图）；流程 = **唯一图画布**——素材 → 策展步骤（`fanout` 展开）→ 烘焙成片终节点的一张图（素材→步骤 = 依赖边，终步→成片 = 血缘边）。手风琴整体退役（原素材在输入区，prompt 住进发射区）。**发射区 = composer 发送机构的挂载**（同一 useProjectLaunch 路径，同一发射台的第二个停放位）——overlay 零推断 / 零 prior / 零生成，生成永远在 chat 之后；A 形态否决精确化为"禁 modal 直接跑 run"，发射机构的位置不再受限。**修改通道**：预设参数（如 dub 目标语言）永不做选择器控件——可见 = chips，修改 = 预填文本改字 / chat 修订（chat 恒胜，merge_prior_slots）。**入口分工**：composer = 通用组合式需求，配方卡 = 预设快捷需求 |
| D7 | **FlowView 基座**（2026-08-07 升格，ADR-036 及补记） | 共享只读图基座（`components/flow/`）：节点皮（asset / output / step）× 双边语义（lineage 血缘边 ⊥ dependency 依赖边）× 确定性分层布局（append-only 保序，"chat 加节点，图只长不晃"）；四个消费面（配方扇出 / run 进度图 / 舞台家族视图 / spike 血缘板）各做"领域数据 → nodes/edges"适配器，禁自绘边、禁自写布局（`packages/clip` 同款单一画笔纪律）。**引擎 = `@xyflow/react`**（摆位 + 视口；布局自算，不引 dagre）。**只读结构性执行**：`nodesDraggable`/`nodesConnectable` 常锁（拓扑编辑手势物理缺席，ADR-035 第 2 条）；**缩放 = 导航按面门禁**——有界面 fit-first 锁缩放，血缘板全开。**过渡动画三层**（用户拍板）：诞生编排（按 `seq` 编译序逐节点入场 + 边描画，真实编译序的缓动回放）/ 状态动画（running 脉冲、边流动，SSE 驱动）/ 生长动画（chat 加节点即诞生+描画）；动画 = 真实事件投影，禁假进度，`prefers-reduced-motion` 降级即时呈现。flow ↔ outputs 同文件登记防漂移不变（RECIPES §7.1） |
| D8 | **精修闭环** | 指出（舞台：transcript 行点选/文字框选 → 确定性指认，`transcript_segment` mention 已有座位）→ 表态（chat 说感受 / chips / 检视器参数直操——字幕样式/画幅/音乐/语言控件即改即预览）→ 执行（**系统选执行深度**：edit op / 单节点 / 子图重跑，用户只听一句代价"会重做文案和渲染，约 2 分钟"）→ 验证（舞台原位更新 + Before/After + undo） |
| D9 | **翻译两层** | 指认归确定性（mention / 舞台点选 / 焦点注入——不让 LLM 猜"第二条"是哪条）；意图归 LLM。翻译失败 = ask 反问（已有座位）；**图永不当错误信息或兜底界面**。新可翻译操作 = registry 注册项，永不开新面 |
| D10 | **双 modal 退役（第 4 周）** | ClipDetailModal → 检视器；ChatModal → 对话列（全高左列，消息机器一寸不动）。**asset scope 会话退役**：工作面统一 project 会话 + 焦点产物上下文注入（§6 context 组装加一行"当前焦点 output"）；asset scope 的独有价值（auto target 注入 / revise 兜底）被焦点注入替代——判例随第 4 周落地执行，届时同步剧本 harness |
| D11 | **网格组件双挂载** | 结果页裸访 + 工作面中央区共用同一网格组件（props 驱动，第 3 周写时即 workspace-ready） |
| D12 | **Before/After 对照** | 舞台级开关（按住看 Before），operations 快照 + `restore_version` 驱动，视觉类产物通用（竞品图片编辑 modal 的唯一采纳件） |

## 2. 六屏形态（终态，第 4 周完全体；第 2 周先落屏 1/1.5，第 3 周落屏 4 的页面版）

**屏 1 · 配方检视 overlay**（点配方卡，**2026-08-08 修订 = 检视 tabs + 发射区**）：左区固定发射区——title/promise/tags + 素材需求提示 + 上传暂存区 + 产出预设 chips + 收起态可编辑预填 prompt + 发送按钮；右区 tabs——**示例**（输出/输入平铺卡：自动静音循环 + 单张发声开关）/ **流程**（唯一图画布：素材 → 策展步骤 → 烘焙成片的一张图）。单屏不滚动。

**~~屏 1.5 · composer 回填态~~（2026-08-08 退役）**：两跳删除——发射区在 overlay 内直接发送，走与 composer 完全相同的路径（建项目 → 上传 → 跳转 → overlay chat 首发）。"配成德语"想改直接改预填文本的字，通道不变。

**屏 2 · 计划确认**：左列对话（用户气泡 → 计划摘要），dock 任务书钉输入框上方（配方抬头 + 槽位 + Start/Cancel + Auto/Review）；中央区安静态（素材概览）。参数齐 → reasons 空 → 自动 Start（S2 现成行为），无双重确认。

**屏 3 · run 进行中**：中央区 = **run 进度图**（2026-08-07 修订，取代"进度网格"）——FlowView 渲染当前 run 拓扑（编译期定死的死图），SSE 状态动画逐节点亮起（dub×3 扇出同屏可见；渲染扇出是真实事件，**不做假倒计时**）；左列打勾流照常（线性旁白，与图同源 workflow_steps，配方皮肤步骤名）。

**屏 4 · 终态**：一次平静交叉淡入——网格全部落位，top pick 抬升标记，分数直接印卡面；RunCard 收官（聚合行 + 产物缩略条）；批次级 chips 亮起。**无 toast，无关窗，无跳转。**

**屏 5 · 舞台（点任意卡）**：中央区切舞台——大播放器/大字版/画廊 + 同类型兄妹 ‹›（>1 时出现）；右栏检视器淡入：分数+理由常驻 / tabs（caption·topic·transcript，transcript 行可点→指认）/ 参数直操控件 / Publish 主按钮 + Download·Share。chips 切产物级。

**屏 6 · 修改循环**：说一句"开头两秒剪掉" → 左列 OpsCard（可撤销）；舞台原位重渲染（说完眼前就变）；↶↷ 头部常驻。大改（"该选 Q&A 那段"）→ 系统算执行深度、一句话报代价，确认才跑——用户永远看不到节点。

**移动端**：单列堆叠——网格 → 点卡 → 舞台 → "详情"展开块，对话沉底。网格即移动端答案，无额外形态。

## 3. 分期与改动点（闭环链，PROGRESS 第 2–5 周）

### 第 2 周（08-10 ~ 08-14）：dub 数据实例 + 检视 overlay + 串连入口

| 交付 | 文件 |
|---|---|
| Recipe 数据 schema 落码（五字段 + 可见性分层）+ dub 首件实例（示例 prompt / 素材账单 / 静态流程图定义 / 预览烘焙，flow ↔ outputs 同文件登记） | `app/pipeline/recipes.py`（RecipeEntry 扩展）；`GET /api/v1/recipes` 公开投影扩展；烘焙脚本 |
| **FlowView 基座 v1**（ADR-036）：FlowNode/FlowEdge 契约 + 确定性分层布局 + SVG 边层 + 节点卡双皮（asset/output） | 新增 `components/flow/`（FlowView / FlowNodeCard / FlowEdgeLayer + 布局） |
| 配方检视 overlay v3（**2026-08-08 修订，D6 二次**）：✅ 扇出主视觉 + FlowStrip（08-07 完成）；当日起 **左发射区 + 右检视 tabs**——`useProjectLaunch` 共享 hook 抽取（composer 发送机构：建项目 → 上传 → 跳项目 → 首发交接，composer 与 overlay 共用同一发射台）、发射区（上传暂存 + 素材需求提示 + 产出预设 chips + 收起态可编辑预填 prompt + 发送按钮）、右区 tabs（示例 = 输出/输入平铺卡 / 流程 = 唯一图画布：素材→步骤→成片一张图）、手风琴退役、单屏不滚动 | 新增 `lib/useProjectLaunch.ts`；`components/recipes/RecipeInspectOverlay` 重构；`HomeComposer`（改接共享 hook） |
| i18n / Tour 锚点更新 | `en.ts` / `zh.ts` / tour 配置 |

### 第 3 周（08-17 ~ 08-21）：结果网格 + 终态不跳转 + dub 完全通路 v1

| 交付 | 文件 |
|---|---|
| **run 进度图**（2026-08-07 排产，ADR-036）：`StepResponse.inputs` 下发 + `RunFlowGraph` 适配器（steps → nodes/edges，`chat.stepKinds.*` 友好名 + 状态动画）+ GenerationOverlay 进度态挂载（打勾流保留为线性旁白）+ `run.context.recipe_id` 穿线 | `pipeline/outputs.py`、`lib/types.ts`、`components/flow/RunFlowGraph.tsx`、`GenerationOverlay`、`chat/service.py` |
| 结果网格重构：类型分段、分数+理由卡面可见、动作抬出一级、失败/空态带下一步；组件 props 驱动（第 4 周双挂载准备） | `routes/_app.projects.$id.index.tsx`、`components/results/*` |
| 批次级 chips（确定性派生）+ 终态不跳转（网格版：run 收官就地落网格，toast+关窗退役） | `components/results/` chips 行；`GenerationOverlay` 终态分支 |
| 成功定义对照呈现（⚠️ 依赖轨 A schema，另一线第 4 周交付，未到则第 4 周合流） | 对照区块 |

### 第 4 周（08-24 ~ 08-28）：工作面

| 交付 | 文件 |
|---|---|
| chat 列提为页面区域（GenerationOverlay 拆壳：消息机器原样，外壳从全屏 dialog 变页面列）；中央区状态机（**run 进度图**→结果网格⇄舞台；进度图自 overlay 迁入中央区进度模式） | `components/generation/GenerationOverlay.tsx` 拆分；`routes/_app.projects.$id.index.tsx` 重构为工作面 |
| 舞台五类型渲染器（复用卡内容渲染器提拔）+ 检视器（ClipDetailModal 信息面板搬家）+ 双 modal 退役 | 新增 `components/workspace/Stage` / `InspectorRail`；删 `results/ClipDetailModal.tsx`、`results/AssetChatModal.tsx`；ChatModal 内脏迁对话列 |
| **lineage 端点**（`GET /projects/{id}/lineage`，血缘边服务端解析唯一发生地）+ 舞台**家族视图**（一跳血缘邻里：父 + 己 + 派生子，替代"同类型兄妹 ‹›"为同家族兄妹） | 新 `pipeline/routes/lineage.py`；`components/workspace/FamilyView`（FlowView 适配器） |
| 舞台指出升级（transcript 点选/文字框选 → mention 指认）+ 文字类舞台直编（contentEditable → operations）+ asset scope 退役（焦点注入，§6 context 加行） | Stage 组件；`chat/service.py` context 组装（一行）；剧本 harness 同步 |
| Before/After 对照 + 产物级 chips | Stage / InspectorRail |

### 第 5 周（08-31 ~ 09-04）：三档重跑接线 + 活图 spike + 09-03 裁决

| 交付 | 文件 |
|---|---|
| 三档重跑接进工作面（单节点/子图内核 + 对话接线；系统选执行深度，用户只听代价）+ **图节点点击 → `@workflow_step` mention 落 chat**（进度图从"看"变"指"） | `app/pipeline/`（重跑内核）；chat task_list 接线；RunFlowGraph `onSelect` |
| **血缘板 spike**（2026-08-07 收窄，ADR-036：项目全史产物血缘 = 唯一无界图面；只读投影，当前 run + 最新产物，历史不入图），复用 FlowView | 新增 `components/workspace/LineageBoard`（spike 级，不做拖拽/编辑） |
| 小白复述测试 + go/no-go（09-03；裁决问题收窄为"血缘板是否升正为默认中心"） | 裁决落 ADR-035/036 补记 |

## 4. 命名审计

| 名 | 义 | 备注 |
|---|---|---|
| 工作面 workspace | 项目页三区形态（对话列 + 中央区 + 检视器） | 入 NAMING §2（第 4 周落地时登记） |
| 舞台 stage / 检视器 inspector | 中央区焦点模式两零件 | 同上 |
| 配方检视 overlay | recipe inspect overlay，只读 | 第 2 周落地时登记 |
| 故事地图 story map | ~~运行期活图（spike 名）~~ **2026-08-07 拆分为二**（ADR-036）：run 进度图（排产项，`RunFlowGraph`）/ 血缘板（spike 名，`LineageBoard`，09-03 裁决去留） | 均已入 NAMING §2（2026-08-07，连同 `FlowView` / 血缘边 / 依赖边 / 家族视图） |
| 退役 | `ChatModal` / `AssetChatModal` / `ClipDetailModal`（第 4 周） | 入 NAMING 判例库 |

无新表。新列/字段：`RECIPE_REGISTRY` display 字段（注册内容，非表）；`run.context.recipe_id`（上下文键）；§6 context 焦点行（不落成表）。

## 5. 验收

1. **第 2 周周五（08-14）**：dub 入口链全通——点卡 → 检视 overlay（发射区上传 + 发送）→ chat 接住首发，全程无断点（2026-08-08 修订：回填折返删除）。
2. **第 3 周周五（08-21）**：dub 完全通路 v1——再加"对话定计划 → 生成 → 终态不跳转落结果网格（分数可见/动作抬出/chips）→ chat 精修"。
3. **第 4 周周五（08-28）**：工作面就绪——六屏全程一面；双 modal 退役无回退投诉；舞台指出/直编/对照可用；S1–S40 剧本无回归（asset scope 退役同步 harness）。
4. **第 5 周周四（09-03）**：活图 go/no-go——复述测试（小白看完能用自己的话讲出"它拿我的素材做了什么"）+ 使用数据，裁决落 ADR-035 补记；升正 = 地图成默认中心，不升 = 留检视模式零浪费。周五 🎯 Remix 精修就绪。
5. 前端手测（用户口径）：屏 1→6 全链路 + 刷新/跨设备重建 + 移动端堆叠。

## 6. Prohibited Behaviors

1. **禁**第二意图入口——overlay/composer 只构建首发消息；推断/合并/确认全在 plan path（意图单面化禁令平移）。
2. **禁**可操作画布——接线/自由拓扑/节点运行按钮/模型 SKU 货架永不面向用户；拓扑唯一来源 = `compile_graph`（LLM 亦只准提议 task list）。
3. **禁** toast+关窗式承接（第 3 周起）；终态信号 = 网格落位 + 舞台亮起本身。
4. **禁**产物配方徽章——配方身份只走 dock 抬头 / 打勾流皮肤 / chips 三站（2026-08-06 拍板）。
5. **禁**翻译失败亮图——ask 反问是唯一失败形态；图永不当错误信息或兜底界面。
6. **禁**图内堆历史——活图只画当前 run + 最新产物；历史归消息流记录卡。
7. **禁**每类型专属编辑 modal——准入规则：修改需 ≥3 结构化字段或多步流程才可立案（发布对话框为现存先例）；一两个变量永远走检视器/chip+chat。
8. **禁** composer/overlay 侧构建 prior——预填 = 可编辑模板文本，推断与合并永远服务端 plan path。
9. **禁**假进度（倒计时/百分比）——进度只呈现真实事件（步骤态、渲染扇出计数）。
10. **禁**编辑手势进 FlowView——`nodesDraggable` / `nodesConnectable` 常锁（拓扑唯一来源 = `compile_graph`，ADR-035 第 2 条）；导航能力（zoom / pan / minimap）按面门禁：有界面 fit-first 锁缩放，血缘板全开（ADR-036 补记）。图的内容不降级：每条边是真边（`inputs` / `derived_from_output_id`），禁装饰性插画。
11. **禁**消费面自绘边 / 自写布局——一切走 FlowView（`packages/clip` 同款单一画笔纪律）。
12. **禁**有界图面出现模型名 / 技术黑话——友好名 only（`recipes.flow.*` / `chat.stepKinds.*` i18n）。
13. **禁**血缘边前端拼装——lineage 端点服务端解析唯一发生地（同"任务书预设归服务端"纪律）。
14. **禁**进度图取代打勾流——线性旁白与空间图同源（workflow_steps）并存，不是二选一。
15. **禁** overlay 参数控件（2026-08-08，D6 二次修订）——语言选择器 / 参数表单永不在发射区现身（预设空间无界，控件 = A 形态漂移 + composer 建 prior 旁路）；预设**可见** = 产出 chips，**修改**唯一入口 = 预填文本改字 / chat 修订（chat 恒胜）。发射区发送机构与 composer 同一（useProjectLaunch），禁 overlay 自建生成路径（modal 直接跑 run 仍是 A 形态否决对象）。
