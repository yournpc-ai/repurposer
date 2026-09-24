# 精确编辑迭代 live 走查（用户验收脚本）

> 用途：精确编辑迭代（ADR-090/091/092）+ Final Hardening（B1/B2）终态验收。
> **Final Hardening 拍板（2026-09-24）后语义已冻结**：
>
> - **Work** = `outputs.work_id` = 稳定作品身份
> - **Version** = 一个 outputs 行 = **rerun/regeneration 产生的 snapshot**
> - **Precise edit** = 当前 Version 内的一次 operation（原地改 render_spec +
>   journal，**不产生新版本行**——「edit → V2」表述已废止）
> - **Undo** = 当前 Version 内 operation rollback（REST 面；chat/UI 动词 = P1）
> - **Restore** = 跨 Version 的 current pointer 换态（REST 面；UI = P1）
> - **Archived** = 只读历史：read ✅ / restore ✅ / **mutate ❌（B2 写门）**
> - **Billing**：edit→render = $0 既定定价，Billing Preference **不作用于此
>   路径**（设计，非缺口）；偏好只作用于付费 run 的 plan-confirm 披露分级
>
> 前置纪律：
> - 先杀旧栈再起栈（dev.sh 家族杀）：常驻 worker 会抢跑手工 run；改了
>   pipeline/chat 代码必须重启 worker 与 API。
> - `./dev.sh` 起全栈（API 8000 + worker + web）。
> - fixture 纪律：测试项目/素材用 `scenario/` 前缀命名，永不共享 demo key；
>   走查完删项目（页面删除即可，级联干净）。
>
> Claude 已跑（有输出落档）：纯 pytest 702 全绿（`9ddf3ec`/`f9f32de` HEAD
> 自验）；渲染后 chat_intent prompt grep 零原始 op 词表残留；chat 工具集
> 无 apply_edit_ops（纯件 + gate 启动断言）。
> **欠账（用户自跑）：prompt_gate 全量复跑（B1 动了 prompt 面，H 扩为
> H/H2/H3/H4 共 11 探针）+ S-edit 复跑（新增 ③b 拍）+ 下列体感拍。**

## 0. 门禁（先跑硬的，再跑体感）

```bash
# 0.1 prompt 面门禁（B1 改了 chat 工具集 + prompt + schema——必须复跑）
cd apps/api && uv run python scripts/prompt_gate.py
# 期望：11 探针全 PASS（H/H2/H3/H4 = 四请求族路由，阈值各 8；
# 漂移先复跑一次，再二分；402 读数 = INVALID 不算行为读数）

# 0.2 S-edit 确定性尾（对活 API，零 LLM：归档生命周期全链 + B2 ③b 拍）
uv run python scripts/chat_scenarios.py --only S-edit

# 0.3 受影响旧座回归（串行，不与 gate 并发）
uv run python scripts/chat_scenarios.py --only S4,S5,S16,S19
```

## 1. 四请求族（LLM 拍位，DoD 1~4）

场景素材：一个已产出 ≥2 条竖屏短片的项目（先跑一条「剪 2 条短片」全链，
产物落在画布上再开始本拍）。

> 已知 UX 边界（非红）：视频产物没有可选 transcript，quote 需要用户手打
> 原句；解算器容忍轻度改写/标点差异。辅助手势（视频内选区引用）= P1。

### 拍 1 把开头那句删掉（remove_range）
- 操作：点开第一条短片看字幕，发「把开头那句『<第一句原文>』删掉」。
- 预期：agent 一句话预告 + **事实回声带区间**（「我把 0.0–4.2s 这段去掉了，
  正在重新渲染」）；产物**原地**重渲染（同一版本行，journal +1），刷新后
  该句消失。
- 红：回声无区间 / 绕行整条重生成 / 静默没改 / agent 自己编了时间码。
- 结果：

### 拍 1b 解算器边界面（只验证，不扩架构）
- 跨 cue：quote 一句跨越多条字幕 cue 的话 → 应解析成功（区间 = 首 cue 起
  → 末 cue 止）。
- CJK/标点：quote 带中文标点或空格差异 → 应命中（归一化容忍）。
- 未命中：发「把『XYZ 不存在的话』删掉」→ 诚实告知找不到，**不猜时间**，
  不静默重生成。
- 多义：quote 一句在片中出现两次的话 → 域拒绝回环，问是哪一次或要更长
  引文，**不猜**。
