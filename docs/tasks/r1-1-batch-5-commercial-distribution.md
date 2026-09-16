# R1.1 Batch 5 — Commercial / Distribution（W11 商业化闭环）

> Status: PLANNED（2026-09-16 建；属 R1.1，**不阻塞 R1**；排期唯一事实源 = `docs/PROGRESS.md` §0.3，本文件只是施工合同）
> 范围母文档：`docs/PROGRESS.md` 第十一周节 + `docs/BILLING.md` + `docs/DISTRIBUTION.md`——本文件只做批次合同与验收口径，不复述三份母文档的设计。
> **本批开工前应把下列 T1–T6 按当时代码现状重新展开为细化简报**（届时行号以 current HEAD 重新核验）。

## 1. Product goal

用户可以：**订阅 → 使用 → 查账 → 管理套餐 → 回收冻结额度（Batch 4b）→ 发布/导出产物**。

为什么排在 R1 之后：收费的诚实前提 = R1 Batch 2（双扣路径封死再接真钱）；R1.1 吸收外部不确定性（平台凭据/审批），不作为 R1 的结束条件。

## 2. Current state（核验于 e8dbced）

- 积分真账本已闭环：wallets / credit_transactions / hold→capture→release / 失败不扣费 / 出生地 422 / 三面展示（`docs/BILLING.md`，ADR-055，S13–S15 剧本绿）。
- Distribution 工程完成：双平台 adapter / OAuth（Fernet token 加密，ADR-031）/ REST 路由 / worker 第四认领源（`app/worker.py:60-63`）/ 发布对话框 + 通知中心 + Settings Channels（`docs/DISTRIBUTION.md` 头部状态行）。**待办 = 平台应用凭据联调（外部依赖）。**
- 已登记缺口：删除「已发布产物」应 409（`ARCHITECTURE_GATE_2_REPORT.md` §8 末 + §16-4——`publications.output_id` FK RESTRICT，删除会炸；Batch 2 已镜像 FK-safe 顺序保证不炸，409 用户语义归本批）。
- agent_calls 台账未建（PROGRESS 需求池 P1 行：现状只记钱 cost，修复一轮不留痕；挂本批成本校准闭环做前置）。

## 3. Gap

支付商接入 / 订阅生命周期 / 套餐权益执行 / 用户计费中心 / 发布联调 / 已发布产物删除语义 / 调用台账。

## 4. Files / modules

届时按母文档展开；已知区域：billing 支付边界（`app/platform/`）、订阅与 webhook 路由、计费中心 API + 前端页、`app/distribution/`、`app/pipeline/routes/outputs.py`（409 守卫）、`app/agents/` 调用装配层（台账捕获点）。

## 5. Preconditions

- R1 完成（**硬前置 = Batch 2**）；Batch 4b 钉在本批「资金可用性」验收场景上。
- 外部：支付商沙盒 / LinkedIn·TikTok 开发者权限——**不得阻塞本地代码验收**：未到位走 mock 验收 + 真联调排队清单。

## 6. Implementation tasks（合同骨架，开工时展开）

- T1 **agent_calls 台账**（批内前置，成本校准闭环的地基）：每次 provider 调用（含空内容/max-tokens/校验失败首试）落库——agent 名 / run+step / attempt / outcome∈ok·repaired·failed·empty·max-tokens / tokens / 错误类 / prompt 模板名；调用 envelope 可重建（大 prompt 走对象存储 spill）。schema 以 PROGRESS 需求池「agent 调用台账」行为需求源，动工时补 ADR。
- T2 支付接入 + 沙盒订阅。
- T3 订阅生命周期（续费/升级/取消 + webhook）。
- T4 套餐权益执行（额度检查/超限提示/周期重置；用户级余额不足入流灰行 vs provider 额度两词分开）。
- T5 用户计费中心（用量/明细/套餐页入口）。
- T6 LinkedIn/TikTok OAuth 联调 + 发布验收（成功/失败/授权过期进通知中心）+ **已发布产物 delete = 409**（不静默抹发布史；FK-safe 顺序已在，补用户语义守卫）。

## 7. Do NOT touch

- `_mutate` 双层 dedupe / idem key 机制。
- 机构审核 / metrics 回流 / 定时发布 UI / newsletter（DISTRIBUTION 已定界 P2）。
- ExecutionAttempt（台账若满足查询需求，Attempt 论据进一步减弱——保持证据门禁）。
- R1 已冻结的 fencing / run authority 语义。

## 8. Acceptance

- [ ] 订阅 → 使用 → 查账 → 管理套餐全链（沙盒/mock 可过）
- [ ] 每笔消费有据可查（计费中心 + 台账）
- [ ] 发布双平台：凭据到位 = 真联调验收；未到位 = mock 验收 + 排队清单显式记录
- [ ] 删除已发布产物 → 409 + 人话
- [ ] 额度回收场景（Batch 4b 联动）闭合

### R1.1 Definition of Done

用户可以 subscribe → use → see billing → manage entitlement → recover held credits → publish/export。**R1.1 之后 = 运营端（W8–W10，PROGRESS 既有排期），不在本里程碑内膨胀。**

## 9. Docs update（完成后同批）

- `docs/PROGRESS.md` §0.3：B5 → DONE + commit；第十一周节状态同步。
- `docs/BILLING.md` / `docs/DISTRIBUTION.md`：支付/联调落地状态。
- 台账 ADR（动工时补）。
- 本文件 Status → DONE。
