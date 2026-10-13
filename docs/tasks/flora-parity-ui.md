# UI 对齐批（冲刺版 · D4 一日包 + D5 顺手项）

> Status: 待开工（2026-10-13 拍板插入；随 MG 批压缩至 4 天冲刺，UI 件集中在 D4 = 10-19，溢出滑 10-20 上午、不挤占 MG 验收）。形态原型 = `scratch/skill-mg-ui-proposal.html`（双端对照屏：页顶真值表 / 桌面 Split 对照组 / 移动端锚卡两帧 / MediaLightbox 过渡，深浅双主题）。
>
> 压缩原则（2027 用户习惯尺）：用户习惯的是"对话里什么都能发生 + Flora 形体顺滑"，不是"货架很满"。冲刺只取体感权重最高的三件；货架作为顺手项收 D5（原型已数据驱动，转正成本低）。

## 形态基座（本批先决，ADR-118）

桌面 = **固定 Split**（对话 + 世界并排）；移动 = **纯 chat**。零切换控件、零 view-mode 持久化、零形态分叉门控、零切换触发相机节拍。宪法 = ADR-118：解耦律（图模型 = 唯一事实源，画布 = 一种投影）+ **chat 自足律**（画布完全隐藏时产品必须完整可用——本批锚卡是它的首个构造物，也是一切后续迭代的验收尺）。

## D4（10-19）：一日包三件（优先级序，活动行不滑出 D4）

**① 活动行体感**
- `apps/web/src/components/chat/ActivityStream.tsx`：ActivityRow / FoldedActivityRow 补 hover `bg-accent`；折叠头对齐「Ran N tools」形（chevron 旋转）；registry 加 icon 字段（kind → lucide；**icon ≠ 工具名**；failed 永不折叠、落定即退役不变）。

**② 消息 copy + 免责声明**
- 用户/助手消息动作条：copy = 纯客户端剪贴板（toast 静默档）。
- AI 免责声明行（"Repurposer is AI and can make mistakes…"，i18n 双语）。

**③ 锚卡（本批主体）**

*谓词与双键*
- 语义谓词 `canvasVisible`（**禁设备名硬编码**——谓词一处定义，全站单源）。
- chat 装配层注入两个**结构化上下文字段**：`canvas_available` / `canvas_visible`（进 context 装配，**不是 prompt 散文提示**）。
- 真值表：桌面 = true/true → 零锚卡零承接句；移动端 = false/false → 锚卡渲染 + 承接句。锚卡渲染 ⟺ `!canvas_visible`（**渲染时刻状态**，非历史快照）。

*形态*
- 单卡 = 缩略图 + 产物名 + 时长 + 类型徽标；N 产物 = **数组平铺**（flex-wrap 小卡行，**禁合集卡组件**）。
- 名缺 → null 容忍回退「类型词 + 时长」（无模板回填）；命名遵守展示文案二源律（世界自证，零冻参模板）。

*不变量*
- 指针语义；**无内联播放钮**；点击 = 开 MediaLightbox。
- 数据只读骑消息载荷既有 `output_refs`（types.ts:293）——**零新 SSE 订阅**。
- 挂在**终态收据行之下**，归收据所有（收据行 = 锚卡唯一父座）。
- 单一渲染面律修订注同批落档（ADR-118）：锚卡 = 终态收据帧——静态、零订阅、不是第二个 live 面。
- 解剖合规：rounded-md/lg、in-flow 零 shadow、`ring-foreground/10` 发丝线、文字三档、lucide、i18n 双语。

*环境感知（翻案入档 ADR-118 §6）*
- LLM 也消费环境上下文——但**只经结构化双键**；**禁 LLM 从用户语言/设备特征推断环境**。
- 唯一言语消费 = **交付承接句**：iff `!canvas_visible`（锚卡将渲染），交付回合收尾散文带一句朴素承接句指向紧随其后的产物行；`canvas_visible` 时收尾散文**永不交接、永不提及任何面**。
- 法条窄门：echo 防编造律（ADR-060）与展示文案二源律（ADR-058）只对「指向刚产出锚卡行的承接句」开这一处门，其余面指涉永禁。
- 承接句 = 普通 assistant.delta 散文——打字机双牙同批检查（null 读容忍 + paceSettledProse 节拍释放）。

## D5（10-20 上午，顺手项转正）：home 两级 tab 货架

- 原型屏①已是数据驱动实现：`components/home/RecipeTabs.tsx`（pill 轨 + 下划线子 tab）与 `RecipeShelf.tsx`（白容器横滑 + › 翻页）按原型转正；recipe 注册表加 `family` 字段 + `en.ts`/`zh.ts` 文案。
- 「模板」族首货架复用 RecipeCard；MG 族货架 = demo 视频 loop/muted。
- 纪律不变：**无真 demo 的族/卡不上架**；卡片唯一归宿 = composer 预填（永不是模板编辑器）；home 首次/回访双形态不变，货架在 composer 之下。

## 延期清单（本批明确不做）

- Queue chip（无真实队列读数 = 假数，世界自证门不过）/ 👍👎（存储决策未定，连摆位都不摆）/ assistant 行内节点 chip / Jump to latest / composer 24px 圆角例外 / mic 钮（死按钮永禁）。

## 验收口径（用户视角）

- **移动端**：跑完一个 run → 承接句 + 收据行 + 锚卡 → 点击锚卡开 MediaLightbox 可播；多产物 = 平铺小卡数组。
- **桌面**：同一次 run → 零锚卡、零承接句，画布在侧（对照组 = 现状不变）。
- **chat 自足律首次实证**：全程不看画布完成「上传 → 生成 → 接受 → 修订一次」闭环。
- 深浅双主题走查。

## 禁止事项

1. **模式切换 UI 永禁**（ADR-118）：禁复活任何档位控件 / view-mode 持久化 / 形态分叉门控 / 切换触发相机节拍。
2. **禁「Agent」字样**——N-25 禁令无例外适用；用户可见文案一律 assistant / 助手。
3. **环境双键 = LLM 唯一合法环境源**：禁从用户语言/设备特征推断环境；**唯一合法面指涉 = 交付承接句**，其余平台/面引用永禁。
4. 锚卡：禁内联播放钮 / 禁新 SSE 订阅 / 禁合集卡组件 / 禁脱离收据行独挂。
5. **禁 MentionEditor remount**；**禁相机自动动**。
6. 解剖合规：禁新增 rounded-full 例外；in-flow 面永不带 shadow；hover 一律 `bg-accent`。
7. **禁工具名上屏**；禁死按钮/假数据（Queue、mic、👍👎 见延期清单——摆位都不摆）。
8. 禁"模板编辑器"形态：卡片点击唯一归宿 = composer 预填。

## 验证仪式链

- vitest 纯套件：**谓词真值表**（双键 → 锚卡/承接句分支）+ 锚卡数组渲染 + fold 展开 + copy。
- 装配层 = pytest 纯套件：`canvas_available`/`canvas_visible` 双键入 context 装配 + 承接句谓词分支单测。
- **prompt_gate 重跑**（prompt 面变了：双键装配 + 承接句窄门——原「免跑」作废）。
- 纯 pytest 基线 + tsc 零 error；仪式链同序。
- **声音互斥检查**：MediaLightbox 播放是否接全局声音互斥——未接则本批接上。
- live 验收用户自跑（移动端锚卡点播 / 桌面对照零锚卡 / 深浅双主题）。
