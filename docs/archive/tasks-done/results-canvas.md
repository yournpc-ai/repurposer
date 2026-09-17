# results-canvas 实施简报——结果画布：打勾收官就地长图 + 底部 dock + 移动端 UI in chat

> Status: ✅ 已落地（2026-08-11 立项；结果画布为桌面默认中心，后续各轮走查迭代——产物卡解剖 / 工具条做薄 / 名词节点收窄——逐日落 PROGRESS）。
> 依据：ADR-035（可操作画布永久拒绝——不变）/ ADR-036（FlowView 基座）/ **ADR-041（结果画布升正）** / ADR-040（配方 = 提示词）；STRATEGY §5；排期以 PROGRESS 第二周为准。
> 取代：`tasks/results-workspace.md`（2026-08-06 立项，本简报立项后退役——中央区状态机 / 六屏 / 工作面三区被本简报吸收改写；chips 双级派生 / 翻译两层 / Before-After / 焦点注入沿入本简报）。

## 0. Context

两个结构性事实促成形态终裁：① **多产物扇出被一切线性容器物理消灭**——tabs / 手风琴 / 消息流同为线性容器（08-07 dub 对照包"图结构被线性容器消灭"证据的推广），空间面是多产物的唯一解法；② chat 打勾收官 → toast 关窗 → 跳结果页 = 跳切，把"过程"和"结果"劈成两个房间。形态答案：**过程在时间面（chat 打勾），结果在空间面（canvas）；转场 = 收官时画布在输入组身后长出来，输入组全程零位移**。总原则不变：精修的对象模型是图，界面是语言——图只为"懂"与"指"现身，永不为"改"现身。

关键架构事实（本简报的底座）：FlowView 只读图基座（ADR-036）；outputs / workflow_steps 同源双视图（桌面空间图 / 移动时间流）；mention 注册表（指认确定性，MENTIONS）；GenerationOverlay 消息机器（拆壳不动内脏）。

## 1. 设计决策

| # | 决策 | 要点 |
|---|---|---|
| D1 | **结果画布 = 桌面/iPad 默认中心** | 项目页收官态 = FlowView 渲染当前 run 拓扑 + 最新产物（真节点真边）。多 tab 结果页与"结果网格为默认中心"退役；已动工的网格重构件降级为移动端列表渲染件复用，零浪费 |
| D2 | **进度不进图** | 打勾流是唯一进度面（run 进度图排产撤销）——run 进行中是图信息量最低的时刻；时间信息归 chat，空间信息归 canvas |
| D3 | **转场 = 输入组零位移** | 收官帧：遮罩淡出 + 消息区上收 + 画布按 `seq` 编译序诞生回放（真实事件的缓动回放，禁剧场）；reduced-motion 即时呈现；断线重连 / 历史打开直接呈现终态，不播回放 |
| D4 | **底部 dock**（2026-08-13 修订：一体容器 + 灰行入流） | chat 外壳从全屏 dialog 转 Mac-Dock 式居中悬浮输入组（带 padding，非通栏；同一消息机器内脏不动）。**两态**：收起 = 输入组（唯一常驻 chrome）；展开 = 历史区域在**同一磨砂容器内**向上生长（容器独占圆角与玻璃，子件全方；摘要卡条 / 焦点 chip / 三态机退役）。**系统层灰行入流**：步骤勾选 / run 收官 recap / 焦点事件 = 消息流内灰色 meta 行（`MetaRow`，muted + xs + 无填充 + 超长截断可点开）——信息入流，控制留底。**agent 发声（含焦点设置等系统事件）历史必自动展开**；点画布空白 = 回中性（历史收起 + 焦点清除，pane 级）；画布视口留 bottom safe-area ≥ dock 高 + padding。一个输入组三停靠位：首页 composer / overlay 底排 / 结果 dock |
| D5 | **产物节点 = 卡** | 缩略图 / 分数 + top-pick 长在节点上；卡下常驻磨砂工具条（44px 带，2026-08-19 做薄；hover 化否决——小白可发现性优先）：信息位（语言/分辨率/时长/画幅）左、下载 / 删除 + ⋯ 菜单（发布/打开/在对话中指认）右；单击 = detail modal 旧逻辑原样；publish modal 保留。**过程节点永无 toolbar；toolbar 装图操作（运行 / 接线）永久禁区** |
| D6 | **密度三档 + 渲染单元**（2026-08-12 修订；2026-08-19 名词节点收窄） | 配方说明书 = 策展密度（≤5 节点，只画兑现承诺的步骤）；结果画布 = 名词密度（素材 + 任务书文本节点 + 产物主角）；run 期无图。**渲染单元 ≠ 执行单元**——step 全量落库（成本 / 重跑 / 血缘靠它），画布按节点类自描述 `canvas_key` 聚合：同键合一卡（现行唯一授予 = `plan`：understand+checkpoint+plan 的任务书，dock-surface 雾面玻璃文本节点）；**过程动词永不上图**（select_clips / dub / add_music 授予全移除，translate_clip 08-15 先例推广），无键折"过程脊"组节点（干预 = 点产物卡注入 dock 焦点 / 脊内步骤 pill 走 @workflow_step），`canvas_hidden`（render；prelude——preprocess/persona_bootstrap，08-19 二轮 R1 成环修复，资产喂边走下游兜底）永不上图、状态原地投影到产物卡。节点解剖 = 输入在边上、规格在身上、结果在卡上、改动在 chat。判定任一节点只问："它是名词吗？"——动词一律折脊 |
| D7 | **导航门禁** | 缩放 = 导航不是编辑：配方卡说明书锁 fit；结果画布开放 pan / zoom（minimap 退役——稀疏小图无导航价值）。拓扑编辑手势（拖节点 / 接线）在任何面物理缺席——拓扑唯一来源 = `compile_graph` |
| D8 | **修改通道唯一 = chat** | @mention 确定性指认（点过程节点插 `@workflow_step`）；ChatModal / AssetChatModal 退役——产物对话归 dock + 焦点注入（context 加一行"当前焦点 output"；asset scope 会话退役判例随本条执行，剧本测试 同步）。**焦点 = 一次性消费 + 落库**（2026-08-13 修订）：点画布产物 → 流尾焦点灰行 + 历史自动展开；发送携带 `focus_output {id,label}` 即消费（点画布空白即清，失败回滚即还）；焦点持久化在用户消息上（`messages.focus_output`），历史回读渲染焦点前缀灰行。undo 常驻；大改前一句代价提示（undo 撤产物状态，撤不回已花积分） |
| D9 | **历史与资产：存是数据律，显是视图律** | 产物与操作全量落库（outputs / operations append-only）；画布只画当前 run + 最新产物；历史经 chat 档案流（RunCard 缩略条点了拉回 detail） |
| D10 | **移动端 = UI in chat** | 不渲染 canvas（< iPad 宽度）；对话沉底（与桌面 dock 同心智模型）；一回合一张 RunCard——卡头血缘摘要行（"素材→…→成片"，可展开过程脊）+ 产物分组缩略条（带分数徽章）+ 卡下 chips；点缩略图进全屏查看器（家族兄妹滑动 + 底部迷你输入条）；点卡即焦点免 @。卡片种类注册表制：计划 / 操作 / 结果三型，新增 = 注册项 |