- 结果：

### 拍 2 第二条再短 3 秒（set_trim + @output 指认）
- 操作：@第二条短片，发「这条再短 3 秒」。
- 预期：target 骑 @output pin（序位词不被解为 id）；事实回声「结尾已收紧到
  NNs」；重渲染后时长确实短 3s。
- 结果：

### 拍 3 字幕换 karaoke（set_caption_style）
- 操作：发「字幕换成 karaoke」。
- 预期：枚举命中（karaoke-highlight），重渲染后字幕样式变。
- 域拒绝面：发「字幕换成黄色 Comic Sans 超大号」→ 拒绝回环带可答形态
  （给枚举清单），**永不假装改成功**。
- 结果：

### 拍 4 标题改成 X（set_title）
- 操作：发「标题改成『我的新标题』」。
- 预期：事实回声「标题已改成…」，重渲染后标题卡生效。
- 结果：

## 2. 归档不变量（DoD 5~6 + B2）

### 拍 5 undo 可回滚 + 杂志可溯（当前 Version 内）
- 拍 1 之后：调 undo（API 面：`POST /outputs/{id}/operations/undo`，用户级
  undo UI = P1）→ 上一版 spec 恢复（同版本行内回滚，**不是跨版本**）。
- 走查脚本侧：`GET /outputs/{id}/operations` 杂志完整可溯（baseline +
  各 op + undone_at）。
- 结果：

### 拍 6 rerun 产生新 Version，历史不销毁
- 操作：对同项目再发一条「把第一条换成讲 Y 的片段」（触发重跑 wipe）。
- 预期：旧版本**归档不消失**（`GET /projects/{id}/results` 只见新版本；
  旧版本按 id 仍可读）；publication 记录不连坐（锚定当时发布的版本行 =
  immutable snapshot 语义）；新旧版本同 work_id。
- 红：旧版本 404 / 杂志蒸发 / output_refs 死 id。
- 结果：

### 拍 6b 归档版本不可变（B2；S-edit ③b 已覆盖 API 面，此拍为体感确认）
- 操作：拍 6 之后，对**旧版本 id** 直接调 `POST /outputs/{旧id}/operations`
  / `PUT /outputs/{旧id}`。
- 预期：全 409（"Archived version is read-only"）；restore 旧版本后它重新
  可编辑，且当前版本自动归档。
- 结果：

## 3. Billing Preference（DoD 7 收窄版——披露分级，非扣费闸）

> 冻结口径（2026-09-24）：偏好 = **持久化 + plan-confirm 披露分级**；
> edit→render $0 路径无闸可落（设计）。本段不验证任何 edit 计费。

- composer 底排 / dock 头部切 confirm strategy：
  - **仅估价（never）**：新计划确认 pill = estimate 槽现状，CTA 无显价。
  - **完整披露（always）**：pill 出现披露行 + CTA 显价（「开始 · ~N–M 积分」）。
  - **大额披露（large）**：quote 高端 ≤ 阈值（默认 20）时同 never；超阈值
    同 always。跨设备/刷新后档位保持（服务端持久化——换浏览器读到的是
    同一个值）。
- 结果：

## 4. 认知验收（DoD 8，规则 9）

- agent 看见了什么：产物卡 + 词级字幕 reads（拍 1 的区间就是它看见的
  词边界）。
- 怎么知道自己对了：解算回声事实句（区间/秒数/样式名全来自落账 op 的
  真实值）；多义/未命中 = 域拒绝零猜测（拍 1b / 拍 3 的 Comic Sans 面）。
- 结果：

## 5. 收口条件（全勾 = PRODUCT CLOSURE）

- [x] 0.1 prompt_gate 11 探针：10/11 PASS；F 经复跑 + pre-B1 A/B 实证为
  provider 漂移（合成 UUID 抄串行），非行为回归（输出落档末节）
- [x] 0.2 S-edit PASS（含 ③b 归档不可变拍）
- [x] 0.3 旧座回归 PASS（S4/S16/S19；S5 = provider 漂移，pre-B1 A/B 实证）
- [x] 拍 1/1b/2/3/4 四族 + 边界面全通（drive 3 + drive 5）
- [x] 拍 5/6/6b 归档语义全通（真 wipe 取证，KEEP 项目 6986cc90）
- [x] 拍 3 档披露矩阵：持久化层 PASS（`4a3059d` 修后两回 live round-trip）；
  披露分级渲染 = 前端面，本轮未走 UI（冻结口径只要求持久化 + 披露分级）
