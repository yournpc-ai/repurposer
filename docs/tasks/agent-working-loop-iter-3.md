# Agent Working Loop——持续工作闭环剩余合同

> Status: 代码层已落，live 验收与 `edit_graph` 退役证明未完成。现行架构归 ADR-088/089/117/139 与 CHAT_ARCHITECTURE；本文只保留剩余验收、迁移门和开放冲突，不记录迭代施工过程。验证使用当前注册的旅程矩阵，不恢复已退役剧本。

## 1. 当前承重行为

- **同一 Decision Package 持续编辑**：确认前修改原地更新同一确认座，重编译受影响 scope 并刷新 quote；不得实现成“确认失效，再弹一个确认”。只有呈现且授权的付费范围才能执行；auto 不创造制作意图，守卫线与 NULL 不可报价族仍须带价确认。
- **方案身份**：快照保存 `plan_task_map`；`compiled` / `superseded` 写入与读面过滤成对存在。缺失或 legacy 映射诚实降级到 `@output`，不得靠位置猜测修订目标。
- **选择修订**：`revise_selects` 保留 member-index 编辑、bounds 重校验、verdict/reason 重述、幂等、一调用一 journey、settled 闭态和 replay 零写。dock 前/后未确认与 run 后的授权路径分别按当前 scope 与设置处理。
- **产物修订**：`revise_output` 仅在 chat path，目标为 `plan_ref` 或 `output_id`；只改 prompt-consuming nodes，确定族或部分覆盖必须如实披露。单产物精确 clip-spec 修改仍走 `edit_output`，不混为自然语言 craft 修订。
- **范围裁决**：scope classifier 唯一判定 continuation / expansion / unproven；unproven 失败闭，run 后变化仍走 ADR-117/139 的呈现与授权路径。
- **确定性 run review**：`run_review` 只对比 confirmed scope、实际产物、质检与台账事实；不作主观质量判断，不自治续做。
- **Memory 三个窄机制**：租户安全且有界的 `get_artifact`、最多三条最新历史摘要、仅供参考的 exemplar 事实行。不得合并成新 domain object，也不得静默写偏好；若以后实现偏好升格，必须另行获得用户显式授权。
- **Activity**：只增加用户安全的 `at` / `duration_ms`；raw payload、result、reasoning 永不上 wire。持久化数组顺序与 WorkSegment 聚合规则归 ADR-108～110 和 CHAT §8，不恢复时间戳重排。

## 2. 剩余验收

用当前注册的矩阵、相关纯测试、prompt_gate 与 web 检查完成自动回归，再做一次真实六段走查：

1. **直接工作**：模糊目标与素材进入正确读取/探索，不暴露 runtime 词汇。
2. **过程可见**：活动按持久化数组位置与 WorkSegment 呈现，live/刷新顺序一致；无第二条 Thinking、时间戳重排或假展开。
3. **确认前修订**：换选/改方案原地更新同一 Decision Package，受影响 scope 与报价同步刷新，没有第二个确认座。
4. **授权执行**：分别覆盖 continuation、expansion、unproven，以及 auto/ask、无制作意图和费用守卫线；旧确认不得授权新范围。
5. **完成与失败**：核对 run_review 的事实清单、failed/partial/delivered 分支、真实产物卡与费用事实。主观质量判断仍禁止。
6. **持续修订与记忆**：plan_ref / @output 精确命中，legacy 诚实降级；确定族与部分覆盖说明真实；post-run 新发现开新 journey；exemplar 只作参考；历史摘要有界。
7. **CJK 长素材检索**：`search_cues` 的子串匹配对按单字 token 化的中文可能大量 miss。统一 normalization 后，用真实中文长素材验证定位、派生 excerpt 与后续候选 range；未完成前不得宣称长素材搜索对 CJK 可靠。
8. **探索存储迁移**：在含 legacy 探索行的真实目标 DB 副本上验证 upgrade/downgrade、备份/回退、读面过滤、编译与 replay；`exploration_rows` 不得出现在执行闭包、报价、rank 或媒体流边。零双写与旧行不回流都要取证。
9. **Candidate Surface live/replay**：chat-born 候选卡默认三条推荐并可受控展开；ordinal/time/excerpt/speaker 事实、选择高亮、重选替换而非并集、失败回合回滚、跨轮 replay 与回答回合一致。`candidates_log` 的数组形态差异归 `transcript-array-and-speech-seats.md`，本项不新增查询端点。

第 1～6 段使用一份 **≥60 秒、两个主题的真实源素材**：分别在 dock 前、dock 后和 run 后换选，核对同一 Decision Package 的 quote 刷新；覆盖 continuation/expansion/unproven × auto/ask、plan_ref 与 @output 指认、legacy 降级、delivered/partial/failed 事实收官与有界 reference-only memory。任何 instant prose、假成功、重复 WorkSegment、内部 UUID/wiring 泄漏或未经授权 hold/capture 都是红灯。不要恢复退役剧本或“恰好一次确认”的旧期望。

第 5 段按 ADR-135/141 的现行分支验收：`run_completed` 只叙述确定性 delivered/partial 事实，不强制建议 pills 或默认下一步；全败 `run_failed` 的原因与至多两个可行选项按失败合同验收。

## 3. `edit_graph` 退役门

只有以下证据全部存在才可删除：

1. 七类话术到现行工具的覆盖映射完成，无未承接的合法路径；结构手术若仍无产品座位，须明确为设计缺席而非静默拒绝。
2. 当前完整旅程矩阵与迁移无回归证据通过，六段 live 走查完成。
3. 生产引用与存量数据暴露面清点完成，legacy 路径有明确读/迁移结论。
4. 删除控制在一个小提交；删除后做零生产引用 grep，并复跑受影响门禁。

未达标时保留现状，不为了“完成迁移”扩大范围。`propose_tasks` / `select_clips` 的退役属于 PROGRESS 的零探索退化项，不与本门混成同一批。

## 4. 验收边界

- 旧确定性驱动、旧测试计数和逐拍交付记录不是当前证据；未运行的检查写“未运行”。
- 不恢复 S-int / S-explore / S-wait 等退役事故剧本；新覆盖必须归属当前旅程矩阵或承重纯函数守卫。
- live 验证需要活 API、dev worker 和模型配额；付费验证另行授权。
