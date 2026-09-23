# 精确编辑迭代 live 走查（用户验收脚本）

> 用途：精确编辑迭代（ADR-090/091/092）终态验收。代码层门禁已绿（Claude 跑：
> 纯 pytest 693 / web tsc 无错 / vitest 70 / S-edit 确定性剧本 PASS / 迁移
> 回滚实证×2 / prompt_gate 探针 H 首测 11/12）；**LLM 拍位与走查体感由本文
> 件驱动用户自跑**。
>
> 前置纪律：
> - 先杀旧栈再起栈（dev.sh 家族杀）：常驻 worker 会抢跑手工 run。
> - `./dev.sh` 起全栈（API 8000 + worker + web）。
> - fixture 纪律：测试项目/素材用 `scenario/` 前缀命名，永不共享 demo key；
>   走查完删项目（页面删除即可，级联干净）。
> - 全 gate 复跑欠账：S3 批跑到 C 后 MiniMax 402 余额尽——充值后先跑
>   `cd apps/api && uv run python scripts/prompt_gate.py`（E/F/G/H 复跑）。

## 0. 门禁（先跑硬的，再跑体感）

```bash
# 0.1 prompt 面门禁（S3 触过 chat tool 注册表与 EditOutputArgs schema）
cd apps/api && uv run python scripts/prompt_gate.py
# 期望：全探针 PASS（H = 精确编辑路由，阈值 8；漂移先复跑一次，再二分）

# 0.2 S-edit 确定性尾（对活 API，零 LLM：归档生命周期全链）
uv run python scripts/chat_scenarios.py --only S-edit

# 0.3 受影响旧座回归（串行，不与 gate 并发）
uv run python scripts/chat_scenarios.py --only S4,S5,S16,S19
```

## 1. 四请求族（LLM 拍位，DoD 1~4）

场景素材：一个已产出 ≥2 条竖屏短片的项目（先跑一条「剪 2 条短片」全链，
产物落在画布上再开始本拍）。

### 拍 1 把开头那句删掉（remove_range）
- 操作：点开第一条短片看字幕，发「把开头那句『<第一句原文>』删掉」。
- 预期：agent 一句话预告 + **事实回声带区间**（「我把 0.0–4.2s 这段去掉了，
  正在重新渲染」）；产物原地重渲染，刷新后该句消失。
- 红：回声无区间 / 绕行整条重生成 / 静默没改。

### 拍 2 第二条再短 3 秒（set_trim + @output 指认）
- 操作：@第二条短片，发「这条再短 3 秒」。
- 预期：target 骑 @output pin（序位词不被解为 id）；事实回声「结尾已收紧到
  NNs」；重渲染后时长确实短 3s。

### 拍 3 字幕换 karaoke（set_caption_style）
- 操作：发「字幕换成 karaoke」。
- 预期：枚举命中（karaoke-highlight），重渲染后字幕样式变。
- 域拒绝面：发「字幕换成黄色 Comic Sans 超大号」→ 拒绝回环带可答形态
  （给枚举清单），**永不假装改成功**。

### 拍 4 标题改成 X（set_title）
- 操作：发「标题改成『我的新标题』」。
- 预期：事实回声「标题已改成…」，重渲染后标题卡生效。

## 2. 归档不变量（DoD 5~6）

### 拍 5 undo 可回滚 + 版本链完整
- 拍 1 之后：调 undo（API 面：`POST /outputs/{id}/operations/undo`，或等
  P1 卡面 UI）→ 上一版 spec 恢复。
- 走查脚本侧：`GET /outputs/{id}/operations` 杂志完整可溯（baseline +
  各 op + undone_at）。

### 拍 6 修订重跑不销毁历史
- 操作：对同项目再发一条「把第一条换成讲 Y 的片段」（触发重跑 wipe）。
- 预期：旧版本**归档不消失**（`GET /projects/{id}/results` 只见新版本；
  旧版本按 id 仍可读）；publication 记录不连坐；新旧版本同 work_id。
- 红：旧版本 404 / 杂志蒸发 / output_refs 死 id。

## 3. 三档 × 费用矩阵（DoD 7）

- composer 底排切 confirm strategy：
  - **仅估价（never）**：新计划确认 pill = estimate 槽现状，CTA 无显价。
  - **完整披露（always）**：pill 出现披露行（hold→按步结算耳语）+ CTA
    显价（「开始 · ~N–M 积分」）。
  - **大额披露（large）**：quote 高端 ≤ 阈值（默认 20）时同 never；超阈值
    同 always。跨设备/刷新后档位保持（服务端持久化——换浏览器读到的
    是同一个值）。

## 4. 认知验收（DoD 8，规则 9）

- agent 看见了什么：产物卡 + 词级字幕 reads（拍 1 的区间就是它看见的
  词边界）。
- 怎么知道自己对了：解算回声事实句（区间/秒数/样式名全来自落账 op 的
  真实值）；多义/未命中 = 域拒绝零猜测（拍 3 的 Comic Sans 面）。
