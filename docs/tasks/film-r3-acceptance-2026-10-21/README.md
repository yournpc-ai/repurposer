# R3 验收证据摘要（2026-10-21，脱敏）

> 范围：film 编排 R3（Chat 作品读取与图片机制）付费面实测。**R3 已于同日通过复审**。
> 脱敏口径：无密钥、无完整图片载荷（日志只记字节数/token 数）；fixture 全为隔离测试项目/用户，事故项目 14fa16b6 与其源素材只读未动。
> 台账与收口判定：`docs/tasks/film-storyboard-orchestration-progress.md`（唯一事实源）；本目录只是证据副本。

## 证据文件

| 文件 | 内容 | 来源 |
|---|---|---|
| `spike_verdicts.md` | 图片 spike 两跑原始判决 + usage（第一跑 INCONCLUSIVE→归因，第二跑 POSITIVE） | 会话输出逐字转录（脚本 stdout 不落盘） |
| `smoke_transcript.md` | 真实 Chat smoke 6 腿 transcript（用户消息/助手回答/activity 帧序列） | `/tmp/r3_smoke_transcript.md` 副本 |
| `gateon_8001.log` | 8001 门控开实例全程日志（围栏计数、minimax_usage、uvicorn access） | 本会话启动实例的 stdout，实例已关闭 |
| `prompt_gate_full.log` | prompt_gate 全量日志（321 次请求的 usage 行 + 探针读数行） | 包装器 stdout |

/ tmp 原件随时可失——本目录是唯一持久副本。

## 关键读数

**① 图片 spike = POSITIVE（选项 A 成立，fallback 不启用）**：C1（tool-role 带图）命中像素独有随机码词、C0（无图）诚实承认无图、C2（user-role 对照）命中。10 HTTP / 8,580 tokens / 估算 ≈$0.004。图像 token 化观测 ≈+316 tokens/640×360 JPEG——**单个探针样本的观测，非通用计费规律**（不同尺寸/内容/供应商策略下的费率未测量）。

**② 真实 Chat smoke = 6 腿全硬断言绿**（每腿后 L7 授权律）：L1 读版本（v1/15 场/9:16）/ L2 叠字 vs 截图文字双源 / L3 scoped 视图像素问答（绿底代码面板 smoosh.py + 元素卡）/ L4 取景编辑落 patch（pending v2，focuses=[s1e15] 来自读取清单；**activity 线形 = `chat.activity.storyboardEdit` → `storyboardEditDone`**）/ L6 authored 8s vs actual 8.2s(245f) / L5 超预算报错零图 → scoped 重读全对。L7：零新 run/output/台账行、读取腿 pending 字节不变、standing review hold 全程未释放（含 L4 落版后）。16 HTTP（帽 216 未触发）；prompt 457,852 / completion 6,891 / cached 262,563 tokens；估算 ≈$0.08（缓存口径）–$0.15（无折扣）。

**③ prompt_gate = 10/10 PASS（共享路由回归口径）**：A 12/12、B 12/12、C 10/12（阈 10，贴阈——历史带 11-12/12，边际读数留观）、D/E/F/G/H/H4 12/12、I 11/12（阈 8 = 占位未校准；唯一失败形态 terminal=None ×1，此读数为校准样本）。零 INVALID / 零 provider error / 未复跑 / 未调阈。323 HTTP（session 台账 323/600）；prompt 7,442,324 / completion 137,143 / cached 7,104,237 tokens；估算 ≈$0.69（缓存口径）–$2.4（无折扣上限）。

**合计**：349 HTTP；估算 ≈$0.77（缓存口径）/ ≈$2.6（无折扣上限）——均为估算，非美元硬顶。

## 未验证项（R3 验收范围内）

- **浏览器真实渲染**：patch 活动文案的 SSE 线形（服务端真值）已实证；界面呈现（now-line / 落定行 / 折叠类目）需人工核验。
- **编辑后真实制作未验证**：本轮 patch 止于待产版本落库（L4 断言到 pending v2 为止）；真实 run 执行、TTS 合成、渲染出片与计费结算均不在 R3 验收范围（归 R4+ 轮次）。
- 剧本矩阵 S11 家族延续未运行（归后续轮次按需授权）。
