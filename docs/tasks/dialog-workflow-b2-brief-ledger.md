# B2 P0 施工简报——brief 账本 + ask 一等动作 + 出书门槛（ADR-052 判词 4/5，DIALOG_WORKFLOW §4）

> Status: 待开工（简报 2026-09-03 落，排期 PROGRESS W7：09-04 day1 账本+相位统一 / 09-07 day2 ask+门槛）。前置 = B1 ✅（改名面已全栈一致）；**开工硬前提 = B1 各 commit 已验证入库**（B2 不得与未验证 B1 改动同工作区混排）。
> 本批是**行为批**（B1 零行为纪律不再适用）：prompt / 动作集 / dock 行为按蓝图定向改变；剧本 harness 断言随 commit 同步更新（形态变化是交付物，不是回归）。

## 1. 变更表（蓝图片段 → 实现物）

| 蓝图（DIALOG_WORKFLOW §4） | 实现物 | 层 |
|---|---|---|
| brief 账本槽位 topic / audience / tone / constraints[] / material_state + 任务链与 derived 原样 | `PendingBrief` schema 扩展（JSON 列内结构，**零表迁移**——列已在 B1 rename） | schemas |
| 每槽带来源 user-stated > inferred > default，代码侧合并 | 槽位值 = `{value, source}`；合并函数 `merge_brief(llm_update, stored)` 纯函数：LLM 每轮提议全量更新，代码按来源优先级落账，**user-stated 永不反向覆盖** | chat/service |
| router 相位统一（案 A 已拍板——双实例保持，§4） | 零 harness 改动；ask 形状两相位共享 = 两 prompt 各写同一策略行 + 共用 `AskProposal`（pre-run 可提问） | chat/intent |
| 动作集 ask/draft/answer/start（generate 名不副实） | `InferredIntent.action` 枚举正名 `generate → draft` + prompt 同步；SSE/wire 动作值同批换（前端消费点同 commit） | schemas + prompts + web |
| ask 一等动作（choice 2-4 + freeform，走现成 dock 提问机器，caption-mode 特例泛化） | pre-run 相位 verdict=ask → `_dock_question` 直通（复用 chat_intent ask 形状 C）；dock 答复后 autoResume 回 book path | chat/service |
| 提问策略三条（一轮一问决定槽 / 一词可答 / 散文必带默认路径） | prompt 策略行 + ask payload 恒带 `default_path` 字段（散文第二句的 schema 牙齿） | prompts + schemas |
| 出书门槛（brief 有根才 dock：主题/素材/明确配方三者其一） | `_book_turn` generate→draft 分支前置门：无根 → ask 主题（不 dock 书）；问完一轮仍无根 → draft-from-persona 书 + 默认路径声明 | chat/service |
| zero-material net / no-material lift 折叠 | `_ask_for_material_text` 安全网与 S13/S48 软信号逻辑并入门槛同一策略（出书决策只看账本，不看临时网）——两补丁删 | chat/service |
| 上下文装配（brief 主状态，累积 prompt 叙事降存档） | `_assemble_book_turn` 入参改 brief + presented_book + recent + 素材摘要（800 字不变）；`MAX_ACCUM_PROMPT_CHARS` head/tail 截断簿记退役 | chat/intent + service |

**不在本批**：任务书卡渲染（B3）；有界 loop 节点（B4）；`chat_intent_agent` 四态机的其他改动。

## 2. Commit 切分（各自自绿，剧本同步）

- **D1-C1 账本 schema + 合并机器**：`PendingBrief` 槽位 + 来源 + `merge_brief` 纯函数（单测级剧本断言：来源优先级三态矩阵）。存量行无槽位 = dev 数据可清（FK 顺序清理 memory），**零读容忍**（N-42 纪律）。
- **D1-C2 动作集正名 + ask 形状共享**：`generate → draft` 全栈（enum / prompt / SSE / 前端）+ ask 策略行进两相位 prompt（案 A：双实例零合并）。剧本动作断言同 commit。
- **D2-C1 ask 一等动作**：pre-run verdict=ask 直通 dock 提问机器 + 策略三条进 prompt + `default_path` 牙齿。剧本新座：裸愿望 → 主题问（一词可答 + 默认路径）。
- **D2-C2 出书门槛 + 折叠 + 装配切换**：门槛前置 + 两补丁删除 + `_assemble_book_turn` 换血 + `MAX_ACCUM_PROMPT_CHARS` 退役。S13/S48 断言改写随 commit。

## 3. 验收

1. **裸愿望**（"I want a social post." 无素材无主题）→ 先收到一词可答的主题问（选项带来源、散文带默认路径），**不再收到空心书**（母验收，DIALOG_WORKFLOW §7）。
2. 账本每槽带来源；构造 LLM 全量更新提议 → user-stated 槽原样存活（永不反向覆盖举证）。
3. 问完一轮仍无根 → 出 draft-from-persona 书 + 散文含默认路径声明（「直接开始我会按人设风格起草」）。
4. 每 commit：剧本 harness 全绿（更新后的断言）+ 冷启动 import 绿 + web tsc 绿（用户自跑）。
5. 09-02 任务书瘦身 echo 散文（prompts.py 在途未提交块）与本批默认路径声明方向一致——同车验收，不另开批。

## 4. 悬案④：router 两相位物理形态（**已拍板 2026-09-03 = 案 A**）

**案 A 双实例保持**（用户拍板，判词存档 DIALOG_WORKFLOW §8 已关闭条）：`intent_router`（pre-run）+ `chat_intent_agent`（post-run）各自声明，概念合一靠文档与共享 `AskProposal` schema 承载；零 harness 改动。~~案 B 单实例相位参数化~~（联合 schema 非法动作可表示 + assemble 纯度腐蚀 + 漏斗手术，bespoke 机制单用户，已否决）。

## 5. Prohibited Behaviors

- **禁 LLM 合并槽位**：合并永远代码侧（LLM proposes, code decides）；prompt 里写「请保留用户已说的值」是散文不是机制。
- **禁反向覆盖**：任何路径不得让 inferred/default 改写 user-stated（含 repair 重试与 ask 答复回填）。
- **禁第二意图入口 / 禁 ReAct**：不变量全批有效（DIALOG_WORKFLOW §6）。
- **禁空书 dock**：出书门槛无旁路；「先 dock 再说」旧路径不得保留开关。
- **禁读容忍 shim**：旧形状（无槽位 / generate 动作值）零 fallback，dev 数据可清。
- **禁顺手改卡面**：任务书卡渲染变更一律 B3（本批只动 wire 与散文牙齿字段）。
