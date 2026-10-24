# R1.1 Hold GC——PLANNED 合同

> Status: PLANNED，随 Commercial / Distribution 排期；不阻塞当前 Film 主线。计费语义归 BILLING.md，优先级只读 PROGRESS §0.3。

## 1. 目标与边界

回收“已具备执行资格却长期无人认领”的 PENDING run 所冻结的额度，使用户余额与台账最终闭合。合法等待素材、依赖未完成、RUNNING、WAITING_HUMAN 和新生 run 永不被 GC。

第一交付物是**资格丧失谓词**，不是拍一个 timeout。PENDING 同时可能表示未启动、待 worker 或等素材，不能按 `created_at + age` 粗扫。

## 2. 实施合同

1. **共享谓词**：从 worker claim 的同一份项目资产门控抽取定义。GC 候选 = run PENDING ∧ 项目无 PENDING/PROCESSING 素材 ∧ `updated_at` 超龄，即 runnable-but-unclaimed；claim 与 GC 漂移应由纯测试拒绝。
2. **回收路径**：候选经既有 finalize FAILED 路径，再调 `release_run`；重复 sweep 幂等。只处理 PENDING，绝不改变 RUNNING / WAITING_HUMAN。
3. **计费边界**：`_mutate` 双层 dedupe、idempotency key 与 hold→capture→release 不变；不得另写余额修补。
4. **前置**：asset 失败终态必须能解除 claim 依赖门，否则“素材已 settled”不成立。执行计数与 fencing 语义不重做。
5. **节奏**：复用 worker tick，不另建 backoff 或调度系统。

## 3. 验收

- claim/GC 谓词镜像一致性纯测试通过。
- 超龄且可执行的 PENDING hold 被 release，台账 hold+release 闭合，重复 sweep 不重复写账。
- ASR 在途、依赖未完成、新生 run 零误杀；RUNNING / WAITING_HUMAN 零状态变化。
- 当前付费边界旅程覆盖“冻结 → 回收 → 余额恢复”，失败不扣费与既有执行权规则不回归。
- 完成后把当前语义写入 BILLING 与 North Star，并更新 PROGRESS；不保留批次施工记录。
