# INTENT_COVERAGE — 意图层覆盖全景

> Status: 活跃（2026-07-30 建，随 intent-ask 迭代 1-4 + API 面收口落地后的现状；**2026-07-30 期 4 补四**：G-1/G-4/G-2 修复 + G-5/G-6 收编，见 `tasks/done/intent-ask-primitive.md` 期 4 补四）
> 单一事实源：**"用户在任意相位说任何话 → 系统走哪条路"** 的唯一登记表。
> 新增 chat 能力（skill / op / 问题形态 / 相位）时必须在本表登记；发现新缺口按 §6 格式追加。
> 机制细节不复述——task list 契约看 `CHAT_ARCHITECTURE.md`，命名看 `NAMING.md`，实施史看 `tasks/done/intent-ask-primitive.md`。

---

## 1. 通道地图（四个文本表面 × 五个入口）

| 表面 | 相位 | 用户输入去向 | 推理者 | 裁决 |
|---|---|---|---|---|
| 首页 composer | 首次 | `POST /projects/{id}/intent` | ComposerIntentAgent | 代码：reasons 推导 + pin-merge + dock task_book |
| Overlay 确认相位 | confirm | `POST /projects/{id}/intent`（累积 prompt + `turn`=本轮原文） | 同上（action 三值：generate / answer / **start**） | 同上 + start 分支复用 answer kind=start 起 run |
| Overlay 运行/答疑相位 | running / answer | `POST /chat`（project scope） | ChatIntentAgent | 代码：四态裁决（task_list / edit_ops / ask / **answer**）+ autoResume |
| ChatModal（单产物） | asset-scoped | `POST /chat`（asset scope） | ChatIntentAgent | 同上（asset 语境注入） |
| 任意 dock | — | `POST /chat/messages/{id}/answer` | **无 LLM** | 代码：kind × question-kind 契约分派 |

非文本路径（不经意图层）：dock 按钮（Start/Cancel/autonomy/选项）、面板手编任务书、retry 按钮（`/generate` 单槽 full run）、发布对话框、编辑器内操作。

---

## 2. 意图分类法（用户会说什么）

七类。示例话术以 en 为主（目标市场），zh 对照。

| 类 | 名 | 示例 |
|---|---|---|
| **G** | 生成类 | "cut 3 clips and a LinkedIn post" / "帮我处理一下这个演讲" / "再来一版，聚焦 Q&A 部分" |
| **E** | 精编类 | "把第 3 条的标题改成 X" / "trim 掉 0:12–0:18" / "字幕样式换成 bold" |
| **T** | 翻译/配音类 | "translate clip 2 into French" / "配音成德语" / "字幕加西语版" |
| **Q** | 提问类 | "你能做什么" / "还要多久" / "这条为什么这么剪" / "为什么计划里只有 3 条" |
| **C** | 控制类 | "好的开始吧" / "停下" / "撤销" / "算了不要了" |
| **M** | 元信息类 | "换个品牌模板" / "把目标语言改成法语"（改设置而非改产物） |
| **S** | 闲聊/越界 | "你好" / "今天天气如何" / 与项目无关的请求 |

---

## 3. 全分叉矩阵（相位 × 意图类 → 路由 → 现状）

状态口径：✅ 闭环 / 🚧 能走但有损（兜底接住，体验打折）/ ❌ 缺口（走错路或死路）

### 3.0 首次 composer（首页 → 创建项目）

| 意图 | 路由 | 现状 |
|---|---|---|
| G 明确（产出物+语言都说清） | /intent → plan，reasons 空 → 前端自动 Start | ✅ |
| G 模糊（"帮我处理一下"） | /intent → plan + reasons → dock 确认 | ✅ |
| Q 能力（"你能做什么"） | /intent → answer（双方落库） | ✅ |
| Q 其他 | /intent → LLM 判 generate 或 answer | ✅ |
| 空指令 | 前端本地拦截（toast） | ✅ |
| 只要 clips 但无媒体 | LLM 排除 clips；绕过则出生地 422 | ✅ |
| S 闲聊 | /intent → 大概率 answer 或默认 plan + dock | 🚧（无专门拒绝形态，靠 LLM 判断力） |

### 3.1 确认相位（任务书已 dock，未 Start）

| 意图 | 路由 | 现状 |
|---|---|---|
| G 修订 slots（"加条德语 post"） | /intent pin-merge（explicit 槽保留）→ 新任务书 dock，旧 supersede | ✅ |
| G 修订焦点/指令（"聚焦定价部分"） | 同上（specific_instruction 随累积 prompt 重推） | ✅ |
| Q 能力（"能发 TikTok 吗"） | /intent → answer 落库，任务书不被动 | ✅ |
| Q 计划（"为什么只有 3 条"） | /intent → LLM 判 answer（解释）或 plan（改成你要的数量） | ✅（LLM 判断，两可都算对） |
| **C 确认（"好的开始吧"）** | /intent → **action="start"** → 复用 answer kind=start 路径起 run，响应 `{type:"started", run_id, answered_question}` | ✅（期 4 补四；前端同 dock Start 落跑步相位） |
| C 取消 | dock Cancel 按钮 → answer kind=bail → 清 pending_intent 回 draft | ✅（按钮；文本"算了"仍无 chat 路径——低频，登记待真实投诉） |
| C 撤销自己上次修订 | 无（重说一遍反向修订 = 新修订） | 🚧（可接受：pin-merge 天然幂等） |
| E/T/M/S | /intent → LLM 折算成任务书修订（如"配德语"→ dub_languages）或 answer | 🚧（M 类改品牌/说话人在 confirm 相位靠 answer 引导；chat 相位见 §3.3 M 行） |
| 手编面板后 Start | dock Start → answer kind=start（edited intent 优先于 stored） | ✅ |

