# results-workspace 实施简报——结果工作面：终态承接、网格⇄舞台、配方检视 overlay

> Status: 📋 立项（2026-08-06，未施工）。施工窗口：**第 4 周轨 B**（结果网格重构 + 下一步 chips + 配方检视 overlay）→ **第 7 周**（工作面周三模式 + 活图 spike）→ **第 8 周周五**（活图 go/no-go 裁决，随三档重跑周）。
> 依据：STRATEGY §5（闭环优先 / 顾问姿态）；CHAT_ARCH §3.3 / §8；ADR-028 / ADR-032 / ADR-033 / **ADR-035**（DAG 用户化三切）；PROGRESS 第 4/7/8 周；竞品证据 2026-08-06 评审（DECISION_MATRIX §F——Lovart 类单产物工作面 ×2、flow 类画布+流程智能体 ×2、ElevenCreative 配方 modal、图片编辑 modal、gallery 检视 overlay，共七组截图）。
> 用户裁决（2026-08-06，五条）：
> ① **精修的对象模型是图，界面是语言**——隐藏画布，意图识别把用户语言翻译成图操作；图的用户化只剩"懂"（说明书/溯源），永不为"改"现身。
> ② **终态不跳转**——run 收官不打 toast 关窗，就地落成结果面。
> ③ **配方 = 检视 overlay + composer 回填**（B 形态），否决自带生成按钮的表单 modal（A 形态）：composer 保唯一发射台，overlay 只读。
> ④ **DAG 三切**：静态配方流程图 = 采纳；可操作画布 = 永久拒绝；运行期活图 = spike + 小白复述测试，第 8 周周五裁决。
> ⑤ **排期插一周**：第 7 周 = 工作面周，三档重跑顺延为第 8 周，周期收尾 10-16 → 10-23（PROGRESS §3"目标上线日"行，总监决策项）。

## 0. Context

用户到来即彷徨的第三步此前没有东西接：overlay 终态 toast + 关窗把用户扔到结果页网格；看（ClipDetailModal）与改（ChatModal）双 modal 接力；分数理由藏 tooltip；动作全收 "···" 菜单；完成后无下一步引导。竞品评审结论：行业收敛到"chat 前门 + 结构可见 + 单一连续面"，但画布上的操作镀铬（接线/节点模型货架/节点运行按钮）服务操作员画像，与"到来即彷徨"的知识专家画像冲突。**我们到达同一山顶的路径是：chat 为脊柱，产物为中心，图为说明书。**

关键架构事实（本简报的底座）：mention 注册表（asset/output/transcript_segment/workflow_step/recipe）= 节点寻址方案；RunPlan = 图内核；registry = 操作词汇表；outputs 经 `workflow_step_id` 挂图。**工作面不是移植别人的形态，是把已有架构渲染出来。**

## 1. 设计决策

| # | 决策 | 要点 |
|---|---|---|
| D1 | **终态不跳转** | run 终态：打勾流收官为 RunCard 聚合行 + 产物缩略条；中央区从进度网格翻成结果网格；无 toast、无自动关窗（W7 生效；W4 过渡期维持现状——结果页网格已重构，关窗落地体验不差） |
| D2 | **中央区状态机** | 进度网格（占位格逐条点亮）→ 结果网格（类型分段）⇄ 舞台（焦点单产物 + 检视器）。否决"顶部产物栏"：单类型形态假设，装不下 N 类 × M 条 |
| D3 | **流=档案 / 网格=当前 / 舞台=焦点** | 消息流 = 各轮记录卡（RunCard 终态产物条，历史可点击 → 拉回舞台检视）；网格 = `outputs` 当前态物化视图（无 run 分组逻辑）；舞台焦点规则 = 刚被碰的产物自动上焦点 / 点任意记录卡切换 |
| D4 | **chips 双级派生** | 网格模式 = 批次级（"全部加法语版"）；舞台模式 = 产物级（"翻译成法语 / 去口头禅 / 再来一版"）。零 LLM，按焦点产物类型 + 状态 + 配方确定性派生；顾问姿态"永给唯一下一步"的呈现层 |
| D5 | **配方身份贯穿三站** | dock 抬头（配方名 + 所需素材）/ 打勾流皮肤（步骤名 = 配方工艺名）/ 下一步 chips（配方感知）。**禁产物徽章**（2026-08-06 拍板）。实现：`RECIPE_REGISTRY` 注册项加 display 字段，run.context 带 recipe_id |
| D6 | **配方检视 overlay（B 形态）** | 点卡面 → 全屏只读检视：大片预览 + 固定信息卡（风格/标签/画幅——**无模型 SKU chip**）+ 可展开堆叠项（User prompt / Transcript / 原素材 / "它是怎么做的"流程图节）。Remix = 回填 composer（mention chip + 预填文本 + Assets 块必填提示态"需要：一段演讲视频"）。**否决 A 形态表单 modal**（自带输入槽+生成按钮）：平行表单系统、教义负债、服务不了未来真实 Gallery |
| D7 | **静态流程图** | 配方注册时作者策展的只读结构图（友好步骤名、固定结构、不可接线、无模型名），住 overlay 堆叠项；渲染器与 W7 活图 spike 共用（静态配方定义 vs 活 workflow_steps，同画笔两数据源） |
| D8 | **精修闭环** | 指出（舞台：transcript 行点选/文字框选 → 确定性指认，`transcript_segment` mention 已有座位）→ 表态（chat 说感受 / chips / 检视器参数直操——字幕样式/画幅/音乐/语言控件即改即预览）→ 执行（**系统选执行深度**：edit op / 单节点 / 子图重跑，用户只听一句代价"会重做文案和渲染，约 2 分钟"）→ 验证（舞台原位更新 + Before/After + undo） |
| D9 | **翻译两层** | 指认归确定性（mention / 舞台点选 / 焦点注入——不让 LLM 猜"第二条"是哪条）；意图归 LLM。翻译失败 = ask 反问（已有座位）；**图永不当错误信息或兜底界面**。新可翻译操作 = registry 注册项，永不开新面 |
| D10 | **双 modal 退役（W7）** | ClipDetailModal → 检视器；ChatModal → 对话列（全高左列，消息机器一寸不动）。**asset scope 会话退役**：工作面统一 project 会话 + 焦点产物上下文注入（§6 context 组装加一行"当前焦点 output"）；asset scope 的独有价值（auto target 注入 / revise 兜底）被焦点注入替代——判例随 W7 落地执行，届时同步剧本 harness |
| D11 | **网格组件双挂载** | 结果页裸访 + 工作面中央区共用同一网格组件（props 驱动，W4 写时即 workspace-ready） |
| D12 | **Before/After 对照** | 舞台级开关（按住看 Before），operations 快照 + `restore_version` 驱动，视觉类产物通用（竞品图片编辑 modal 的唯一采纳件） |

