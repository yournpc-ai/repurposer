# I8 冻结候选验收 · 2026-11-23

**裁决：I8 整体未通过，暂缓合并。** 同一作品完成插图、同对象左移、定版导出、断进程续行与交付。交付后的下一句“结尾再留半秒，其他保持原样”产生了一版用户没有要求的黑底字幕片尾。旧成片和单次收费均保持正确。

## A　Git、平台与环境

验收时的本地 main 与 GitHub main 同为 `ab2360cbc544c1097a330f2e4e591c542f7959ba`。归档提交 `11a733fe507dcac023b70d36f28ca2d5f407bc50`，基线 `ec02b02d421d2fb6cfe237c2d94966fa7f3cc7c8`。在普通临时目录将归档 diff 应用到基线的文件副本，11 个目标逐字节等同工作树。diff SHA-256 为 `41961bef82ce3049847dfae2ab97bf16a55c598bc48dc068076ac81dc65b68c5`。Remotion 补丁 SHA-256 为 `2a914fa1fa9c60887f1bd370040872c062f92303a7b00555e8b5a9b689472713`。

候选包含 render Dockerfile、artifacts.ts、artifacts.test.ts、audio.ts、video/index.ts、web Dockerfile、PROGRESS.md、RENDERING.md、pnpm 锁与工作区配置，以及新增的 4.0.484 patch。另有声音听评 REPLAY.md 修改和 upstream-4.0.540 下 25 个未跟踪研究文件。均予保留。原有 iteration-4、iteration-5 worktree 保持原状。暂存区为空，git diff --check 通过。没有生产代码提交、推送、合并、上线或数据库迁移。本目录保存可复核的验收证据。逐文件名见 [Git 清单](git-files.txt)。