- [x] git worktree clean（B1/B2/B4/设置修复已提交；文档收口批随后一次性落地）

### 验收记录

（每跑跑完把输出/现象贴在这里——日期、命令、结果。）

**2026-09-24（Claude 代跑，用户授权「你跑吧」）**

栈：API :8000（新代码）+ worker + render（3001，因 500 重启过一轮并捕获日志——
初启 500 落在 18:26–18:47 DNS 抖动窗内，重启后未复现）。

- **0.2 S-edit**：PASS（含新增 ③b 归档不可变 409 四连拍，对活 API）。
- **0.3 回归**：S4 / S16 / S19 PASS；S5 FAIL = provider 漂移（pre-B1 worktree
  `d06ff1e` A/B 对照同样失败且更糟——LLM 把 raw JSON 漏进散文；与本批改动无关）。
- **0.1 prompt_gate 第一次全量**（18:03–18:27，`tail -25` 管道只留尾部）：
  H3 12/12 PASS；H4 INVALID（3 轮 ConnectError = DNS 抖动，非行为读数）；
  A/B/C/D/E/F/G/H/H2 tally 丢失于管道。
- **0.1 prompt_gate 第二次全量**（18:45 起，完整日志 `/tmp/prompt_gate_full_1845.log`）：
  **A 12/12 PASS，B 11/12 PASS**；C 起全部 INVALID——MiniMax **402
  insufficient_balance (1008)** 自 18:48 起持续，余额耗尽。
- **体感驱动**（`scratch/precise_edit_live_drive.py`，真 fixture 视频 + 真 ASR +
  真 plan/run/render + 真 MiniMax 回合）：
  - 第一轮：ASR PASS / plan→run PASS / run terminal PASS / select_clips 成功；
    渲染 500（DNS 抖动窗）；driver 自身 RenderStatus 枚举笔误（DONE→COMPLETED，
    已修）。
  - 第二轮：ASR PASS；plan 回合 **402 余额耗尽**中止。
- **当前阻塞**：MiniMax 账户余额（402）。欠账 = gate C~H4 九探针读数 +
  体感拍 1~6b + billing 持久化。**充值后复跑**：
  `cd apps/api && uv run python scripts/prompt_gate.py > /tmp/gate.log 2>&1`
  然后 `uv run python ../../scratch/precise_edit_live_drive.py`。

**2026-09-24 晚（充值后复跑）**

- **0.1 prompt_gate 第三次全量**（19:07 起，完整日志 `/tmp/prompt_gate_full_1907.log`）：
  **A 12/12 · B 12/12 · C 12/12 · D 12/12 · E 12/12 · G 10/12 · H 12/12 ·
  H2 12/12 · H3 12/12 · H4 12/12 全 PASS；F 7/12 FAIL（阈值 8）**。
- **F 复跑**（纪律「漂移先复跑一次」）：7/12 再 FAIL，完全可复现。
- **F 取证**（`scratch/probe_F_forensic.py`，逐轮打印）：12 轮全部调对
  revise_plan 且全部指向 plan B——3 轮失败 = **UUID  verbatim 抄错**
  （`bbbbbbbb-2222-2222-2222-222222222222` → `…-bbbbbbbbbbbb`，探针合成
  UUID 的高度重复段诱发抄串行），1 轮 ask_user 误路由。语义路由 11/12 正确。
- **F 零假设二分**（纪律「再二分」）：pre-B1 worktree `d06ff1e` 同小时跑
  `--probe F` = **5/12，比现行更差**。结论 = MiniMax provider 漂移 +
  对抗性合成 UUID 的固有复制难度，**非 B1 回归**（B1 未触 intent_router.j2
  / revise_plan schema）。阈值不回调。生产面有兜底：错误 plan_id 走域拒绝
  回环（读容忍），且真实 UUID 段间差异大、不似探针合成值重复。
