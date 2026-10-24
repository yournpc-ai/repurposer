# 渲染所有权与就绪语义——剩余验收（ADR-096）

> Status: 编译期 render owner、静态屏障与 track 原子写已有代码层结果；交错序列/live 验收仍开放。一个历史 dev 产物的条件恢复尚未执行，不能用新代码已落地宣称它已经恢复。

## 1. 当前不变量

- 编译器为每份 output 静态指定唯一 **render owner**（通常是装配站）；非 owner morph 不 re-pend、不创建 render step。
- owner 的 render step `inputs` 静态包含同产物全部并行写入者；不得再用 seq、step 状态、时间戳或墙钟猜所有权，旧 `later_inplace_morph_exists` / defer 机制不得复活。
- 非 owner morph 失败必须阻断 owner 并走命名修复路径；不得拿部分 spec 渲染看似成功的终产物。
- in-place morph 在 output 行锁内按 track 局部更新（`jsonb_set` + TRACK_REGISTRY 权限），合并后完整 `ClipSpec.model_validate`；不同 track 不丢更新，同 track 冲突显式拒绝或串行。
- verify/delivery 不只看 payload：文件无效、render 状态矛盾或版本不对应均不能 delivered。film/clip 还须满足各自 probe 与 `files.video` 准入；部分失败按真实产物分 failed/partial。
- reconcile 仅是修复机制，正常路径必须在 compiler/runner 层自给；归档产物不得被 re-pend，跨 run 的在飞渲染不得被双重拥有。

## 2. 交错序列验收

至少覆盖：

1. owner 先启动、其他写入者后启动；
2. 非 owner 先完成与 owner 先完成两种顺序；
3. 非 owner 失败 → owner 阻断，无部分交付；
4. owner 屏障等待中被取消；
5. run 恢复后屏障与 owner 不重复执行；
6. 多 output fork 时每个 owner 只等待自己的写入者；
7. 并发不同 track 不丢更新，同 track 冲突可诊断，跨 track 联合不变量重校验无漏；
8. 空文件、文件与 spec 版本不符、render 已完成但文件缺失均不得进入交付卡或成功播报。

所有交错序列终态必须是零死渲染、零提前渲染、产物与有效文件一致。当前纯测试与真实 worker/live 证据分别记录，不能相互替代。

## 3. 历史 dev 产物条件恢复

目标：dev DB output `1cab75fc-7429-4c3f-91d8-62261e1ba2da`。只有逐项证明以下条件才可操作：

- 属于目标事故 run 且未归档；spec 已包含全部预期 morph 终改；
- 没有有效 pending/running render step，文件无效且没有有效在飞 token；
- 不会重复扣费、重复建任务或覆盖其他执行者。

满足后，在事务内执行条件 UPDATE 并断言行数，再经既有 fan_out/enqueue 建任务——不是只改状态；最后确认认领、完工、文件有效以及 run/output 状态一致。**禁止裸 SQL 状态修复，禁止未经授权触碰生产数据。**

## Prohibited Behaviors

- 禁改变 worker 认领与 claim-token fencing；禁立即 defer 与静态 owner 双机制并存。
- 禁非 owner 失败后静默部分交付；禁 verify 只看文件存在不看版本对应。
- 禁以 reconcile 代替正常路径，或把历史恢复操作推广成常规维护脚本。