## 2. 六屏形态（终态，W7 完全体；W4 先落屏 1/1.5/4 的页面版）

**屏 1 · 配方检视 overlay**（点配方卡）：全屏只读——左大片预览（真实烘焙 demo），右上 Remix + Copy style；右侧固定信息卡（风格/标签/画幅）+ 可展开堆叠项：User prompt / Transcript / 原素材 / 它是怎么做的（静态流程图）。

**屏 1.5 · composer 回填态**（overlay 点 Remix）：mention chip + 预填文本（可编辑活文本，"配成德语"想改直接改字）+ Assets 块亮必填提示态。发送 = 现状链路（建项目 → overlay chat 首发）。

**屏 2 · 计划确认**：左列对话（用户气泡 → 计划摘要），dock 任务书钉输入框上方（配方抬头 + 槽位 + Start/Cancel + Auto/Review）；中央区安静态（素材概览）。参数齐 → reasons 空 → 自动 Start（S2 现成行为），无双重确认。

**屏 3 · run 进行中**：中央区 = 进度网格——分段标题先立（Clips · Post · Quotes），占位格逐条点亮（"Clips 2/5 · Post ✓ · Quotes 渲染中"，渲染扇出是真实事件，**不做假倒计时**）；左列打勾流照常（配方皮肤步骤名）。

**屏 4 · 终态**：一次平静交叉淡入——网格全部落位，top pick 抬升标记，分数直接印卡面；RunCard 收官（聚合行 + 产物缩略条）；批次级 chips 亮起。**无 toast，无关窗，无跳转。**

**屏 5 · 舞台（点任意卡）**：中央区切舞台——大播放器/大字版/画廊 + 同类型兄妹 ‹›（>1 时出现）；右栏检视器淡入：分数+理由常驻 / tabs（caption·topic·transcript，transcript 行可点→指认）/ 参数直操控件 / Publish 主按钮 + Download·Share。chips 切产物级。

**屏 6 · 修改循环**：说一句"开头两秒剪掉" → 左列 OpsCard（可撤销）；舞台原位重渲染（说完眼前就变）；↶↷ 头部常驻。大改（"该选 Q&A 那段"）→ 系统算执行深度、一句话报代价，确认才跑——用户永远看不到节点。

**移动端**：单列堆叠——网格 → 点卡 → 舞台 → "详情"展开块，对话沉底。网格即移动端答案，无额外形态。

## 3. 分期与改动点

### 第 4 周轨 B（08-24 ~ 08-28；轨 A = 成功定义 + 顾问姿态，另一线，不动本简报）

| 交付 | 文件 |
|---|---|
| 结果网格重构：类型分段、分数+理由卡面可见、动作抬出一级、失败/空态带下一步；组件 props 驱动（W7 双挂载准备） | `routes/_app.projects.$id.index.tsx`、`components/results/*` |
| 批次级 chips（确定性派生）+ 成功定义对照呈现（⚠️ 依赖轨 A schema） | `components/results/` 新增 chips 行；对照区块 |
| 配方检视 overlay（只读）+ Remix 回填 composer（chip + 预填文本 + Assets 必填提示态）+ 静态流程图节 | 新增 `components/recipes/RecipeInspectOverlay`；`HomeComposer`（回填态/Assets 提示）；`RECIPE_REGISTRY` display 字段（服务端） |
| i18n / Tour 锚点更新（results tour 三步挪位：分数 → 舞台 → chips） | `en.ts` / `zh.ts` / tour 配置 |

