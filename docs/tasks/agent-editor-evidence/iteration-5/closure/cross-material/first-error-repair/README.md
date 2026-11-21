# 首次未完整通过任务：首错归因与最小闭环

本轮保留六个独立素材的原始首次分母：**3 完整、2 部分、1 失败，完整通过率 3/6 = 50%**。同源复测、定向续测和新增独立样本都不回填这个分母。原始用户原话、Provider wire、Tool Schema、原生调用 ID、SSE、数据库快照和媒体仍保存在上级目录；本目录只追加修复后的证据。

真实复测继续使用 MiniMax / MiniMax-M3.1-Flash、temperature=0.2、最多 20 次模型决策，使用隔离 PostgreSQL、对象存储前缀和测试服务。没有提高上限、新增 Agent/Workflow/工作台、通用 DAG 或兼容层。

## 1. 施工前首错归因

以下归因在修改代码前，由三份原始 Provider wire、SSE、持久消息、版本内容和真实媒体交叉核对。

| 任务 | 首个错误决策 | 模型当时看到的事实 | 缺失或错误事实 | 根因类别 | 最小修复位置 |
|---|---|---|---|---|---|
| 单人讲话 | 最后一次模型决策把单帧视觉观察写成“头肩、上臂完整且构图合适”的确定性结论 | v3 已正确保存 scale=1.55、x=-8、y=18；0–12 秒已复看；实际只有 5.966667 秒采样帧、源帧和几何边界 | 没有全时段头肩完整性证据；源上下仍有裁切，人脸/扩边区域不等于头肩证明 | 模型视觉陈述过强；不是执行或停止错误。现有几何与人脸边界修复已存在 | 不重复开发；用原话复测 `chat/prompts.py` 的现有边界 |
| 字幕短视频 | 正式审阅已经报告字幕不完整清晰后，主 Agent 仍选择交付，最终回复漏掉这个未满足的用户硬要求 | v3 已恢复 scale=1、x=0、y=0；Output 与 v3 和实际文件一致；reviewer 的 F01 明确报告字幕可读性/裁切问题 | 最终回复没有保留未满足项；字幕是源视频烘焙像素，不是独立 TextObject；源与 Output 全流 PCM 都为零 | 证据充足下的模型交付/陈述错误；不是 Renderer 音频故障，也不需要字幕工作台 | `chat/prompts.py` 的审阅后决策与最终回复规则 |
| 开放演讲 | 第 4 次模型决策在已有 v1 上调用 `create_video`，试图用重建作品实现 fit 修改；服务端拒绝，未写版本 | 当前 Composition/v1、三段源窗口、两个真实空档和实际预览均完整可见；`create_video` 仍错误地对已有作品可见 | 当前作品 Context 没有缺失；是工具可见性与模型工具选择错误 | 首个错误是 Tool 选择/可见性；后续同源复测还显示模型把假设性缺陷反复升级为追加观察 | 保留已有 `create_video` 可见性修复；只收紧 `chat/prompts.py` 的证据充分停止与交付规则 |

### 原始证据锚点

- 单人讲话：`../first-single-speaker.json.gz`，最终决策 `5fc2f4c3-b19b-4206-9c87-e2d0bd14e84a`；v3 `c9abceda-b4a0-4347-aa21-1347e02fdede`；当前帧 JPEG SHA-256 `5237df9840d8954357c9a3b41f79e356f56e07c25befb1a5ef8b4f21a5edd00f`。
- 字幕短视频：`../first-subtitled-short.json.gz`，reviewer 调用 `4d3730ed-1d4f-4207-a15c-5abd8c757972`，交付决策 `7af425aa-e7dc-4180-9fee-aeae3c735040`；Output `842064ba-66fd-4507-94b3-27bef48af672`；源 SHA-256 `deb5d036ccf0311b6c7d90ba33104f66de25484acca332599c3707ede485743b` 与本地源一致。
- 开放演讲：`../first-open-speech.json.gz`，错误 `create_video` 为 `call_function_z0jqlmvazi27_1`，决策 `d4e76cd8-ba9d-4f5b-a866-790659507bc7`；当前版本和工具清单都在该次请求中。
- 开放演讲同源后续：`../open-speech-after-facts-post-facts.json.gz` 已不再调用 `create_video`，三次缩放合为一组，但仍因连续假设性补看而在正式审阅后耗尽；该轮及之后应用户要求完成的交付均不回填为首次成功。

