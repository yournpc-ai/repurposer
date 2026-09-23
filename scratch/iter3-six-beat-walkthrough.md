# iter-3 六拍 live 走查（用户验收脚本）

> 用途：迭代三「Agent Working Loop」终态验收。代码层门禁已绿（Claude 跑：
> 纯 pytest 625 / check_gates OK / web tsc 无错 / vitest 70）；**LLM 拍位与
> 六拍体感由本文件驱动用户自跑**（2026-09-23 拍板：本批不做全量回归与门
> 测试，用户迭代完成后自测反馈）。
>
> 前置纪律：
> - 先杀旧栈再起栈（dev.sh 家族杀）：常驻 worker 会抢跑手工 run。
> - `./dev.sh` 起全栈（API 8000 + worker + indexer + web）。
> - fixture 纪律：测试项目/素材用 `scenario/` 前缀命名，永不共享 demo key；
>   走查完删项目（页面删除即可，级联干净）。
> - 双语言面各过一遍拍 2/5 更好（活动行/兑现叙事都走 i18n）。

## 0. 门禁（先跑硬的，再跑体感）

```bash
# 0.1 prompt 面门禁（S4/S6 触过 intent_router/chat_intent；S5 触过 trigger_system）
cd apps/api && uv run python scripts/prompt_gate.py
# 期望：全探针 PASS（阈值见 ADR-071；漂移先复跑一次，再二分，永不调阈值）

# 0.2 三座常驻剧本的确定性尾（对活 API，LLM 拍位不在其内）
uv run python ../../scratch/s_explore_3_deterministic_drive.py   # 拍 6 修订回路：R20 路由 + R19 装配 + 写门
uv run python ../../scratch/s_explore_4_deterministic_drive.py   # 拍 3 插话换选：门分支 + 三金钱态机械
uv run python ../../scratch/s_explore_5_deterministic_drive.py   # 拍 5 收官 reviewer：兑现事实清单 + 缺口裁决

# 0.3 受影响旧座回归（串行，不与 gate 并发）
uv run python scripts/chat_scenarios.py --only S-explore-2,S23,S4,S7,S13,S16,S19,S22
```

## 1. 六拍逐拍走查

场景素材：一段 ≥60s 的讲话视频（含至少两个话题段，如定价 + roadmap）。

### 拍 1 直接开干
- 操作：新项目 → 上传视频 → 发「帮我找最好的定价讨论片段，剪成竖屏短片」。
- 预期：agent 产品语言复述 + 立即开工（不连问参数）；activity 流行行落下
  （「正在读素材…」类），散文打字机节奏（**整段瞬移 = 红**）。

### 拍 2 过程可见（S7 面）
- 预期：候选合集卡 → 精选卡 → 方案卡依次落画布；消息流里 activity 行与散文
  **按真实时刻穿插**（不再是一块固定底块）；完成行右侧带耗时耳语（如 `3s`）；
  里程碑行（Found N candidate sections / Picked N sections / Structured N plans）
  可展开（展开 = 全文案行 + 计数 + 耗时，无候选内容复制）；普通读行无展开 affordance。
- 回归不动项：thinking 行在散文流动时隐藏、排干才回；dock 三态形态不变。

### 拍 3 中途插话免费秒改（S4 三金钱态）
- dock 前（方案未呈现）：发「第 1 个换成讲 roadmap 的那段」→ 精选卡原地更新，
  零确认零报价仪式；方案自动跟随。
- dock 后未确认（拍 4 的包已在桌上）：再发一次换选 → **同一个确认座**原地更新
  （新价随行），不弹第二次确认。
- run 后（拍 5 完成后）：再换选 → 受影响方案 supersede-继任 + **迷你决策包**
  （只含变化）重确认。
- 证据面：精选卡 verdict/reason 跟着新选段走（LLM 重述，永不沿用旧的）。

### 拍 4 只在渲染前停一次
- 预期：决策包 dock = 方案层（LLM 命名）+ 编译证据层 + 费用语义；确认 pill 在
  dock 底排（三形态同座）；确认后才出生 run——确认前零付费。

### 拍 5 收官自检汇报（S5 reviewer）
- 操作：等 run 完成，读触发回合的收官散文。
- 预期：逐条讲**兑现事实**（落了什么类型/语言、clip 时长 vs 裁切区间、字幕轨/
  配音存在性、实扣 vs 报价区间）；**零主观质量词**（「great / polished / 惊艳 /
  效果不错」出现 = 红）；有缺口（承诺没落地的）诚实一句 + 建议 pills 出口；
  `needs_human` 质检旗平述（「值得你看一眼」），不软化。
- 人为造缺口对照（可选）：让一个 writer 步骤失败，收官应出现 GAP 叙事而非
  笼统「做好了」。

### 拍 6 一句话修订零仪式（S3 + S1 快照路由）
- 信封内（continuation）：「第二条 post 语气更锐利」→ 零仪式直接修直接跑，
  无新确认；卡面 prompt 可见修订条款追加（诚实面）。
- 新钱（expansion）：「再加一条法语 article」→ **迷你决策包**重确认（只含变化
  子图 + 价差），确认才跑。
- 指认双通道：序位词「第 2 个方案…」与 @output 钉产物都路由到正确节点集；
  legacy 旧 run（无快照）诚实降级引导用 @。

### 记忆面（拍 10，S6 三窄切）
- 同项目第二个目标：发「再找一组，照上次的样子」→ agent 能看到「Past
  journeys」事实行并**引用**上次方案规格（语言/字幕/画幅/配音）；参考是
  reference-only——用户没点名相似时不得静默套用上次参数。
- 修订前读卡：换选/改方案时 activity 出现「正在读卡片的详情…」（get_artifact）。

## 2.  reds（任一命中 = 不验收）

- 散文整段瞬移 / 收官出现主观质量词 / 承诺未落地却说「做好了」
- 换选后出现第二次确认弹窗（dock 后未确认态）/ run 后换选没有迷你包直接跑
- activity 固定底块回归（行不随时刻穿插）/ 无载荷行出现展开 affordance
- agent 散文/回声漏出 UUID、wiring op、task 工具名等执行世界词汇
- 确认前发生任何扣费（hold/capture 先于确认拍）

## 3. 验收通过后的一步

- 简报归档：`git mv docs/tasks/agent-working-loop-iter-3.md docs/archive/tasks-done/`
  + `docs/README.md` 索引同行迁移（归档前把 Status 行翻为「六拍全顺（live 走查
  证据齐）」）。
- edit_graph 退役执行：按简报 §4 S8 施工记录的机械削除清单一个小提交
  （退役扳机 = 本走查 + 全量剧本绿）。