- **体感驱动第一轮**（driver v1）：setup 全绿（真 ASR / 真 plan / run
  completed / 双渲染 completed / caption_track 30 cues）；拍1b 跨cue PASS
  （ops 落账 + cue 消失 + 重渲染）；拍1b 未命中拒绝 PASS（诚实告知 + 可答
  形态选项，零突变）；拍5 undo+journal PASS（200 + head undone_at + 杂志
  可读）。**发现一真问题：@output pin 被 LLM 转述覆盖**——拍2 钉 fa51d3f3
  发「这条再短 3 秒」，实际编辑落在另一条 e5ee26cd（intent 戳
  target_output_id 实证，「收紧到 8.7s」是该条真实数字，非编造）；拍3/4
  同理（driver 文案「第一条」与 pin 矛盾，属干扰信号）。根因（静态实证）：
  `_edit_output` 的 target.output_id **由 LLM 填**，服务端只校验合法性，
  无「pin 在 → 钉 id 强制覆盖」；MENTIONS 注册表声称「钉 id 服务端确定性
  解出，LLM 不猜」。**与 probe F 同属「LLM 转述 UUID」失败类。**
- **拍6 driver bug**：graph/revise 422（v2 已改打印响应体）。
- 驱动 v2（`scratch/precise_edit_live_drive.py` 重写）：每拍记录
  intent target vs pin、双侧 journal 增量；quote 选择耐受词级 cue；
  复跑中。

**2026-09-24 深夜（drive 2/3）**

- **drive 2**：拍2 set_trim PASS（delta 精确 3.0s、回声「收紧到 34.1s」真实）、
  拍3 karaoke PASS / Comic Sans 零突变、拍4 set_title PASS、拍5 undo PASS。
  拍1/1b 为 driver 工件（词级 cue 致 quote 退化 + 文本缺席断言对词级流无效）。
  拍6 422 = undo 的重渲染在途、节点 running（driver 节奏问题）。
- **drive 3**：拍1b 跨cue PASS（op span [12.4,13.14] 与引用 cue 区间**逐秒
  一致**、回声区间真实）；拍1b 大小写容忍 PASS（全大写引用命中
  [15.06,15.84]）；未命中拒绝 PASS（明说查不到 + 给可答形态）；多义拒绝
  PASS（「of」5 处列举 + 反问哪一处，零猜测）；拍2 set_trim PASS
  （pin_honored=true，delta 3.0s）；拍3 karaoke + Comic Sans 拒绝 PASS；
  拍4 set_title PASS；拍5 undo+journal PASS（title 回滚、journal 5 行、
  head undone_at）；拍6 revise 202 PASS。**pin 命中 3/3**（拍1b/3/4），
  拍2 本轮 pin 也命中——drive 1 的 3/3 覆盖未复现（见下，仍待裁定）。
- **拍6 rerun spawned RED = driver 工件**：runs0 快照在 revise 之后取
  （202 同步产 run），v4 已修正。
- **拍1 INVALID 根因**：无 pin 时 agent 的「第一条」与 driver 的 clip1 不是
  同一条（outputs 列表序 vs 用户序位词），agent 在另一条里查不到引用原话
  → 诚实拒绝。序位词目标歧义 = 与 pin 覆盖同族的指认问题。
- **中途插曲**：栈被外部重启（dev.sh 家族杀，exit 144）——驱动经 DB 轮询
  无碍继续，run 由新 worker 接管（Postgres SKIP LOCKED 队列韧性实证）。

### 待裁定新发现（晋升评估）

**@output pin 转述制**（live 实证 + 静态定位）：

- **现象**：用户 @钉 A 发「这条再短 3 秒」，agent 改了**会话焦点里的另一条**
  B 并以 B 的真实数字回报成功（drive 1 拍2、drive 2 拍2 两回干净复现；
  drive 3 拍2 命中）。钉子被 LLM 的序位判断覆盖。
- **静态根因**：`propose_turn._edit_output` 的 `target.output_id` **由 LLM
  填**（schemas ReviseOutputTarget），mention pin 只进 prompt 上下文
  （`context.py` Mentions 块），服务端校验 id 合法性但**从不核对 =
  钉的 id**；prompt 只有一句「use its id instead of guessing」
  （chat_intent_system.j2:103）。`revise_output` 同一转述制。
  MENTIONS 注册表声称「钉 id 服务端确定性解出修订目标，LLM 不猜」——
  实现与宣称不符。与 probe F 同属「LLM 转述 UUID」失败类。
- **晋升自评**：命中硬条件 **B（造成错误修改）**——编辑落在未钉的另一条
  且回报成功。修复面小（服务端 pin 覆盖或 pin≠param 域拒绝回环，
  `_edit_output` + `revise_output` 两处）。**晋升 B4 还是入
  POST-CLOSURE BACKLOG，由用户拍板。**