### 直接媒体核对

字幕源 `artifacts/sequential-p2/first-run/review-1.mp4` 与原始归档 Output 都经 PyAV 完整解码音频：各 190 个音频块、389,120 个数组值，最大绝对值均为 0。输出静音与源一致。字幕位于源视频像素内，当前 Composition 只有一个 VideoClip；`scale` 只能缩放整个视频，不能独立调整字幕字号或样式。原用户要求是“底部字幕完整可读”，不是增大字号，因此本轮没有擅自添加字幕 Tool 或修改字号。

开放演讲原始三次 0–12 秒同参预览对应不同版本与不同 MP4 SHA，不是同版缓存失败。剩余问题是模型在现有覆盖充分时继续寻找没有证据的问题，不是简单禁止同参预览。

## 2. 实际最小修改

- `apps/api/app/chat/prompts.py` 的 `assemble_video_round()`：采样限制只限制结论，不得成为不断寻找假设问题的理由；用户点名内容已在当前版本观察且没有待修发现时，停止追加观察并完成要求的交付或答复。审阅发现若仍涉及未解决的用户硬要求，交付与最终回复必须明确报告，不得把 Output/交付卡等同于目标完成。
- `apps/api/app/tools/video/preview.py` 的 `source_framing()`：在已读取并核验 digest 的固定源上复用 `analyze_audio_bytes`，向模型投影 `source_audio={stream_present, fully_decoded?, is_silent?}`。多 Clip 只有全部共享同一 SourceSnapshot/digest 时才返回源音频事实，不伪造多 Clip 几何或源帧。
- 没有新增 Tool、Schema、状态机或 Composition 写口；没有删除本轮仍正确的逻辑。开放演讲的 `create_video` 误用已由本轮之前的 `names.discard("create_video")` 修复，本轮不重复修改。

源音频投影是复测中确认的事实缺口：模型只能看到 Output 的技术音频事实，无法据此区分“源有静音轨”和“源无音轨”。它只补充观察事实，不替模型判断用户目标。

## 3. 原失败任务真实复测

| 原任务 | 实际结果 | 版本 / Output | 严格分类 |
|---|---|---|---|
| 单人讲话 | 7 次请求；正确恢复并复看 12 秒；scale=2.2、x=-29.1、y=46.2；按要求无 Output。能区分源裁切、画布留边和人脸框，但仍无依据地称“手部完整”，并泄露内部字段/技术标识 | v3 `ba27de81-651c-4650-b7ce-0c5df7b57ef5` | **部分完成**：执行目标完成，Chat 事实仍未关闭 |
| 字幕短视频 | 12 次请求；v3 恢复 scale=1/x=0/y=0；120 帧、4 秒 Output 已审阅并交付。本轮 reviewer 认可底部字幕完整，回复保留源静音和抽样限制；未改字号、未改原声 | v3 `2c8f3bcf-80dc-4ffd-ae63-6596ef3be2ac`；Output `fefd8629-c8ee-404a-95da-e9f4d0e1db5f` | **本轮用户目标完整**；不代表可独立编辑烘焙字幕 |
| 开放演讲 | 17 次请求完成到交付；未再误用 `create_video`；两个空档关闭，三段保留原顺序和 30–45 秒有效源窗口；三次 scale 同批；450 帧/15 秒 Output 已审阅交付。一次非法 `trim_clip(end=6)` 被拒绝，另有 1 个取消的非法预览；最终仍把约 1.2px 留边说成“黑边消除” | v6 `4903eb1b-f67d-4d49-80fa-306aa5c23998`；Output `c31e8b92-163e-497a-b7fa-dc6290583530` | **部分完成**：编辑/交付完成，Chat 视觉结论过强 |

开放演讲从首次 20 次耗尽降到 17 次并完成 Output 审阅与交付，证明停止规则改变了原来的错误路径；但最终误述证明它还不是稳定完成。没有通过禁词表或自动交付掩盖这一点。

