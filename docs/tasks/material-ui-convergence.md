# 素材理解对话面收敛——施工合同（ADR-102 后续批）

> Status: **施工完成**——compileall OK；纯 pytest 908 绿 + 在册 10 红零新增；web tsc 2 错 = HEAD 既有债零新增。live 四场景（验收节）用户自跑。

> ADR-102 把素材处理挪进「读企图 → 盖章 → 认领」的回合内前提后，对话面残留四条旧世界的车道/叙事，与用户live实测四案对齐后同批清扫。本简报只承载现行规格。

## 事故锚点（live 四案，2026-10-05）

1. **用户消息刷新后消失**：回放谓词 `historyReplay.ts:472` 按「内容 === ctx.prompt」跳过开场行，而 ctx.prompt 的回退链取到 `pendingBrief.prompt`（跨轮累积、随对话更新为最新指令）——最后一条用户消息被逐字误杀。
2. **「已理解素材 · 20s」与「看完 mp4 · 25s」两行重复**：read 帧（agent 的读取）与 per-asset beat（世界的工序）在旧世界时间分离、各叙各的；新流程把工序套叠进读取等待内部，两行成重复叙事。
3. **转写卡说谎**：上传路线（`routes/assets.py` 两处）仍「转写卡上传即出生（queued/running）」——休眠素材世界里斯什么都没在处理，卡面声称的事实不存在；弃用素材还留永久 loading 痕。
4. **法条词汇被复读**：`_asking_strategy.j2` 的 "safe to skip" 被模型直译为「跳过的话，我按……」——法条里的可复读词汇是污染源（用户拍板：做减法，不加禁令）。

## 施工四项

### ① 归档单一源（web）

消息全在 DB，刷新 = 调接口全量渲染。删三条互相绑死的车道：

| 座位 | 删什么 |
|---|---|
| `ChatDock.tsx` ~4494 | 钉顶 prop 气泡 `{prompt ? <UserBubble text={prompt} assets={openingAssets}/> : null}` |
| `ChatDock.tsx` ~2023 | `openingAssets` memo（唯一消费者 = prop 气泡） |
| `historyReplay.ts` ~472 | 跳过谓词 + `mapHistoryRows` ctx 的 `prompt` 参数（调用点同步） |

安全性（双渲窗口核查）：新项目首挂对话不存在 → 归档 fetch 早退（`if (!conv.id) return`）；刷新时 auto-send 的 server 检查命中走 rebuild 不发送。`prompt` prop 保留逻辑座位（specific_instruction / Start gate），仅失渲染职责。auto-send docstring 等引用「opening bubble renders from the prop」的注释同步核销。

### ② 转写卡认领出生（api）

| 座位 | 改动 |
|---|---|
| `app/pipeline/routes/assets.py` 两处上传路线 | 删 `stamp_transcript_node` 调用（asset node 出生保留） |
| `app/pipeline/asset_processing.py:process_asset` | claim 落座后（`db.get` 成功、处理链起跑前）补 `stamp_transcript_node` —— born running 即真实事实 |

完成/失败路径的既有 `stamp_transcript_node` 翻牌不动（幂等愈合既有行）。`assets.py`（声明式素材，带文本出生即 done）与 `graph_fill.py:921`（计划路径幂等确保）不动。docstring 的「上传即出生」叙事改写为「认领即出生」。

### ③ beat 抑制（api）

`_record_reading_beat`（`asset_processing.py:311`）落库前加谓词：**该项目会话存在 in-flight 用户回合 → 不落**。读路径恒有回合在飞（read 帧已全程覆盖等待叙事）；run 出生地路径无用户回合，beat 照常。谓词用 SQL 直查（`Message.turn_state == "in_flight"` join Conversation）——pipeline 零 `app.chat` import 的向律不变。

### ④ 法条减法（prompts）

消去法条里的可复读词汇（"skip"），改写为无示例句的结构描述：

- `_asking_strategy.j2:6` — "every question is safe to skip, and the user can always SEE that it is" → 结构律：散文收尾自带默认路径（作答恒为可选项），不命名任何动作、不给措辞示例。
- `intent_router_system.j2:21` / `:32`、`chat_intent_system.j2:7` / `:24` 的 "safe to skip / safely skip" 同律改写。

prompt 作者律：只写现行法，不带日期/事故标签。

## 验收（live，用户跑）

1. 刷新页面：开场消息与全部用户消息按归档渲染，不少一行、不重一行。
2. 上传视频但不问素材：画布只有视频卡，零转写卡、零 beat。
3. 「这个素材你看看有什么建议？」：等待期画布转写卡 running（认领即出）→ done；对话流只有「正在查看素材内容…」→「已理解素材 · Ns」一行（beat 抑制生效）。
4. ask_user 回合：散文收尾为自然默认路径表述，全文无「跳过」。

## Prohibited Behaviors

- 禁新增任何「跳过谓词」式的内容比对车道——归档渲染的唯一过滤律是形态律（dock/QA 既有分支），不新增成员。
- 禁在 prompt 里加「不要复读法条词汇」式禁令——减法 = 删掉可复读的词，不是加第二道墙。
- 禁给 beat 抑制加 stamp 来源标记列——in-flight 谓词已切开两条路，不加 schema。
- 禁动 `assets.py` 声明式素材的出生（带文本 born done 是正确形态）。
