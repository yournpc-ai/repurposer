# Transcript 数组与言语座位——剩余验收合同

> Status: 代码层已落；prompt_gate、当前矩阵、目标环境迁移与真实回放仍开放。长期规则归 ADR-108/109/110 与 CHAT_ARCHITECTURE §8；本文只保留迁移、验证和未决差异。

## 1. 当前承重规则

- 每个 conversation 的 `messages.seq` 单调分配；持久化数组顺序就是渲染顺序。append/open 定位置，update-in-place 改状态，live 与 replay 共用 reducer 语义；不得再用时间戳交织或锚点推导重排。
- seq 允许有间隙，不要求永久连续。**首回合事务例外**：conversation 在当前未提交事务内出生时，第一条消息的 seq 必须在该事务内分配；后续分配回到专用计数器的独立短事务。
- checkpoint 适用于有散文且参数合法的非终态调用，在 post-validation / pre-execute 发射；cap 4 只是节奏护栏，不是资格白名单。checkpoint 是 earned，不是配额；纯回答可以结构性为零。
- 零 delta 散文只能在信封到达后追加，再经 typewriter 排干，数组位置不变；iteration≥1 的非流式结果只经 checkpoint/settle 出站。
- WorkSegment 负责当前聚合。failed 行保留诚实告警；cancelled 行留作审计数据但从可见投影退役，不生成空 Worked 行。
- echo 只能指向当前真实可见的面；plan-ready reveal 与 chat-only 布局按现行画布规则处理。

## 2. 未决形态差异

ADR-108 的“每个可见元素都是数组行”与当前 `candidates_log` 聚合行例外尚未统一。当前传输是 `assistant.candidates` SSE 帧族；turn settle 后把本回合 events 合写成一行 `intent.type="candidates_log"`，由 `historyReplay` 折叠成候选卡、原位更新同集并重绘选择。需要明确 adjudication：聚合行是数组合约的正式例外，还是应改成更细的持久行；不得静默写成豁免，也不得为数组化拆坏单卡 repaint 或制造空 selection 行。该决定不新增候选查询端点。

验收时必须覆盖 set、同集幂等重发、纯 selection、revise 替换、失败回合零持久化、answer-turn 六类载荷，核对：live/replay 的数组位置一致；候选卡与前后散文/Activity/WorkSegment 的相对顺序一致；selection-only 不产生空行；失败回合客户端回滚与服务端记录一致；跨回合 replay 后仍能重选。若改持久形状，先保留旧 `candidates_log` 读容忍，再更新 ADR-108、CHAT §8.9 与本合同。

trigger `/event/sync` 回合目前不产 Activity 行，作为 parity 观察保留；它不是自动授权的新实施项，需先确认是否影响当前用户旅程。

## 3. 迁移与回放验收

1. 在目标环境先 dry-run `migrate_activity_log_rows.py`，确认目标与影响，再获授权执行；验证计数器对齐、真实迁移后回放和首回合/后续回合两种 seq 分配路径。生产验证前不得删除迁移脚本。
2. 在项目 `3e333147-35e0-41ea-8c80-828d41c71893` 重跑“竖屏切片”形态：读前散文先于读行；硬刷新/切 tab 后逐行一致；WorkSegment 可展开。
3. failed 行刷新后仍诚实可见；cancelled 行只留审计，不出现在可见投影，也不产生空 Worked。
4. 新 conversation 首回合与后续回合分别验证 seq 分配、计数器对齐和 FK 安全。
5. 按 §2 的六类 Candidate 载荷验证聚合行位置、幂等、失败回滚与 answer-turn parity；先完成“正式例外还是改形”的裁决，再把结论写回 ADR/CHAT，不能仅以页面看起来一致关闭。

## 4. Checkpoint 五类路由覆盖

将以下检查归属当前承重纯函数套件，并保留 `tool_loop_checkpoint` / `tool_loop_checkpoint_capped` 计数读数：

1. 非终态 + 非空散文 + 合法参数 + 有 checkpoint channel：post-validation / pre-execute 发射，execute 不重复携带该段。
2. 终态调用：散文只走 settled envelope，永不走 checkpoint。
3. 参数校验拒绝：不发射 checkpoint，不执行工具，不留下 dock/言语残片。
4. 无 checkpoint channel 的一次性路径：散文保留在 ledger，最终 envelope 不丢字、不重复。
5. cap 已达：不再发射，记录 capped 计数，被截散文不合并回 ledger 造成延迟复读。

单读直出可以结构性零 checkpoint；只有实测系统性漏发“新且与用户理解相关”的 earned checkpoints 才重审路由，不能为追求计数放宽资格。

## 5. 完成条件

当前纯 pytest、prompt_gate、当前注册矩阵、适用 web 检查与上述迁移/live 验收完成后，更新 PROGRESS 并删除本合同。旧测试计数、事故叙述和退役剧本不构成完成证据。