对应完整 wire/SSE/DB 归档：`single-speaker-repair-original.json.gz`、`subtitled-short-repair-original.json.gz`、`open-speech-repair-original.json.gz`。三份 Output 的实际 MP4 与 SHA 在同目录。

## 4. 独立素材、连续修改与成功回归

| 层级 | 任务与结果 | 分类 |
|---|---|---|
| 新独立人物素材 `talking-head.mp4` | 6 次请求；v3 `573de149-d116-471e-8583-6f91e9de9fbd`；scale=1/x=0/y=0；4.25 秒不变，无 Output；明确说明人脸框不单独证明头肩 | 主任务完整 |
| 新独立双 Clip 动画 `text-animation.mp4` | 8 次请求；v2 `17666652-ef98-4190-aafd-53e64b52f41d`；空档 2.75→2 秒关闭；Output `83883407-0efb-4200-82c7-69930eb46476`，128 帧，审阅并交付 | 主任务完整；当轮附带“源自带音轨”误述由后续源事实续测纠正 |
| 同作品连续修改 | 真实 API 4 次请求；人物左移 4px，v4 `f0c4dd0b-b9f9-40b5-b718-8ab58af54d62`；时长不变，无 Output | 完整 |
| 原成功双人视觉修订 | 7 次请求；一次错误 `inspect_clip(clip_0)` 后恢复；v3 `fcc936c3-1ac4-4072-be27-1cdc93e44a59`，scale=1/x=0/y=0，无 Output | 编辑目标完成；回复仍有 composition 技术 ID |
| 原成功真实接缝 | v2 后执行反复 `workflow_step_fenced`，相关 Run 已取消；无 Output | **失败回归，未通过** |
| 原成功图片标题/片尾卡 | v3 后同样反复 fencing，相关 Run 已取消；无 Output | **失败回归，未通过** |
| 原成功媒体生成与插入 | 旁白首错为 `This execution's narration request has no confirmed fixed audio; recovery will not submit it again`，随后恢复失控；Run 已取消；v1，无 Output | **失败回归，未通过** |

因此本轮只证明两个新增独立素材的主任务能够走通，**没有证明跨素材普遍稳定，也没有证明原成功任务全部保持**。三项 Worker/恢复故障不在本次 Prompt/观察事实修复中扩修，原始 wire、版本、Run/Step 和取消终态见 `failed-*.json.gz` 与 `failed-regressions.json`。

## 5. 五面核对

| 面 | Prompt/停止切片 | 源音频事实切片 | 证据 |
|---|---|---|---|
| Tool Call | Schema 未变；已有作品不再暴露 `create_video`；开放复测 20/21 调用符合当次 Schema，非法 trim 被拒绝且未写坏版本 | `preview_range` Schema 未变，只增加固定源的音频事实 | 各 gzip 中每次请求的 `payload.tools`、原生 call ID/参数与下一轮 tool 响应 |
| Prompt / Context | 修改现有 System Prompt；观察仍绑定当前版本、窗口、媒体和采样时点，没有删除必要观察 | 单 Clip 保留原源帧/几何/人脸；同源多 Clip 返回同一 digest 的音频事实 | 两个 `*-source-audio*.json.gz` 中的实际 System/User/Tool Context |
| Chat Message | 未满足硬要求必须进入交付与回复；复测仍有过强视觉陈述，未宣称修复 | 正确区分“源有静音 AAC”与“源无音轨、输出有静音占位 AAC” | 持久 assistant 消息、SSE 和浏览器截图 |
| Execution / State | 开放演讲 v6 与 Output 一致；字幕 v3 与 Output 一致；时长、源窗口、无关素材保持 | 只读；两次定向续测均未修改版本或新增 Output | `metrics.json`、版本 timeline、Output digest 和真实 MP4 |
| Recovery / Replay | 真实 Stop 返回 `accepted=true, turn_state=retracted`，版本 3→3、Output 0→0；未改 StaleBase/并发/账本/Worker 恢复代码 | 重读当前版本没有重复 Output 或扣费；固定源 digest 不符仍拒绝提供事实 | `repair-stop.json`、两次源事实续测；既有完整恢复矩阵见上级 closure 证据，未冒充本轮重跑 |

