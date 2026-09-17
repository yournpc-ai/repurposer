# flora-parity 实施简报——FLORA 对齐：画布优先路由 + 折叠打勾增量感 + 节点交互升级 + 提问 dock 形态切换

> Status: 📋 已立项（2026-08-31，用户拍板；施工 2026-08-31 ~ 09-01 两个工作日）。
> 依据：**ADR-051（本条母决策）**；被修订：ADR-041 D2/D5 与外壳条款；不动：ADR-035/036（只读基座）、ADR-039（agent 层零变化）、ADR-040（chat 唯一发射路径）、CHAT_ARCH 四态契约。
> 证据：用户 FLORA 工作台走查（2026-08-31，真实案例项目 `/projects/c6616fc8-cc5c-45e6-aba7-76587c0b1f8d` 对照）。
> 排期：PROGRESS W7 头部插入批（原计划顺延 2 工作日，go/no-go 10-23 → 10-27，仍早于回退位 10-30）。

## 0. Context

FLORA 走查暴露的五处差距与我们的答案（拍板逐条对应）：

| # | FLORA 走查发现 | 我们的答案 |
|---|---|---|
| 1 | 点阵明显可读；我们的 1px/20% 几乎不可见 | dot-grid 一个配方调大调显，home + 结果画布两面共用（D-E1） |
| 2 | 免责行常驻基础输入上方，形态切换时随输入行消失 | 逐字照搬：en "Repurposer is AI and can make mistakes. Check important info."（zh 镜像），常驻 dock 基础形态输入区上方，形态切换随输入行隐藏（D-E2） |
| 3 | 提问 = 选项 1/2/3 + 尾行铅笔手输，dock 整体变形 | choice 待决时输入行 + 免责行隐藏，容器 = 问题行（去 ✓ 加 ×）+ 选项行 + 尾行铅笔手输入（D-D1） |
| 4 | run 节点生命周期：出生即有尺寸 → running → 填充 → hover prompt 框可编辑 → 重跑 → 变体分页 → 详情面板带模型事实 | 增量感两件（折叠打勾 + 占位物化）+ hover prompt 框（per-product spec）+ 变体分页 + 详情面模型事实（D-B/C/F/H） |
| 5 | 全程无中间 step 节点 | 物种差异不是架构缺陷（FLORA node = 单次生成单元 vs 我们 run = 编译批量 DAG）；真实缺陷是投影层三处：≤1 步脊噪音 / 无占位物化 / 全局 prompt 逐卡重复——逐条修（D-B/F/G） |

路由层病根：`?overlay=chat` / `?overlay=run` 是 fullscreen overlay 时代的遗留参数。项目页本应永远画布+dock——删掉壳概念，路由即简化；活画布（占位物化）是删 overlay 的**必要补件**不是可选项（原 fullscreen 壳覆盖了 run 期，壳退役后 run 期由活画布 + 折叠打勾接住）。

## 1. 工作项（A–H）与两天切分

### Day 1（一 08-31）：路由 + 进度面 + 提问 dock + 质感

| 项 | 内容 | 主要触点 |
|---|---|---|
| A | **路由简化**：`/projects/$id` 永远画布+dock；`?overlay=` 参数与 GenerationOverlay fullscreen 壳退役（dock 壳唯一形态）；composer → 项目页直达（router state 交付草稿不变）；`?overlay=` 全部引用清改（项目卡片 processing/待确认 CTA / 继续设置 / tours / attach 模式 latch） | `routes/projects.$id.index.tsx` / `GenerationOverlay.tsx` / composer 导航 / 项目卡片 / tours |
| C | **折叠打勾**（Claude Code 式）：RunTaskList 浓缩为默认折叠 meta 行——运行中 = shimmer 状态行 + 当前步名；点击展开步骤日志；收官 = recap 聚合行照旧（pinned 语义、量化行、失败人话行全部保留，只是默认折叠） | `RunTaskList` 组件 |
| D | **提问 dock 形态切换**：choice 待决 → 输入行（attach + MentionEditor + history + send）+ 免责行隐藏；容器 = 问题行（去 ✓ 加 × 关闭 = bail 通道）+ 选项行（字母徽章不动）+ 尾行铅笔手输入（Enter 提交 freeform；确定性字母/序号/原文 autoResume 映射不变）；形态切换时容器与消息流边界明确区分 | `QuestionDock.tsx` / `GenerationOverlay.tsx`（choiceDock 分支、`choicePlaceholder` 逻辑删除） |
| E | **点阵 + 免责行**：dot-grid 配方调大调显（一个配方两面共用，两面专用纪律不变）；dock 基础形态输入区上方常驻免责行（en 逐字 "Repurposer is AI and can make mistakes. Check important info."；zh 镜像「Repurposer 是 AI，可能出错。重要信息请核对。」），形态切换时随输入行隐藏——取代既有 `results.dock.honesty` 行（位置/文案按本条统一） | `styles.css` `@utility dot-grid` / dock 组件 / i18n 双端 |