[GitHub ARM64 作业](https://github.com/yournpc-ai/repurposer/actions/runs/45071746435/job/137360023691) 的实际日志和工作流步骤均已复核。两镜像构建通过，24/25/30 fps 分别为 191/199/240 帧，382000/382080/384000 有效采样。630 帧时间戳、源帧、三声部、尾段、AAC edit、25 fps 动态响度、30 fps 并行预编码和短窗拒绝符合既有断言。冻结文档里的 Linux 待验文字已过期。为保持签名现场，未改写归档及候选所含文档。[日志摘录](arm64.txt)

本地 Darwin arm64 默认 3001 虽健康，已装 CJS 和 ESM 文件与候选不同。另行 frozen install 锁定 4.0.484，实际 CJS 为 7214406b…，ESM 为 149686a7…，均匹配镜像内检查。隔离 API、Worker 使用同一份本地源码，Renderer 23001 从候选副本启动，Web 23000 从候选工作区独立构建。PostgreSQL 25966 空库迁移到唯一 head j6d05_project_brief，API lifespan 完成；独立回环 MinIO 承载测试素材、固定快照与导出。没有借用旧用户对象。fixture 为合成六秒 30 fps 测试视频、440 Hz 源音、可编辑文字轨“STUDIO LAMP”和用户上传的固定图片。fixture 止于 v1。注册表含 uploaded_video_editing、promo_p1_revision 等场景；本轮从既有 I8 fixture 经正常 Chat/SSE 发送指定原话。

只读登录部署手册指定的服务器，实测 Linux x86_64、Ubuntu 22.04.4、Docker 29.2.1。Renderer 镜像 ID 为 sha256:2fd33fec64b956360578b31ddc8b84218ccb44be9038e5e8cdbf39fade46f4b1，Node v22.23.5、Remotion 4.0.484，CJS 文件哈希 73adbc93…，仍为原安装。使用本轮临时 SSH 主机记录首次接收主机键，未独立核验运维指纹。维护窗口、可恢复的旧缓存卷及生产排空均待确认。[只读回执](production.txt)

## B　同一条 Chat 的五面证据

Project 494bbe0c-73d9-4885-9100-1493c80ecaa4，Conversation 26cb8ec0-2e91-4322-9726-cfb9f488f9dd，Composition e89a8226-4429-42fe-8fe7-a2326c116a40。四条用户消息各有自己的 opening。批准与恢复沿用导出 opening。原始模型输入及参数在私有本地 provider.jsonl；可读的 Schema、请求身份和参数在 [Provider 清单](provider-calls.json)，版本、Activity、Job 和交付在 [持久事实](facts.json)。

| 面 | 真实证据 | 首错或限制 | 裁决 |
|---|---|---|---|
| Tool | 首请求实际发出 29 个原生 Schema。模型自行 inspect、prepare、insert_visual、translate、preview_range。写入工具沿 edit_clip → apply_composition_edits。已授权续行投影收窄到固定交付。无 create_video 或重复插图 | 导出先被观察门拒绝一次；第四轮选错可延长的对象。现役日志名 intent_router，源码沿既有 call_loop；候选没有新增决策器 | 未通过 |
| Context | trace 含项目内图片 mention、当前版本、用户原话、窗口和返回观察；双图问答正确选回第二张；恢复请求读固定 Output | 知道主片是视频、来源有界且 extend_still 只支持静态片，仍将字幕当成片尾替代。未见跨项目引用成功 | 有条件通过 |
| Chat | SSE 活动对应真实回执。390×844 与 1280×900 Chrome 均从 Chat 打开两个窗口并播放，刷新后播放器时钟再次前进，Output 卡可播 | 主旅程首两轮在 HTTP 客户端尚无观看动作时即称“已播放”；第四轮通用停止正文遗漏已保存的 v4。模型审片只覆盖所见样帧 | 未通过 |
| Execution | v1→v2→v3 的对象、快照、位置、原轨与媒体已核对。v3 正式片与全长预览 180 帧解码画面 MAE 0，48 kHz 有效窗口 288000 个采样，原基准与成品同窗音频相关系数 1.0 | v4 只延长字幕和场景；新增 15 帧的主画面全黑。声音验证限于该固定测试信号 | 未通过 |
| Recovery | 在真实编辑提交后和已导出但未交付两个边界 SIGKILL 专用 API。原 opening 恢复、同 call 重放、Stop、单次收费与历史下载均已核对 | fencing、过期 base、未知上传及竞争顺序另跑隔离 DB 定向测试；没有在生产对象存储制造 Unknown | 有条件通过 |

## C　用户旅程

| 原话 | opening、决策与实际结果 | 达成情况 |
|---|---|---|
| 把第 2–4 秒加入我上传的产品图片，保留字幕和原声。做好后播放这一段给我看。 | 6a8a7297…；v1 3cbb2e17… 经 call_17faa5747c0a45eda3309d34 保存 v2 ca436c97…，一次插入、一次 2–4 秒预览。原轨、场景和已有来源保持 | 编辑和播放卡通过；已播放的陈述超前 |
| 图片往左移一点，其他不变，再播放这一段。 | 0abc7c85…；call_g6FZKZSlWjMc2OZNCzK2ayy7 将同一 obj_overlay_989ef066f37b5562968e2686e67d4c34 的 x 减 40 px，得到 v3 4682cc68…。2–4 秒范围以及图像大小、字幕、来源均保持 | 同对象修订和播放卡通过 |
| 这样可以，导出正式视频。 | b2498b9a…；首个 export_video 被观察门拒绝后，模型预览 0–6 秒，再次请求导出。批准原问题 997e5e05… 的 12 积分报价，固定 v3 digest 55c9391860bf66cd7885211ce546717d01649d95a1b65d61cb3c4af9013002df。仅一个 Job/正式 Output 7a47ca27-0e05-5a2c-94aa-98d51893eee0，attempt=1。成功回执 3e82f87c… 后强杀；Worker 沿原 opening 审阅并交付，卡消息 53c900fc… | 通过。下载 SHA-256 与上传回执及交付消息一致。字幕带相对 v1 平均像素差 0.287/255，窗外 0.424/255 |
| 结尾再留半秒，其他保持原样。 | d97f317a…；主视频的 extend_still 与越界 trim 均被拒，模型改对 clip_caption 调 extend_still，形成 v4 2c22736a…，digest d8a4bd9c…。场景与字幕从 540000 延长到 585000 tick，主片与原音仍在 6 秒结束。实际渲染 5.5–6.5 秒，前 15 帧主画面平均亮度读数约 124.65，后 15 帧字幕上方像素最大值 0。之后的 trim 再次被拒。没有新导出 | 未通过。Chat 仅笼统说未完成。旧 v3 再次下载仍为相同 SHA |

[v1 对照视频](main/v1.mp4) · [正式 MP4](main/output.mp4) · [媒体测量](main/quality.json) · [v4 片尾实物](main/v4-tail.mp4) · [片尾读数](main/tailcheck.json) · [桌面](main/desktop.json) · [移动视口](main/playback.json)

## D　首次偏差、修复边界与复测

| 样本／首个偏差 | 模型输入与实际动作 | 归因与处理 | 复测 |
|---|---|---|---|
| 首测 eaf9afaf… 真实预览失败 | 正确写入图片后，渲染端读取隔离桶固定字体返回 403 | 测试桶未向回环 Renderer 开放所需素材读取。修正测试桶 | 原样本留证，在新项目复测通过插图 |
| 复测 498f4c41… 中断 | v2、v3 及两张精确窗口卡已产生 | 本机重启；将验收库放 RAM 卷导致持久状态丢失，原 SSE 与 Provider 记录保留 | 使用独立磁盘库重建为本报告主项目。没有拼接不同项目为一条成功旅程 |
| 双图选择器中断 | 模型展示可区分的 LAMP 08 横图与 LAMP 12 竖图，写前只有 v1 | 浏览器探针宽松匹配“12”，也匹配了横图尺寸 220×120。修正取证选择器；前一环境还有标签页创建错误 | 刷新同一持久问题、点选 LAMP 12。唯一 v2 快照 digest 与上传竖图 e21f1e49… 一致；Live 与禁缓存刷新均播放 2–4 秒。旧页重复点击返回 question.already_answered。属于跨刷新续行样本 |
| 主旅程播放探针超时 | 单次抓取的 video 元素未观测到时钟前进 | 独立保留超时。复测在窗口可见时分别采集卡内实际媒体的 readyState、paused 和时钟 | 两个窗口、刷新前后、两种视口均有时钟推进；正式文件在 Lightbox 中推进 |
| 第四轮首次不适用的调用与首个错误写入 | inspect_clip 已提供主视频身份，extend_still(clip_main, 0.5) 被明确拒绝。随后错把 snapshot ID 用于资产检索；重复准备原视频返回 snapshot identity collision。extend_still(clip_caption, 0.5) 成功，后续越界 trim 被拒 | Agent 选择了错误目标，写口接受了合法的字幕操作；停止回复未还原实际写入。最小修复应先使片尾静止可延长性区分叠加字幕与承载主画面的片尾元素，并让停止回复列出本 opening 已提交版本和实际影响。无法保留用户指定画面时，明确说明能力限制 | 尚未修改产品或复测该修复。验收应允许如实停止且版本不变，或证明新增半秒确实保留片尾主画面、其余部分保持 |

## E　费用、可靠性与证据范围

MiniMax-M3.1-Flash。两次环境共有 59 个记录的模型请求与 59 个响应，542263 输入、11828 输出、275201 缓存 Token；仓内费率估算 US$0.08843625。持久盘这次 39/39，主项目四轮分别 5、4、8、11 个具备该 opening 身份的请求。主项目应用会话记录 US$0.041167，双图 US$0.010877，合计 US$0.052044。重启前环境 20/20，其 DB 成本总额无法复原。上述费用口径分别报告，供应商最终账单未核。测试账户获授权，费用门设为询问。没有额外媒体生成批准或 MediaJob。

持久库共有 3 个项目、8 个作品版本（含 3 个 fixture v1），主作品共 4 版。一条正式 ExportJob、一次认领、一个正式视频 Output、一张交付卡。另有一行素材分析结果。账本有 hold −12、release +12、capture −12，净扣 12，正式 Job 重试 0、重复扣款 0。两个测试钱包开户各 grant 1000。正式请求没有未知上传终态。保存、审阅、交付及用户观看分别有自己的回执。

独立编辑故障样本在 insert_visual 保存 v2 后断开，历史接口两次读取都只有一条恢复说明，原 call_16e1df50f290ebf12c7b9304 同参重放返回同一 v2。随后的独立 Stop 在 turn.started 后撤回，仍为两个版本。导出中断通过同一主项目的真实付费批准完成。定向 API/DB 13 项、Renderer 缓存 4 项通过。DB 竞争用例采用受控外部回执。并发生产 Worker 与存储供应商的 Unknown 仍需生产切换前核账。[编辑恢复](fault/replay.json) · [Stop](fault/stop.txt) · [导出断点](export-boundary.json) · [双图问答](dock/browser.json)

## F　协作边界与切换条件

MG C 保持受控研究，Sound Recipes 保留研究与用户听评结论。Landing、Persona、支付及生产源文件未改。既有不可变版本、单写口、Native ToolLoop、Worker、Job 与交付身份足以支撑前三轮；第四轮问题在目标选择与停止回执。本轮没有引入新的编辑引擎或修改 AAC。4.0.540 未接入。

正式切换前须在独立 Linux amd64 环境用同一候选镜像复核锁、补丁、固定时钟、源帧与短窗拒绝；记录新旧镜像及卷身份、回滚负责人和窗口。暂停新导出后保留原实例和原卷，在 24 小时保留期内按 ExportJob、upload_id、对象 key、Output 和 hold 清点。原 Renderer 完成已 prepare 的上传。结果未知时按原身份 HEAD 核对对象元数据及摘要，保留预占。遇到缺件、缓存 miss、重复记录、无法对账或旧任务未排空即停。清点通过才把新任务指向新实例和独立缓存卷。回滚同样先停止接纳新任务，两代服务分别排空自己创建的成品，再恢复旧路由。历史 Output 与原账本保留。

## G　分项裁决

| 项目 | 裁决 | 边界 |
|---|---|---|
| Renderer 技术正确性 | 有条件通过 | 签署 macOS、Linux ARM64 固定媒体与实际 Chat 导出。另有源码复核风险：基线 ffprobe 进程失败或 JSON 解析失败会产生普通异常，外层只重新抛出 InvalidAudioClock，可能将未经确认的基线当作可用回退。应验证探测故障不发布；该分支本轮未注错 |
| Chat-Origin 五面 | 未通过 | 第四轮发生错误写入并漏报；主链前三轮交付成立 |
| 旧 Output／费用／恢复 | 有条件通过 | 同一旧文件、两处真实断点、Stop 与单次结算已核；生产排空和在途 Unknown 未演练 |
| 生产合并准备 | 未通过 | 先关闭第四轮目标与回执缺口，补基线探测失败边界证据，再审候选身份 |
| 生产部署准备 | 未通过 | 生产为 x86_64，仍运行未打补丁的旧镜像。目标架构验证、排空、维护窗口和回滚条件未齐 |
| I8 整体收官 | 未通过 | 本轮停在架构裁决，等待签收决定 |
