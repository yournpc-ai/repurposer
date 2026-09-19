# Verification Contracts — Registry

> Phase 2.5（Verification Contract Migration）产物：Tests / Scripts / Harness =
> 当前 Architecture Contract + Product Contract 的 executable specification。
> 本文档是验证侧合同登记表：合同条目（Owner / Source ADR / Test / Scripts /
> Status）与已知方差（Known Variance）的单一事实源。
>
> Status: **骨架（Batch B-4 立）**——当前只装剧本 fixture 律；合同条目全表与
> Known Variance 登记表随 Batch C 补齐。

## 剧本 fixture 律（Batch B-4，强制）

**每个 Scenario 必须显式声明被测资产（fixture）的 processing / material /
failure state；测试前置条件永不由 background worker 的 timing / race 决定。**

机理：`seed_asset` 的默认态是 `PENDING` + 虚构 `scenario/*` 字节——常驻
worker 的 `claim_pending_asset`（只认领 `PENDING`，`FOR UPDATE SKIP LOCKED`）
会认领它、HeadObject 404、把行翻成 `FAILED`。剧本跑到一半，LLM 的 ground
truth 从「处理中」变成「处理失败」——前置条件被 worker 调度决定，断言沦为
轮盘赌。

合法的声明形态（按被测意图选，三者互斥）：

| 被测意图 | 声明 | worker 行为 |
|:---|:---|:---|
| 素材已就绪（内容与语言事实在场） | `processed=True` + `extracted_text` + `meta={"language": …}`（S20B 形） | 从不认领（COMPLETED 不可认领） |
| 素材未就绪 | `status=AssetStatus.PROCESSING`（S20A 形） | 从不认领（只认领 PENDING）；lifecycle 归并入 `material_pending` |
| 处理失败 | `status=AssetStatus.FAILED`（S16-P2 形） | 从不认领；lifecycle 读 `material_failed` |
| 真实处理（字节真实存在） | `file_url=<真实 bucket key>` + 默认 PENDING（S16 形） | 认领并真处理——此时 race 本身就是被测对象 |

禁止：默认值裸奔（不声明任何态的 `seed_asset(...)`）。fixture intent 必须
独立于 worker scheduling。

已硬化：S5 / S7(A/B/C) / S10 / S20A。S16 的 PENDING 是「真实处理」行的
合法实例（字节真实存在）。迁移中对齐此律的历史剧本在改动时顺手登记于此。