### Day 2（二 09-01）：活画布 + 节点交互

| 项 | 内容 | 主要触点 |
|---|---|---|
| B | **占位物化**：run 开始即从 derived preview（ADR-043 编译期干跑，现成）物化占位产物卡——roster + 画幅已知，`productNodeSize(aspect)` 定最终尺寸，出生即占真位；产物落地原地填充；占位卡带 @ mention 教学文案（功能性）；画幅未知取默认档 | 服务端 outputs.py 序列化（占位行投影）/ `runFlow.ts`（placeholder 节点态）/ `FlowNodeCard`（占位皮） |
| F | **hover prompt 框 + per-product spec**：产物卡 hover → tooltip + 磨砂 prompt 框，展示**该产物自己的 spec**（fork 派生行的目标语言 / hook / 参数——从编译图 slot 参数投影，runFlow 的全局 run `prompt` 逐卡重复退役）；可编辑 → 发送 = 带焦点预钉的修订回合（骑 `POST /chat`，零新通道） | 服务端序列化（per-product spec 投影）/ `runFlow.ts` / `FlowNodeCard`（hover 浮层）/ dock 焦点机构（现成） |
| F2 | **变体分页（1 of N）**：修订/重跑后产物卡带分页器；数据源 = Operation Model 版本快照 + fork 家族（现成）；翻页切换展示 | `FlowNodeCard` / outputs 快照查询 |
| G | **脊收编**：折叠步 ≤1 时过程脊不成节点（边经既有祖先投影规则解析，零新规则） | `runFlow.ts` 分类环 |
| H | **详情面模型事实**：灯厢信息栏陈列模型 / provider 事实（caption 恒友好名不变；节点面永无选择器） | `ResultsCanvas` MediaLightbox 信息列 |

## 2. 验收标准

1. **路由**：全仓 grep `overlay=chat` / `overlay=run` 零命中；composer 发送直达 `/projects/$id` 画布+dock；processing 项目卡片 / 待确认 CTA 点进项目页即见对应 dock 形态（活 run / 任务书）；刷新 / 断线重连 / 跨设备直接呈现终态不播回放（ADR-041 D2 不破）。
2. **折叠打勾**：活 run 时消息流只有一条折叠状态行（shimmer + 当前步名）；点击展开完整步骤日志（done ✓ / running spinner / pending 空心 / failed ✗ 人话全部保留）；收官 recap 聚合行照旧落档。
3. **提问 dock**：choice 待决时输入行与免责行不可见；问题行无 ✓、有 ×（点击 = bail，与既有 bail 按钮同通道）；选项行字母徽章映射不变；尾行铅笔手输入 Enter 提交 freeform（autoResume 字母/序号/原文映射零 LLM 不变）；回答后坍缩回基础形态 + 已答问题双层入流不变。
4. **增量感**：review 档起 run → 占位产物卡立即出现在最终位置（尺寸 = 该产物画幅的最终尺寸）；产物落地原地填充无位移；折叠打勾行全程可见。
5. **hover prompt 框**：hover 任意产物卡见其自己的 spec（fork 卡见其目标语言/参数，不再是全 run 全局 prompt）；编辑发送 = 修订回合进 chat 流（焦点灰行 + 历史展开照旧），服务端收到焦点钉住的目标。
6. **变体分页**：对同一产物做修订/重跑后卡上出 1 of N 分页，翻页切换各版本展示（数据源 = Operation Model 快照）。
7. **脊收编**：折叠步 ≤1 的 run 画布无过程脊节点，边仍然正确（经祖先投影）；≥2 步照旧。
8. **详情面**：灯厢信息栏可见模型 / provider 事实；画布节点 caption 无模型名（grep 节点 caption 渲染路径）。
9. **点阵/免责行**：home 与结果画布点阵同配方清晰可读（双主题）；dock 基础形态输入区上方常驻免责行，提问形态时消失。
10. **回归**：S1/S13/S48 + accept_prompt_surface 全绿；web tsc / api compileall 绿；i18n en/zh 双端无裸键。