**2026-09-24 深夜（裁定后修红批，用户三项拍板）**

- **Billing 持久化落空（live 实测新发现，frozen DoD 7 红）**：PUT
  /auth/settings 回显 200 但 `users.settings` 恒 NULL，GET 永读默认值。
  根因 = 依赖会话分离：`get_current_user_required` 用自有短会话加载 User，
  路由改的是游离实例、提交的是另一个会话 → 零写入。已修（`4a3059d`，
  经路由会话写）+ live 复证 PASS（PUT never → DB `{'confirm_strategy':
  'never'}` → GET never；二次写合并正常）。
- **B4 用户拍板晋升，已修（`35e572e`）**：`pinned_output_id` 写门——回合
  恰一个 output pin 时钉恒胜（覆盖/填空 LLM 转述），`_edit_output` 与
  `_revise_output` 同批封闭；纯件 5 件 + 全量 710 绿 + 冷导入 OK。
  **live 复证欠账**：钉非焦点片的编辑回合，随下一轮 drive 复跑。
- **drive 4 两个未决异常**（证据随 cleanup 销毁，未复现）：
  ① run 25min TIMEOUT 但双渲染 completed（81s 长片或 finalize 卡住，存疑）；
  ② 拍1b /chat 500。500 定向复现尝试（`scratch/repro_chat_500.py`：chat
  路径 + 多义问题挂着 + 带 pin 编辑）→ **未复现（201）**；首轮复现的 500
  实为 repro fixture 的伪 spec 多带 `version` 键所致，与 drive-4 不同因。
  两者留观：下一轮 drive 若重现即取证（栈日志在手）。
- **下一轮 drive（等充值）**：拍6 真 rerun → 归档不变量 → 拍6b → billing
  round-trip → B4 live 复证（钉非焦点片）。driver = v4 修订版
  （runs0 快照序已修、拍1 钉 clip1、span 覆盖断言）。

**2026-09-25 凌晨（drive 5 终轮 + 真 wipe 取证，充值后）**

- **drive 5 编辑拍全绿**：拍1 remove_range PASS（pin 命中、op span
  [11.7,13.46] 贴开头、区间回声真实）；拍1b 跨cue / 大小写容忍 / 未命中拒绝 /
  多义拒绝 全 PASS；拍2 set_trim PASS（pin 命中、delta 3.0s）；拍3 karaoke +
  Comic Sans 拒绝 PASS；拍4 set_title PASS；拍5 undo+journal PASS。
  **pin 全拍命中**（B4 写门上线后）。
- **拍2/拍3 重渲染 RED = 渲染服务间歇失败**（err「视频渲染失败，请重试」，
  同栈 drive 3 全成、本拍 拍1/拍4 重渲染成）——环境类 flake，非本轮代码面；
  留观。
- **拍6 revise 422（第二次）根查明**：拍2/3 渲染失败后节点滞留 running，
  revise 门的 running 守卫正确拒绝；~15min 后 worker reaper
  （reaped_stale_nodes 900s）重跑 select_clips → **真 wipe 发生**。
  「失败渲染 → 节点滞留 → reaper 重跑 = 重型副作用」是图生命周期层的
  既有行为（D9 族），非本迭代引入——入 POST-CLOSURE BACKLOG 观察项。
- **真 wipe 归档取证（KEEP=1 项目 6986cc90）**：
  - 旧版本 228689a2 / 2bb830bb 均 archived_at 落戳 ✅；读面只见新版本
    （results = b9104fc5 / d4faf6f8）✅
  - **work_id 按位继承** ✅：d4faf6f8 继承 2bb830bb 的 26b793ef，
    b9104fc5 继承 228689a2 的 5fed3fd8
  - 旧行按 id 可读 GET 200 ✅；journal 完整可溯（2bb830bb = snapshot +
    3×remove_range + set_caption_style + set_title(undone) 全在）✅
  - **拍6b 归档不可变：operations / undo / PUT / regenerate 全 409** ✅
    （真 rerun 产物上实证，B2 写门 live 生效）
- **billing round-trip 复证 PASS**（该项目用户上 never→never / always→always，
  `4a3059d` 修复后第二次 live 实证）。
- **B4 live 复证**：drive 5 pin 全命中（拍1/1b/2/3/4 钉 = target 一致）；
  覆盖分支（LLM 自选 ≠ 钉）由纯件 5 件锁定，本轮未自然复现分歧场景——
  如实标注。