## 2. 形态规格

**桌面三态**：规划期（overlay 全屏 chat 照旧：首发 / 反问 / 任务书 dock / 打勾）→ 转场（D3）→ 结果期（整屏 canvas + 底部 dock）。

**结果画布构图**：左 = 素材节点（asset 皮）；中 = 任务书玻璃文本节点（唯一 artifact 授予 = plan，2026-08-19 名词节点收窄）+ 过程脊（无键管道步骤的折叠组节点，点击就地展开）；右 = 产物节点列（output 皮大卡）。边 = 真边（dependency / lineage 双语义存于数据，视觉统一安静灰）。

**移动端（本期）**：不渲染 canvas，保留现有结果列表兜底；RunCard 增强（D10 全量）排第三周。

## 3. 分期与改动点

### 08-12（三）：拆壳 + 转场 + 画布挂载

| 交付 | 文件 |
|---|---|
| GenerationOverlay 拆壳：消息机器原样，外壳从全屏 dialog → 结果期底部 dock | `components/generation/GenerationOverlay.tsx` |
| 收官转场（遮罩淡出 / 消息区上收 / 画布诞生回放；降级规则见 D3） | 同上 + 动画 |
| 结果画布 v1：FlowView 适配器（workflow_steps + outputs → nodes/edges，终态一帧渲染）+ 项目页挂载，多 tab 结果页退役 | `components/flow/`（新 ResultsCanvas 适配器）；`routes/_app.projects.$id.index.tsx` 重构 |

### 08-13（四）：产物节点卡 + 接线 + ChatModal 退役

| 交付 | 文件 |
|---|---|
| 产物节点卡（缩略图 / 分数+top-pick / 下一步建议）+ hover toolbar（带 gap 浮 pill） | `components/flow/` |
| 单击产物节点 = detail modal 旧逻辑；publish modal 保留 | 接线 |
| ChatModal / AssetChatModal 退役删除；产物对话归 dock + 焦点注入；asset scope 判例执行 + 剧本同步 | `components/chat/`、`chat/service.py`、`scripts/chat_scenarios.py` |
| 结果页 tour 锚点重锚产物节点卡（`data-tour="results-*"`） | tour 配置 |

