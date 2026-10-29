# R1.1 Commercial / Distribution——PLANNED 合同

> Status: PLANNED，排期挂起。Stripe 一次性积分充值由 `stripe-credit-topup.md` 单独实施；订阅与其余启动窗口由 PROGRESS §0.3 决定。计费、支付、分发和渠道规则分别归 BILLING.md / PAYMENTS.md / DISTRIBUTION.md。本文件只保留剩余启动范围与验收，不复制旧批次状态。

## 1. 目标

用户可以 **订阅 → 使用 → 查账 → 管理套餐 → 回收冻结额度 → 发布/导出产物**。真钱接入必须以现有 fencing、幂等台账和失败不扣费为前提。

## 2. 启动范围

1. **agent_calls 台账**：记录每次 provider 调用，包括空内容、max-tokens 和校验失败首试；保存 agent/run/step/attempt/outcome/tokens/error/prompt 模板与 usage，可重建调用 envelope，大 prompt 走对象存储。动工时补 ADR。
2. **订阅**：支付商沙盒、订阅 webhook、续费/升级/取消、周期额度与订阅权益；一次性积分充值不在本文件重复登记。
3. **权益执行**：额度检查、超限提示、周期重置；用户余额不足与 provider 402 严格分开。
4. **用户计费中心**：用量、明细、套餐与余额的同一事实投影。
5. **渠道联调**：LinkedIn/TikTok OAuth、发布成功/失败/授权过期通知；平台凭据未到位时用 mock 验收并保留真联调清单。
6. **已发布产物删除边界**：删除已发布产物返回 409 与人话原因，不静默抹除发布史；保持 FK-safe 删除顺序。
7. **Hold GC 联动**：按 `r1-1-batch-4b-hold-gc.md` 验证冻结额度回收。

## 3. 外部依赖与不变边界

- 支付商入驻、公司主体、LinkedIn/TikTok 开发者权限是外部前置，不得伪称已完成。
- `_mutate` 双层 dedupe、idempotency key、fencing 与 run authority 不变。
- 机构审核、metrics 回流、定时发布 UI、newsletter 仍按 DISTRIBUTION 的延期边界，不随本批自动扩入。
- ExecutionAttempt 仍由证据门决定；agent_calls 不自动等于新执行模型。

## 4. 验收

- 沙盒/mock 完成订阅 → 使用 → 查账 → 管理套餐全链，真实支付联调单独核对 webhook 重放与幂等。
- 每笔消费可由计费中心和 agent_calls 追溯；余额、hold、capture、release、purchase 不双算。
- 渠道凭据到位后完成真实发布；未到位时明确列出未验证项，不把 mock 写成平台验收。
- 删除已发布产物为 409；失败发布与授权过期有真实通知。
- Hold GC 场景闭合，既有付费边界、失败不扣费与双平台适配不回归。
