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

- [ ] 0.1 prompt_gate 11 探针全 PASS（输出落档到本文件末节）
- [ ] 0.2 S-edit PASS（含 ③b 归档不可变拍）
- [ ] 0.3 旧座回归 PASS
- [ ] 拍 1/1b/2/3/4 四族 + 边界面全通
- [ ] 拍 5/6/6b 归档语义全通
- [ ] 拍 3 档披露矩阵确认
- [ ] git worktree clean（文档收口批随后一次性落地）

### 验收记录

（每跑跑完把输出/现象贴在这里——日期、命令、结果。）