### 3.2 运行相位（run 在跑）

| 意图 | 路由 | 现状 |
|---|---|---|
| checkpoint 答题：点按钮 | /answer option → resume | ✅ |
| checkpoint 答题：打字母/序号/原文 | /chat autoResume（零 LLM）→ resume | ✅ |
| checkpoint 答题：自由文本 | freeform → resume | ✅ |
| checkpoint 弃跑 | dock bail 按钮 → 级联 skipped + COMPLETED（永不 failed） | ✅ |
| checkpoint 不答 | 过期扫描（默认 30min）→ 默认项 auto-answer + resume | ✅ |
| checkpoint 答题期间另起新题 | 新题 supersede → 级联 bail 那个 run（多 run 不搁浅） | ✅ |
| **Q 进度（"到哪了/还要多久"）** | /chat → answer 形态；`_build_context` 注入 latest run 的节点级量化摘要（kind: status — summary，≤12 行），waiting checkpoint 行天然传达"在等你" | ✅（期 4 补四 G-2） |
| **C 停止（"停下来/不要跑了"）** | /chat → 无 stop skill；checkpoint bail 只在 parked 时可用 | ❌ **缺口 G-3**（running 中无中止语义；明确先不做） |
| G 新需求（"顺便来个法语版"） | /chat → task_list（translate_clip/dub_clip/write_*）→ 新 run | ✅ |
| **Q 能力（"你能做 X 吗"）** | /chat → **answer 第四态**（N-21）：纯信息直答，不落 task、不起 run、不 dock；与 confirm 相位同待遇 | ✅（期 4 补四 G-4） |
| Q 解释（"这条为什么这么剪"） | /chat → answer 形态凭 outputs one-liner 答 | ✅（路由已闭环；深度凭 one-liner 有限，深化归 context 丰富化后续） |
| S 闲聊 | /chat → answer 形态礼貌回应 | ✅（期 4 补四 G-4 收编） |

### 3.3 完成相位（results）

| 意图 | 路由 | 现状 |
|---|---|---|
| G 整类重做（"post 重写一版"） | retry 按钮（/generate 单槽）或 chat task_list write_post | ✅ |
| G 全部重出（"换个角度再来一版"） | chat task_list 多 skill / /generate full | ✅ |
| E 精确编辑（改标题/裁剪/字幕样式/音乐/裁切比/恢复版本） | /chat → edit_ops → apply_operations（undo 免费） | ✅ |
| E 改文案内容（"开头改得更抓人"） | /chat → revise_script（或进编辑器） | ✅ |
| T 翻译字幕 / T 配音 | /chat → task_list translate_clip / dub_clip（precomputed ops 不走 edit_ops） | ✅ |
| T 去口头禅 / T 加音乐 | task_list remove_filler / add_music（确定性 tool） | ✅ |
| C 撤销 | chat 撤销按钮 / undo 端点 | ✅ |
| **C 发布（"发到 LinkedIn"）** | /chat → answer 引导文案（"产物卡的发布按钮"）；远期 publish skill 依赖 Distribution 凭据 | ✅（期 4 补四 G-5，answer 引导收编） |
| **E 纠错（"这个词译错了，应该是 X"）** | /chat → revise_script 单点修；**无法"到处都改"** | 🚧（glossary 的对话入口——未来走 dispatch 注册表，不开新通道） |
| **M 元信息（"换品牌模板/换说话人"）** | /chat → answer 导航文案（Brand template / Speakers 页面） | ✅（期 4 补四 G-6，answer 引导收编） |
| M 目标语言改 | chat task_list（translate/write 新槽）折算 | ✅（产物级正解） |
| 上传新素材 | 无 chat 路径（AssetsModal/composer） | 🚧（引导缺失但死路感低） |

### 3.4 产物会话（ChatModal，asset scope）

| 意图 | 路由 | 现状 |
|---|---|---|
| E 改稿（"改短一点"） | /chat → revise_script，target_output_id 自动注入会话 scope | ✅ |
| T 翻译/配音 | /chat → translate_clip / dub_clip | ✅ |
| E 精确编辑 | edit_ops（target 即本会话产物） | ✅ |
| Q 内容（"这段讲了什么"） | /chat → LLM 凭上下文答 | ✅ |
| Q 能力 | /chat → answer 形态（同 §3.2 G-4 修复） | ✅ |
| LLM 故障 | 兜底 revise_script（asset scope 专属降级） | ✅ |

