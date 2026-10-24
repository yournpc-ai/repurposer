# Product Flow Alignment——当前合同与剩余验收

> Status: staging、Product Graph membership/rank/projection 与 RunOp 拓扑解耦已有代码层结果；Greenfield 全链验收未闭环。C-3 空帧显式化和 Batch D 出生编排是否继续由当前产品需求决定，不从旧“施工中”自动扩批。

## 1. 当前架构不变量

- **Product Canvas ≠ Execution Graph**：画布只展示用户拥有、消费、验证或可修改的产品对象；task_book / preprocess / understand / plan / materialize / render / verify / checkpoint / queue / retry 永不成节点。新类型/新 tool 默认隐藏，必须声明 product visibility。
- **ADR-113 边界**：transcript 是资产内容，不是 product node；新图不得为 Source→Transcript→Consumer 再造节点或合成边。合法中间工作产品仍按实际产品语义注册，不因“不是最终产物”而隐藏。
- **rank 是唯一空间权威**：x 是 rank 的投影；frame 只保留 y 座位、w/h 预留与稳定锚。rank 只消费生产/消费语义边，lineage/historical/presentation-only 边不参与。
- **执行不读布局**：RunOp 使用同一 Product DAG 的拓扑序；Canvas 可有 visibility gate，RunOp 对隐藏 modifier 仍按执行关系排序，layout.x/y 永不决定执行。
- **方向与稳定性**：可见 product edge 满足 rank(target)>rank(source)，x 投影同向；sibling 序确定且不依赖 birth order。缺 rank/帧不得静默补原点；dev 显式失败，prod 只能回退 rank 投影。
- **图先呈现后运行**：完整 draft 链一次 stamp，run 在同一 node id 原地更新；动态生长只能是呈现编排，不能把 execution step 滴成产品节点。
- **Chat/Canvas 同一事实**：节点状态和 chat 活动都来自真实世界事件；相位必须随覆盖、活动终止或回合终帧清除。当前素材读取按 ADR-102 在工具内等 ready/failed，不恢复 understanding_warmed 接力。
- **staging 生命周期**：created → uploading → uploaded → attached（+ failed/expired）；PUT 成功但未 attach 的对象必须由 TTL reaper 回收，已被资产引用的 key 不删。

## 2. Greenfield 验收

以全新项目、正常生成和修订为唯一主链，不把旧帧修复能力当本批验收：

1. 选文件/拖入即上传并显示真实进度；Generate 只做建项目、attach、导航，未完成上传有明确阻塞。
2. 多文件、失败重试与 × 删除正常；staging 孤儿含 PUT 成功未 attach 窗口会被回收。
3. 上传后的资产行和资产卡一致；新图没有 transcript 节点，转写内容仍在资产卡可读。
4. 一个回合的相位/活动随真实工作变化，无 stale phase、无第二条 Thinking；processing 未完成前不产生依赖半成品的回答。
5. Canvas 只含合法产品对象；draft→running→done 是同一 node 更新，run 不制造执行节点。
6. 所有可见 product edge 严格 L→R，sibling 序稳定；前端不重算第二份 rank/depth。
7. 构造 frame 与拓扑相反的数据，RunOp 仍生产者先于消费者，canvas-hidden modifier 顺序正确；修订 run 不读 layout。
8. streaming/settled Markdown 与刷新回放一致；背景 refetch 不动相机、不重排。
9. 现有曲线、端口和锚点 routing 无回归；深浅主题与移动端均无第二布局源。

自动证据至少包括 product-graph/layout 纯测试、共享恶意帧 fixture、当前受影响旅程与 web 检查；真实 Greenfield 走查不能由纯测试替代。

## 3. 尚未排期的候选范围

### C-3 空帧显式化

若继续：出生地保证每个节点有合法帧，盘点存量 `{}`；删除前端 `?? 0` / `?? {x:0,y:0}` 静默兜底。dev 响亮失败，prod 用 rank 投影，不迁移旧帧、不写回重排。

### Batch D 出生编排

若继续：draft 链按真实 rank 深度序 reveal，其余基线路径不动画；`prefers-reduced-motion` 瞬染，既有节点不跳位，背景 refetch 不动相机。不得让服务端逐节点 drip-feed，不引入大型动画库。

### 画布可读性剩余

同族链分组、asset→assembler 跨列长边路由和 settled 居中仍是 PROGRESS 的独立需求；只有验收证明本合同已完整吸收才关闭，不为排线创造语义节点或假边。

## 4. 已知对账项与存量迁移门

legacy `materialize` 的读面可见性与新类型准入门不一致，只能在生产 DB 守卫查询证明相关 legacy 行清零后删除兼容；具体条件归 `lifecycle-phase-6-hygiene.md`，不得在本批用全局过滤器掩盖。

**task_book / transcript / exploration 的真实目标 DB 验收仍开放。** 当前代码已停止新写 task_book/transcript 图节点，探索写 `exploration_rows`；这不等于存量迁移已在目标环境验证。升级前必须在真实目标 DB 的隔离副本上取证并准备可恢复备份，不能用空开发库代替：

1. 盘点 legacy task_book、transcript 节点及关联边、`spec.edited_text`、现有 `assets.edited_transcript` 和探索行；确认 dock 计划正文仍由 `messages` 持有，不依赖 task_book 节点。
2. `s2b7d4e6f1a3` 必须先逐个资产把 transcript `spec.edited_text` 回填到 `assets.edited_transcript`，再删旧 transcript 边和节点；源 transcript、`meta.words` 与用户改稿不得丢失或被反算。
3. `l2b5c8e1f4a7` 删除 task_book 边和节点后，验证消息 dock、pending plan、图读取、编译、run/replay 正常；`k1a4b7c3d4e5` 后探索只读新表，legacy 探索行保持过滤，零双写、零回流执行闭包/报价/rank。
4. 在副本上执行完整 upgrade，再核对行数、抽样内容、外键与零孤儿；按真实回退方案演练 downgrade/恢复。**task_book 的 downgrade 是 no-op，transcript downgrade 会删除覆盖列且不会重建节点**——不得宣称数据可逆；需要回滚用户数据时只能走事先验证的备份恢复。
5. 目标环境迁移须另行授权并先 dry-run/备份；上线后验证旧节点零新写、`exploration_rows` 无双写、读面与重放一致。未完成前不得删除迁移脚本或把“代码已 de-stamp”写成“生产迁移完成”。

## Prohibited Behaviors

- 禁重写 edge routing、用 clamp/翻转边/固定 x-y 掩盖拓扑、引 dagre 或服务端重排旧帧。
- 禁把 execution 概念放上画布、为排线新增语义节点/假边、让视觉坐标决定执行。
- 禁 Generate 后才开始上传、静默建 project 当 staging、服务端整对象拷贝当 attach。
- 禁恢复 understanding_warmed、为相位/生长建第二客户端状态机或引入 SSE 事件总线。
- 禁改变打字机、图先呈现后运行、R1 执行身份与授权不变量；禁把 PLANNED 写成 CURRENT。