没有为形式修改五个模块。未改动的恢复面复用既有定向证据；三项新增真实 Worker 回归失败已单列，不能被上述 Stop 通过覆盖。

## 6. 浏览器与工程验证

- Chrome 实际打开三份新 Output，播放时 `currentTime > 0` 且未暂停；硬刷新后以相同 URL/Output 身份再次播放。见 `browser-results.json` 和 `browser-*.png` / `browser-studio-*.png`。
- Studio 截图可见真实回复与 Tool Group。另通过浏览器 composer 真实发送一条只读查询：HTTP 200、4 次 Provider 请求、硬刷新后消息仍在，版本 4→4、Output 0→0。模型仍不必要地追问“怎么处理”，所以 UI 链通过不等于该答复完整。见 `browser-continuation.json(.gz)` 与两张 continuation 截图。
- `apps/api`: `.venv/bin/python -m pytest -q test/core` → **509 passed, 3 warnings**。
- `apps/web`: `pnpm test` → **44 files / 411 passed**；`pnpm exec tsc --noEmit` 与 `pnpm build` 均成功。
- Renderer: `pnpm --filter @repurposer/render exec node --import tsx --test src/*.test.ts src/component-runtime/*.test.ts` → **28 passed**。
- `git diff --check` 与修改的 Python 文件编译检查通过。离线复核 `verify.py` 校验版本、源窗口、Output 绑定、帧数归档、源音频、Stop 和浏览器记录，生成 `verification.json`；它不替代真实 MiniMax 调用。

## 7. 请求、Token、重复操作与费用

### 原任务前后对照

| 原任务 | 请求 | 输入 Token | 输出 Token | 重复预览 | 应用记录 USD |
|---|---:|---:|---:|---:|---:|
| 单人：首次 → 修复复测 | 7 → 7 | 74,794 → 61,287 | 3,673 → 5,889 | 0 → 1 | 0.013423 → 0.012726 |
| 字幕：首次 → 修复复测 | 10 → 12 | 109,039 → 108,911 | 4,858 → 3,068 | 1 → 0 | 0.019271 → 0.018177 |
| 开放：首次 → 修复复测 | 20 → 17 | 327,122 → 202,640 | 23,271 → 8,837 | 3 → 0 | 0.063031 → 0.035698 |

开放演讲输入约降 38%、输出约降 62%、应用记录费用约降 43%，且不再耗尽；其他任务没有全面下降，不能宣称整体成本降低。所有样本 `identical_edit_requests=0`，但开放复测仍有一次非法 trim 和一次取消的预览。

`metrics.json` 的 9 个选中回合合计 **66 请求、619,741 输入、24,615 输出 Token、0.107729 USD**。续轮的 `usage_usd` 已按该回合精确 Token 对应的 ConversationUsage 行计算，没有把同项目累计用量重复相加。

浏览器续发另计 **4 请求、28,589 输入、767 输出 Token、0.004749 USD**。三项失败回归合计 **17 请求、142,756 输入、1,869 输出 Token**；这些回合未正常结算，应用 Usage 行为 0，不能把该 0 解释为供应商没有成本，也不据此估算额外总价。以上不是施工期间每一次实验的全量账单。

## 8. 仍未关闭

- 模型仍会把采样帧扩大成未观察部位或极窄留边的确定性结论，也会泄露技术 ID；本轮没有继续堆禁词。
- 烘焙字幕没有独立字号/样式 Tool；只有未来用户目标确实需要时才值得做最小领域能力。本轮原话只要求完整可读。
- 当前 MiniMax 请求没有可证明的主观音频输入；解码、PCM 与响度不等于听感。
- 网站审美修订、开放创作的一般停止/交付稳定性和自然语言泛化仍未证明。
- 接缝、片尾卡、媒体生成的 Worker fencing/固定音频恢复失控是未关闭的真实工程阻塞；本轮没有借最小 Agent 决策修复扩建 Worker 重构。