## 3. Prohibited Behaviors

1. **禁**新执行通道——hover prompt 框发送必须走 `POST /chat` 回合（意图单面化禁令平移）；任何形式的"节点就地重跑按钮" = 可操作画布复辟（ADR-035 §2 永拒）。
2. **禁**模型选择器上节点面 / SKU 货架——Decision 5 只解禁**事实陈列**（详情面），picker 仍只在真实第二 provider 出现时以策略开关形态落地。
3. **禁** chat / 意图识别任何行为变化——PlanAgent / ChatIntentAgent / 四态契约 / plan path / question-answer 数据层 / autoResume / 停靠法则全部不动；本批只改渲染壳与投影层。
4. **禁**虚构占位——占位 roster 必须来自编译期干跑派生（derived preview），禁前端猜产物清单；画幅未知取默认档，禁硬编码假画幅。
5. **禁**步骤叙事进图——折叠打勾是步骤叙事唯一面；图的状态只表达产物占位/填充（图内容），不表达步骤进度（ADR-041 D2 收窄后的边界）。
6. **禁**假进度 / 剧场动画——占位→填充是真实 output 行落地事件的投影；spine/plan 脉冲 = 真实 step 状态投影（既有机构）。
7. **禁**拓扑编辑手势进 FlowView（#12 本义不变）——hover prompt 框是卡面浮层不是图编辑。
8. **禁**新表 / 新队列——占位吃 derived preview 现成干跑，变体分页吃 Operation Model 快照现成表。
9. **禁**硬编码免责行文案改动——en 逐字按拍板原文；zh 镜像走 i18n 双端常规流程。
10. **禁**双壳残留——fullscreen 壳代码整族删除（不是隐藏分支）；dock 壳成为唯一形态后才算 A 项完成。

## 4. 风险与注意

- **attach 模式 latch 的替代**：fullscreen 壳退役后，原 `?overlay=run` 的 attachRunId latch 机构需在项目页内重建（活 run 时 dock 自动进入打勾态）——注意页面自身 SSE refetch 把 run 翻成 completed 时打勾态中途卸载的老坑（CHAT_ARCH §8 进度面段的原话教训）。
- **占位卡与诞生编排的关系（2026-09-01 用户拍板定稿）**：reveal 不是独立的收官行为——占位世界里诞生 = **生长驱动**：占位物化 / 产物原位填充 / 修订生长共用同一条规则（画布挂载期间新生节点按编译序 `BIRTH_STAGGER_MS` 交错诞生 + 边描画），水合首帧（刷新/重连/历史）直出零动画；running 占位卡带 FLORA 左→右填充擦除（纯 CSS 缓动封顶 96%，不声称分数——禁令 #4 禁假进度不破）。物化与诞生共用 `BIRTH_STAGGER_MS` 常量族，禁各起时钟。配套：dock 起跑经 `onRunStarted` 通知页面 refetch，页面 SSE 从 run 第一拍挂上（终审捉出的 confirm 起跑路径缺口，同批根修）。
- **per-product spec 的数据源**：fork 派生行的 spec 来自编译图 slot 参数（服务端投影），前端永不拼装（投影层纪律同血缘边 #11）。
- **变体分页的"版本"定义**：= 同一产物的 Operation Model 快照链 + fork 家族兄妹；quotes/carousel 既有的 items 变体切换器（`variants` 字段）是**条目**切换不是**版本**切换，两者不同槽——禁把版本分页器与条目切换器合并成一个控件。
- **改 pipeline 代码必重启常驻 worker**（铁律）；占位序列化动 outputs.py 属 pipeline 面。
