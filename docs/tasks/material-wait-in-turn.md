# 素材理解 = 回合内前提条件——施工合同（ADR-102）

> 目标：「素材处理中提问」从四层机器（等待上限 + 地板 + 接力 + 防复读）变为「等终态 + 一个答案」。worker 事件的唯一创建点 = 模型的读企图；上传/寒暄/围观恒零处理。
>
> 本简报只承载现行规格。历史弧（ADR-101 的 W1/W2 与其后 live 修补）在 git。

## 目标形态（UI 规格）

```
send → 直达 LLM 装配（零素材检查）
  → 模型需要素材，调 get_understanding
      → 未就绪 + provider 不具备音轨理解
      → 【此刻才】盖章 processing_requested_at → worker 认领 → ASR
      → 帧 open「正在查看视频内容…」（全程 active + 心跳保活）
      → 工具内等终态（无时间上限；全失败提前出）
      → 观察只有两种：内容 / 失败事实
  → 就绪 → 组装 context（转写文本 + 历史）→ LLM → 打字机真答案
  →「已理解素材 · Ns」（真实时长）/「素材没能读出来」（失败）
```

- 寒暄 / 能力问 / 聊别的：模型不调用 → **零 worker 事件、零处理**。
- 开工入口兜底盖章（生产链前提，与对话无关）。
- 后续回合 digest 命中 → 零等待。

## A. 死亡清单

### A1. 接力 / review 素材路径
| 位置 | 死什么 |
|---|---|
| `app/pipeline/trigger_events.py` | `TRIGGER_UNDERSTANDING` 常量 + whitelist 成员（RUN_COMPLETED / CRAFT_DECOMPILED 保留） |
| `app/pipeline/node_runners.py` | `warm_understanding()` 的 `fire_trigger` 调用（warm 本体保留 = digest 缓存） |
| `app/chat/trigger_turn.py` | `TRIGGER_UNDERSTANDING` 分支、`_already_spoke`、`_wrap_up_rejection` 素材段；`_TRIGGER_DEFER_*` 礼貌窗若只服务素材则连删 |
| `app/chat/warmup.py` | understanding 启动补射 |
| `app/prompts/chat/trigger_system.j2` | understanding_warmed 段落 |
| `app/chat/prompts.py` | 目录注释核销 |

### A2. 回合内有界等待机
| 位置 | 死什么 |
|---|---|
| `app/chat/perception/executes.py` | `material_wait_verdict` 三态判词 / cap 轮询循环 / `_unready_text` + `_CONSTRAINT_TAIL` / outcome 三元组——pending 语义整个消失 |
| `app/platform/configs.py` | `chat.material_wait_secs` 配置项 |
| `app/prompts/chat/_material_wait.j2` | 整文件删除 |
| `_capability_answer.j2` | SCOPE 前置段 |
| `intent_router_system.j2` / `chat_intent_system.j2` | 素材待命行核销 |
| `_read_tools.j2` | get_understanding 描述重写（新语义：就绪才返回） |

### A3. consumed 戳 / 复读禁止律
| 位置 | 死什么 |
|---|---|
| `app/chat/service.py` | `intent.consumed_understanding` 戳（`interaction_policy_version` 戳保留——ADR-099 机器，与承诺机器无关） |
| `app/chat/perception/__init__.py` | `consumed_sink` 参数与写戳调用 |

### A4. 结果派生帧链
| 位置 | 死什么 |
|---|---|
| `app/chat/activity.py` | `report_read_outcome` / `_read_outcomes` / `UNDERSTANDING_*` 常量族 / `_done_key` 实例化——回朴素 read span |
| `service.py` / `plan_turn.py` / `propose_turn.py` / `routes.py` | `on_read_outcome` 全签名与 forward 点 / `activity_sink` / `_make_read_outcome_hook` |
| i18n ×2 | `understandingPending` 删；active = 「正在查看视频内容…」；failed = 「素材没能读出来」 |