### 08-14（五）：过程脊 + 门禁 + 联合验收 + 复核门

| 交付 | 文件 |
|---|---|
| 过程脊折叠（组节点 + 步骤计数 + 就地展开）+ 节点展示档（NodeBase 自描述） | `components/flow/`、`app/skills/` 节点类属性 |
| 导航门禁：结果画布 pan / zoom 开放（配方卡锁 fit 不变；minimap 退役） | FlowView 门禁 props |
| 点过程节点插 `@workflow_step` mention（本面限定的候选源） | 画布 `onSelect` → dock |
| 【联合验收】+ 小白复述测试（画布转正复核门） | — |

### 后续（第三周起，不占本周）

| 交付 | 备注 |
|---|---|
| 移动端 RunCard 增强（血缘摘要行 / 过程脊 / 全屏查看器滑动 + 迷你输入条） | D10 全量 |
| 三档重跑接线 | ⚠️ 被画布挤压顺延，吃第三周缓冲 |
| Before/After 对照（detail modal 内） | 排期以 PROGRESS 为准 |

## 4. 命名审计

| 名 | 义 | 备注 |
|---|---|---|
| 结果画布 | results canvas，项目页收官态默认中心 | 落地时入 NAMING §2 |
| 底部 dock | chat dock，结果期的输入组停靠位 | 同上 |
| 过程脊 | process spine，中间步骤的折叠组节点 | 同上 |
| 诞生回放 | 收官时按编译序的入场动画 | 同上 |
| 退役 | 结果网格（默认中心地位）/ 工作面三区 / 舞台·检视器（页面区方案）/ run 进度图（未落地即退役）/ ChatModal / AssetChatModal | 入 NAMING 判例库 |

无新表。新字段：节点展示档（节点类属性，非表）；其余零变化。

## 5. 验收

1. **本周五（08-14）**：主链一次走通——点卡 → 上传发送 → 打勾 → 收官转场（输入框零位移）→ 产物节点卡（分数可见）→ 单击 detail modal / toolbar 下载发布 → dock 精修（@output 指认）。
2. ChatModal / AssetChatModal 删除无残留入口；多 tab 结果页退役。
3. 刷新 / 断线重连 / 从 `/projects` 进入终态项目：直接呈现画布，不播回放。
4. S1–S41 剧本零回归（chat 行为面不变）。
5. **画布转正复核门**：小白复述测试——看完能用自己的话讲出"它拿我的素材做了什么、做出了哪几样" → 转正；不过 → 结果网格回退默认中心（组件保留），canvas 降为检视入口，零浪费。

## 6. Prohibited Behaviors

1. **禁**第二意图入口——dock / overlay 只构建消息；推断 / 合并 / 确认全在 plan path（意图单面化禁令平移）。
2. **禁**可操作画布——接线 / 自由拓扑 / 节点运行按钮 / 模型 SKU 货架永不面向用户；拓扑唯一来源 = `compile_graph`（ADR-035 第 2 条不变）。
3. **禁**过程节点 toolbar；产物节点 toolbar 只装产物动作（预览 / 下载 / 发布）。
4. **禁**假进度 / 剧场动画——动画永远是真实事件（编译序回放 / 状态迁移 / 真实生长）的投影。
5. **禁**会话外播诞生回放——断线重连 / 历史打开 / 跨设备直接呈现终态。
6. **禁** dock 静默——agent 发声（ask / 任务书 / chips / 收官摘要）dock 必自动升起；顾问姿态"永给唯一下一步"不因布局收敛失声。
7. **禁**翻译失败亮图——ask 反问是唯一失败形态；图永不当错误信息或兜底界面。
8. **禁**图内堆历史——画布只画当前 run + 最新产物；历史归 chat 档案流。
9. **禁**消费面自绘边 / 自写布局——一切走 FlowView（`packages/clip` 同款单一画笔纪律）。
10. **禁**图面模型名 / 技术黑话——友好名 only（`chat.stepKinds.*` / `recipes.flow.*` i18n）。
11. **禁**血缘边前端拼装——lineage 服务端解析唯一发生地。
12. **禁**拓扑编辑手势进 FlowView——`nodesDraggable` / `nodesConnectable` 常锁；pan/zoom 是导航，按面门禁（D7）。
13. **禁**移动端渲染 canvas——< iPad 宽度走 RunCard 流。
14. **禁**一回合多气泡——N 个产物住一张 RunCard，永不成 N 条消息。
15. **禁**每面各起输入组件——dock 挂 composer 同款 MentionEditor 族（输入组件唯一禁令平移）。