### 第 7 周（09-14 ~ 09-18）：工作面周

| 交付 | 文件 |
|---|---|
| chat 列提为页面区域（GenerationOverlay 拆壳：消息机器原样，外壳从全屏 dialog 变页面列）；中央区状态机（进度网格→结果网格⇄舞台） | `components/generation/GenerationOverlay.tsx` 拆分；`routes/_app.projects.$id.index.tsx` 重构为工作面 |
| 舞台五类型渲染器（复用卡内容渲染器提拔）+ 检视器（ClipDetailModal 信息面板搬家）+ 双 modal 退役 | 新增 `components/workspace/Stage` / `InspectorRail`；删 `results/ClipDetailModal.tsx`、`results/AssetChatModal.tsx`；ChatModal 内脏迁对话列 |
| 舞台指出升级（transcript 点选/文字框选 → mention 指认）+ 文字类舞台直编（contentEditable → operations）+ asset scope 退役（焦点注入，§6 context 加行） | Stage 组件；`chat/service.py` context 组装（一行）；剧本 harness 同步 |
| Before/After 对照 + 产物级 chips | Stage / InspectorRail |
| 活图 spike：只读投影（当前 run + 最新产物，历史不入图），复用屏 1 流程图渲染器；默认开给配方 run | 新增 `components/workspace/StoryMap`（spike 级，不做拖拽/编辑） |

### 第 8 周周五（09-25）：活图 go/no-go

复述测试（小白看完能用自己的话讲出"它拿我的素材做了什么"）+ 使用数据。升正 = 地图成默认中心（大一统达成：chat 列操作 + 图中心展示 + 舞台检视）；不升 = 留检视模式，零浪费。

## 4. 命名审计

| 名 | 义 | 备注 |
|---|---|---|
| 工作面 workspace | 项目页三区形态（对话列 + 中央区 + 检视器） | 入 NAMING §2（W7 落地时登记） |
| 舞台 stage / 检视器 inspector | 中央区焦点模式两零件 | 同上 |
| 配方检视 overlay | recipe inspect overlay，只读 | 同上 |
| 故事地图 story map | 运行期活图（spike 名） | go/no-go 后定去留 |
| 退役 | `ChatModal` / `AssetChatModal` / `ClipDetailModal`（W7） | 入 NAMING 判例库 |

无新表。新列/字段：`RECIPE_REGISTRY` display 字段（注册内容，非表）；`run.context.recipe_id`（上下文键）；§6 context 焦点行（不落成表）。

## 5. 验收

1. **W4 周五**：完全通路 v1——Remix overlay 检视 → composer 回填 → chat 定计划 → 生成 → 结果网格知下一步（分数可见/动作抬出/chips）→ chat 精修，全程无断点。overlay 滑期不阻塞验收（chip 链路兜底）。
2. **W7 周五**：工作面就绪——六屏全程一面；双 modal 退役无回退投诉；舞台指出/直编/对照可用；S1–S22 剧本无回归（asset scope 退役同步 harness）。
3. **W8 周五**：活图 go/no-go——复述测试 + 使用数据，裁决落 ADR-035 补记。
4. 前端手测（用户口径）：屏 1→6 全链路 + 刷新/跨设备重建 + 移动端堆叠。

## 6. Prohibited Behaviors

1. **禁**第二意图入口——overlay/composer 只构建首发消息；推断/合并/确认全在 plan path（意图单面化禁令平移）。
2. **禁**可操作画布——接线/自由拓扑/节点运行按钮/模型 SKU 货架永不面向用户；拓扑唯一来源 = `compile_graph`（LLM 亦只准提议 task list）。
3. **禁** toast+关窗式承接（W7 起）；终态信号 = 网格落位 + 舞台亮起本身。
4. **禁**产物配方徽章——配方身份只走 dock 抬头 / 打勾流皮肤 / chips 三站（2026-08-06 拍板）。
5. **禁**翻译失败亮图——ask 反问是唯一失败形态；图永不当错误信息或兜底界面。
6. **禁**图内堆历史——活图只画当前 run + 最新产物；历史归消息流记录卡。
7. **禁**每类型专属编辑 modal——准入规则：修改需 ≥3 结构化字段或多步流程才可立案（发布对话框为现存先例）；一两个变量永远走检视器/chip+chat。
8. **禁** composer/overlay 侧构建 prior——预填 = 可编辑模板文本，推断与合并永远服务端 plan path。
9. **禁**假进度（倒计时/百分比）——进度只呈现真实事件（步骤态、渲染扇出计数）。