### A5. 测试 / 脚手架 / 保留项
| 位置 | 处置 |
|---|---|
| `tests/test_material_wait_pure.py` | 重写为新闸门锁（见 C） |
| `tests/test_activity_pure.py` | outcome 锁删 |
| `scratch/replay_material_wait_turn.py` | 删（replay 方法论在 CLAUDE.md，不依附脚本） |
| `scratch/m3_video_spike.py` / `m3_video_transcribe_probe.py` | 保留（spike 证据） |
| `ActivityRow` 未知键兜底分态（active→Thinking / settled→Done） | **保留**（正罗宾性修复） |

## B. 新建（四件）

1. **能力声明**：`ProviderCapabilities.understands_video_audio: bool = False`（base.py 声明位，ADR-077 判词④）；M3 = False。
2. **休眠素材**：`Asset.processing_requested_at` 可空时间戳（命名律：可空时间戳替布尔）；上传 NULL；`claim_pending_asset` 加非空条件；Alembic 迁移入 `migrations/versions/`。
3. **工具级终态等待**：`get_understanding` pending 分支 = 盖章 → 帧 open → 轮询到终态（H7 独立短事务先例，无 cap，全失败提前出）→ 观察 = 内容 / 失败事实。
4. **帧与保活**：active「正在查看视频内容…」/ done「已理解素材 · Ns」/ failed「素材没能读出来」；等待期帧心跳（现有帧机制复用）。

## C. 施工批次

| 批 | 内容 | 验证 |
|---|---|---|
| B0 拆旧 ✅ | A1-A5 全删 | 纯 pytest：908 绿 + 在册 10 红（HEAD 基线 11 红零假设实证，本批修 1 新增 0——`test_no_pipeline_to_chat_import` 随 `understanding_opening_missing` 删除转绿） |
| B1 建新 ✅ | B1-B4 + 帧文案 + 测试三锁（能力闸判词：deaf→盖章+等待 / capable→直通；终态判词：ready/failed；失败观察锁） | 纯 pytest 同上 |
| B2 落档 ✅ | CHAT_ARCH（素材待命节改写 + trigger「家」收窄两事件）/ README / PROGRESS 同批；NAMING 核查 = 零命中（material_pending 从未入词表）；附带前端清扫（ChatDock trailing window A / now-line 空档相位 / `trigger.understanding_window_secs` 配置链整拆）+ harness 改靶（S-wait-1/2 重写、S18/S19/S20A/S22/S24/S-int-11 骑 craft_decompiled 或 FAILED fixture） | web tsc（2 错 = HEAD 既有债，零假设实证） |
| B3 验收 | prompt_gate → chat_scenarios 全量 → live 三场景 | 用户跑 |

## 验收（live 三场景）

1. 寒暄 / 能力问 → 秒回，**零 worker 事件**（队列空）。
2. 视频 +「看看有什么建议」→「正在查看视频内容…」→ ASR 实际时长 →「已理解素材 · Ns」→ 同回合 grounded 真建议。
3. 追问同素材 → digest 命中，零等待。

## 承重观察（在册不处理）

- ASR 加速旋钮（GPU / 云 ASR）= 运营层另案；spike 证据在 `scratch/m3_video_spike.py`（火山/Groq 对照未跑）。
- 对话阶段模型理解 = 语义级无时间码；「把第 2 分钟剪出来」由开工后 ASR 时间码校准。
- 本地 whisper 的词级时间戳继续服务生产链；云 ASR 若日后引入且时间戳够格，再评一次解析两用。

## Prohibited Behaviors

- 禁在 send / 上传 / 任何入口预盖章——worker 事件唯一创建点 = `get_understanding` 的读企图（开工兜底除外）。
- 禁给等待加任何时间上限 / cap / 超时地板——终态只有 ready / failed。
- 禁任何形式的第二 writer（接力 / review / 「我看了」主动开口）。
- 禁 prompt 层承载机制（发不发 / 等不等是代码判词；prompt 只说内容与工具引导）——CLAUDE.md chat 修复方法律。
- 禁视频字节进 LLM context（M3 路径）——文本是唯一内容形态（能力声明 True 的 provider 除外）。
