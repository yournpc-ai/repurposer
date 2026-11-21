# I7 第一批验收

2026-11-22，main 开工版本 `e5f14ca3`。I7-0 已复现缺陷，I7A、I7B 的真实模型旅程待验。[数据库、预览、恢复装配与 Chrome 实测数据](audit.json)

## I7-0 · 第二镜头的运动来源

独立 PostgreSQL 5966 上的 I6 库为 `j6d05_project_brief`。以 PostgreSQL TEMPLATE 复制到 `rep_i7_9x2iij`，保留项目、版本链、原 opening、六段旁白、快照和 Output 身份。副本与原库开工 head 均为 v15（379d8dd6）。共享 5432、历史项目及正式 MP4 保留。隔离 API 19981 与 Renderer 19987 用于渲染，19881/19889 用于旧 Chat 卡回放。没有启动共享 API。

| 能力 | 实际证据与边界 |
|---|---|
| 动画读取与定位 | 审计者通过生产 inspect_clip 读取 v15 的所选 WebObject。v13–15 数据库均有同一网页快照、缩放和位移轨迹。原工具只提供属性名。I7 增补所选片段两类整对象动画的 ID、target、局部 tick、值和 easing。模型自主定位待验。 |
| 初稿与求值 | 固定网页 view 提供底图。web_shots 将取景写为 Clip.animations。video_spec 将局部 0、364500、810000 tick 编译为 0、122、270 帧。Video.tsx 调用 evaluateProperty 按 object ID 和属性在片段局部帧求值。三个点均为 linear。第 270 帧是右开结束边界。Preset 注册表和 animation.py 的 TextPart 切分均不负责这里的逐帧运动。 |
| 修改已有点 | 首错发生在原生编辑面。静态 scale / translate 拒绝动画接管的属性。UpdateClip 的 animations 字段使用整列表替换。新增 set_keyframe 以 clip、动画 ID、已有 tick 和数值为输入，服务端从固定 base 完整保留同级动画与 easing 后提交 UpdateClip。PostgreSQL fixture 已检验值变更、类型拒绝、重放与旧 base 冲突。 |
| 播放与输出一致性 | 生产 prepare_saved_video_scrub 与 /preview 渲染 v15 第二镜头 3.5–12.5 秒，解码 270 帧。v14 正式 MP4 相同镜头数据逐帧对应 105–374，缩至 384×216 后逐像素 RGB 平均绝对误差 0.159/255，单帧最大均值 0.230/255。覆盖现有缺陷基线，新编辑版本待验。 |
| 版本、恢复与重放 | 复用 opening/call ID、唯一写口和 CAS。旧 opening 的恢复装配可重建。真实模型故障续跑待验。 |
| 专业操作范围 | 工具限整对象缩放与二维位移的已有点值。新增、删除、移动点及其他专业操作均未纳入。 |

左栏为新渲染的 v15 预览，右栏为 v14 正式文件。五个时间点覆盖镜头开始、推近中、原缺陷帧、推近后和最后可见帧。画面中估值卡标题在 8.000 秒已越过右边界，到 12.467 秒仍裁切。

![第二镜头基线逐帧对照](scene-2-baseline.jpg)

## I7A · 恢复

在隔离副本用真实原 opening 和导出回执重建发送前上下文。`already_saved_this_turn` 包含 extend_still v14，目标为原 v14 Output。工具投影包含 review_video，已排除 extend_still、set_keyframe 和 export_video。此次检查在 provider 调用前停止。尚无本批新导出成功后强杀、恢复模型请求、账本差分或交付卡去重证据。历史 v15 保留。

## I7B · 专业编辑

已完成读取和领域写口，原生工具注册、Chat 活动文案、中断回执共用既有入口。回归复用现有 PostgreSQL 片段 fixture，比较整个 timeline，确认只改指定值。同 call 重放返回同一版本，陈旧 base 拒绝。定向执行 test_editor_split.py 与 test_provider_tools.py 共 54 项通过。受影响的 Web 字典经 TypeScript 检查。

本批尚无获准的新 MiniMax 美元上限与正式导出积分上限。I6 的两笔导出分别绑定已执行的旧 Job。未发起本批付费模型决策或新正式导出。目标项目副本仍可从 v15 开始自然语言旅程，当前尚无模型生成的新版本、修复后画面或正式交付。

| 面 | I7-0 基线 | I7A 恢复任务 | I7B 裁切修复 |
|---|---|---|---|
| Tool | 通过，生产读取 | 未验证，缺恢复后的模型调用 | 有条件通过，领域调用已测，缺自主调用 |
| Context | 通过，版本、目标与六个点可读取 | 有条件通过，真实回执装配到发送前 | 未验证，缺本轮模型输入与观察 |
| Chat | 通过，历史交付卡复查 | 未验证 | 未验证 |
| Execution | 通过，真实 DB、Renderer、旧 MP4 | 未验证 | 有条件通过，写口已测，缺任务新版 |
| Recovery | 有条件通过，旧 opening 重建 | 未验证 | 有条件通过，写口重放和冲突已测，缺真实任务 |
| UI | 通过，桌面 Chrome 核对两张旧卡播放、刷新、下载及哈希 | 未验证 | 未验证 |

判定：I7A、I7B 均未达到完成标准。真实模型能否修好整个推近区间、审阅并交付，须由后续授权的独立旅程验证。