---

## 4. 裁决与兜底层（每条路径的安全网）

按序生效，上一层失败落到下一层：

1. **autoResume（零 LLM）**：choice 待决 + /chat 文本 → 字母/序号/原文命中 → option；否则 allow_freeform → freeform；否则进入 2。task_book 待决不参与（它的答案是 dock 按钮与 /intent 修订）。
2. **ChatIntentAgent 四态**：task_list / edit_ops / ask / answer。ask 是合法输出（2-4 选项 + freeform 回落），answer 是纯信息直答（无工作请求且无歧义才可用——干活走 task_list/edit_ops，读数有歧义走 ask），永远不死路。
3. **代码裁决**：registry 校验 skill/params（SkillRejected → 一次 repair_feedback 重试 → 再败则反问）；edit ops 校验（OpRejected → 提示）；出生地校验（requires / clips-media / count 边界 → 422 或反问）。
4. **LLM 故障兜底**：MiniMaxError（含 402/429/5xx，client 边界已统一包装）→ project scope 反问文案；asset scope revise_script 兜底；/intent → 默认任务书（UI 可编可 Start，永不白屏）。
5. **幂等与竞态**：单待决不变量（新题 supersede 旧题 + 级联 bail）；answer 409（重复回答）；落库去重（/intent turn 对最新 user 行去重）；过期扫描守护式 UPDATE（用户答案永远赢）。

---

## 5. 已登记缺口（按修复性价比排序）

| # | 缺口 | 影响 | 建议修法 | 量级 |
|---|---|---|---|---|
| ~~G-1~~ | ~~确认相位文本"开始吧/可以了"被当成修订~~ | ✅ **已修（期 4 补四）**：`/intent` action 加 `"start"` 座位，复用 answer kind=start 路径，响应 `{type:"started"}` | — | — |
| ~~G-4~~ | ~~/chat 无 answer 形态~~ | ✅ **已修（期 4 补四）**：IntentProposal 第四态 `AnswerProposal`（N-21），纯信息直答落普通 assistant 消息 | — | — |
| ~~G-2~~ | ~~进度询问无节点级数据~~ | ✅ **已修（期 4 补四）**：`_build_context` 注入 latest run steps 量化摘要（`_format_step_progress`，≤12 行） | — | — |
| ~~G-5~~ | ~~发布意图在 chat 是死路~~ | ✅ **已修（期 4 补四）**：answer 引导文案（产物卡发布按钮）；远期 publish skill 仍依赖 Distribution 凭据 | — | — |
| G-3 | running 中无中止语义 | 低频（bail 已覆盖 parked 场景） | 评估是否值得 run 级 cancel（涉及级联语义；**先不做**，等真实投诉） | 大 |
| ~~G-6~~ | ~~元信息修改（品牌/说话人）无引导~~ | ✅ **已修（期 4 补四）**：answer 导航文案（Brand template / Speakers 页面） | — | — |

明确不做：chat 内上传素材（modal 已是最短路径）；chat 内改账户/计费设置（settings 页面）；G-3（见上行）。

---

## 6. 测试矩阵（e2e 覆盖对照）

| 路径 | 覆盖 |
|---|---|
| checkpoint 三答法 + bail + 过期 + 多 run 级联 | ✅ 期 4 e2e |
| autoResume 字母/序号/原文/freeform + task_book 不参与 | ✅ 期 3 e2e |
| ask 三态落库 + 单待决 supersede + 待决重建 | ✅ 期 3 e2e |
| /intent plan/answer 落库 + 去重 + 不覆盖任务书 + pin-merge | ✅ B 组 e2e |
| answer 端点 kind 契约 + 出生地 guards + count 边界 | ✅ API 面 e2e |
| ChatIntentAgent 三态实分派（task_list/edit_ops/ask 各一） | ⚠️ 期 3 部分；edit_ops 实分派无 e2e |
| translate_clip / dub_clip chat 派发 | ❌ 待补 |
| G-1 started 联合 + task_book kind=start + pending_intent 清空 + 原话去重 | ✅ 期 4 补四 e2e |
| G-4 answer 形态（能力/发布问题：无 run、无 dock、run 数不变） | ✅ 期 4 补四 e2e |
| G-2 进度询问答真实节点状态 | ✅ 期 4 补四 e2e |
| 修订/派发/ask 旧路径回归（plan 重 dock、task_list 新 run、choice dock + autoResume） | ✅ 期 4 补四 e2e |

---

## 7. 登记纪律

- 新 skill/op/问题形态落地时：更新 §2 分类（若新类）、§3 矩阵、§6 矩阵。
- 发现用户话术走错路：先登记 §5（含重现话术），再谈修。
- 本表只登记"用户→路由"映射与状态；机制怎么实现看 `CHAT_ARCHITECTURE.md`，为什么这么设计看 `tasks/done/intent-ask-primitive.md` 与各 ADR。
