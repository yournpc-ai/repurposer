# I8 首片验收 · 2026-11-22

**有条件通过。** 两组独立上载素材、一次原素材回归完成了插图、局部播放、同对象平移与固定版本交付。两张同名附件的首次盲测选错目标并改写了原叠图。修复后同一对附件触发澄清，未写入。本页末尾单列收官复测，指定 QuestionDock 续行已通过。施工目标与 I8-0 审计见 [阶段合同](../../i8.md)。

## P0 · 数据库与正常入口

接手时本地与远端 main 均为 `419f39448a8abc099bf48673a799a8c249fe9dfb`，工作树干净。默认 Web 和 Renderer 已监听；API 的 reload 父进程占着端口，应用 lifespan 未成功，Worker supervisor 持续重启。API 在 `main.lifespan → require_current_schema`、Worker 在 `run_worker → require_current_schema` 均抛出同一首错。Postgres 已可连接。原库在 `j6b01_export_jobs`，代码要求 `j6d05_project_brief`。原因是数据库版本；重装包或关闭检查都无法恢复这些持久化合同。[完整脱敏异常链](dev-startup.txt)

在仓库根目录核对或执行的主要命令如下。URL 中的身份凭据从示例省略。复现时应使用该机器上的连接配置。第二段建库和升级是本次一次性操作。

```sh
git status --short --branch
git rev-parse HEAD
git ls-remote origin refs/heads/main
./scripts/dev.sh >/tmp/i8-dev-preflight.log 2>&1
docker exec repurposer-db-1 psql -U postgres -d repurposer -XAtc 'select (select version_num from alembic_version),(select count(*) from projects),(select count(*) from composition_versions),(select count(*) from outputs),(select count(*) from workflow_runs),(select count(*) from graph_nodes)'
```

```sh
docker exec repurposer-db-1 createdb -U postgres rep_i8_dev_1122
(cd apps/api && DATABASE_URL='<local asyncpg URL ending in /rep_i8_dev_1122>' uv run alembic upgrade head)
(cd apps/api && uv run alembic current)
curl --noproxy '*' -fsS http://localhost:8000/health
curl --noproxy '*' -fsS http://localhost:3001/health
```

用户选择保留原库，忽略文件 `.env` 仅切换 `DATABASE_URL` 的库名。原库仍是 445 个项目、429 个作品版本、235 个 Output、201 条 WorkflowRun 和 443 个 GraphNode；接手及收尾计数一致。未对它执行升级、导入或清理。启动器先做同款只读 schema 检查，冷起本地容器时等待 Postgres 就绪。原库下实跑启动器返回 1，保全了既有服务和错误日志。

切换后的默认入口使用现有 3000 Web、8000 API、Worker 和 3001 Renderer。Chrome 登录测试身份，读项目列表、详情、AgentThread 历史、v1 与保存的交付，读接口返回 200。预览播放、硬刷新后重播、成片 Lightbox 播放均观察到媒体时钟前进，页面异常数为零。导航取消过媒体和 Skills 请求。Renderer health 报告 macOS 隔离，真实 ExportJob 各认领一次。Worker 的支付告警接收人未配置。旧库私人作品的逐项读取、全栈 Docker 重建和停掉用户正在使用的服务再从零启动均未验证。本次复用已有端口；启动器在通过预检后仍有全机进程清理行为。[Chrome 与 API 回执](acceptance.json)

实际播放文件保留横图 v2 的模型观察窗口、横图 v3 的正式交付以及使用竖图的第二份正式交付。三者均为公开测试用合成素材。[插图后局部预览](landscape-v2-preview.mp4) · [左移后的横图成片](landscape-v3-output.mp4) · [独立竖图成片](portrait-image-v3-output.mp4)

## 五面与费用

样本使用可公开的合成 640×360、30 fps、6 秒动态视频，含 440 Hz 或 523 Hz 原声和原生字幕。横图为带标签的 220×120 PNG，独立竖图为 132×184 PNG。每个项目通过真实上传接口保存字节，v1 通过唯一写口预置。模型只收到任务、附件和应用上下文，v2、v3 由模型亲自操作。真实消息经 HTTP/SSE 提交，报价通过 Chrome 点击；API 诊断实例与默认入口共用独立库、实际 Worker、TOS 与 Renderer。正式导出均在用户设置要求批准后进行。未生成付费新素材。

| 样本 | Provider 请求 / 收到响应 | 版本与成片 | capture 积分 | 应用会话美元 |
|---|---:|---|---:|---:|
| 横图首次，普通编辑语言 | 13 / 12 | v1 → 插入 v2 → 左移 40 px v3，Output `4943e94e-37d9-5f00-96f0-4f828f0b4b47` | 12 | 0.013756 |
| 独立竖图首次，“画中画” | 13 / 12 | v1 → v2 → 同对象左移 40 px v3，Output `19575e9c-aaf2-5e4e-b5ea-fa7ecee35003` | 12 | 0.013526 |
| 同名附件、强杀、Stop 项目 | 17 / 17 | 强杀保住 v2。歧义首次误删、重插至 v4；修后提问留在 v4 | 0 | 0.021179 |
| 原横图成功样本修后回归，新项目 | 12 / 11 | v1 → v2 → 同对象左移 60 px v3，Output `7187c00e-151b-5cb1-9855-f2b57ee99106` | 12 | 0.012414 |
| 双图选择另发新 opening | 7 / 7 | 首问时仍 v1；带绿色竖图 mention 的新消息只插入该来源并播放 v2，原问题仍未作答 | 0 | 0.010970 |
| 双图 QuestionDock 首次 | 5 / 5 | 点击后错误请求生成图片，报价 2，未批准、无 MediaJob，仍 v1 | 0 | 0.008517 |
| 双图 QuestionDock 第一次修后复测 | 5 / 5 | 绿色选项已写回，但模型追问其用途，无插图、无预览，仍 v1 | 0 | 0.007423 |
| 合计 | 72 / 69 | 3 个正式 Job、3 个 Output，各 attempt=1 | **36** | **0.087785** |

- **Tool**　MiniMax-M3.1-Flash 实收封闭的 `insert_visual`，参数为项目固定图片 UUID、起止秒、角位、宽占比。样本按需 inspect / prepare，写入后使用真实对象 ID 续改。逐次调用、参数、Schema 和各轮工具集合均留证。[请求与 Token](model-requests.jsonl) · [Provider Schema](provider-tools.json)
- **Prompt / Context**　既有作品现在可准备素材和提问。项目内的两个同名 mention 以各自 ID、标签投影；与本项目无关的 ID 不入投影。去掉把一次视频 mention 自动指定为模仿样片的逻辑。已授权的固定成片续行仍只处理原交付。按观察窗口陈述结果；首个样本正文仍有“version_id 第 2 版”这类冗余措辞。
- **Chat**　沿用 Clean 的 Activity、问题、局部 Player、Output 卡和 Lightbox。三个首轮都播放了相关窗口，零正式导出报价。第二轮均对实际固定版本报价 12，批准后可见审片和交付，刷新保留同一张卡。主样本在默认 Web 实播历史窗口并播放了交付 MP4；同名图复测的真实 delta 与持久化问题有回执。未新增 Storyboard 或 Chat 状态系统。[历史消息、窗口和交付](acceptance.json)
- **Execution**　`BindSource / AddTrack / AddClip` 由一次 `apply_composition_edits` 落版，第二个工具只改该对象的变换。检查三个项目的 v1/v2/v3 原轨、字幕、场景、设置和来源。每份下载成片与 v3 同规格预览共 180 帧，逐帧 RGB 平均绝对差的最大值均为 0。与 v1 比较，窗外及底部字幕区域平均差均低于 0.45/255；在第 60–119 帧能检测到产品图，前后相邻帧均退出。解码、单声道 48 kHz 重采样后与 v1 音轨相关系数均为 1。已保存 SHA-256、预览、版本与 Job 引用。合成音轨的客观保持已验证，主观听感未验证。[媒体测量](acceptance.json)
- **Recovery / Replay**　在独立 API 中调用真实编辑函数，保存事务返回后、生成 ToolObservation 前向本进程发 SIGKILL。另一实例读取历史两次，原 opening 收敛为 failed，已提交的插图 Activity 为 completed，仅一条“插入图片（版本 2）”恢复说明。相同调用重放获原 v2，未新增轨道、Job 或费用。早期 Stop 在可见边界为空时撤回 opening，历史零残留。最终业务树又对三个成功工程的六个真实调用进行重放，均返回原版本。[恢复与 Stop](acceptance.json) · [最终重放](final-replay.json)

应用账本共 538,242 输入、11,749 输出、224,824 缓存 Token。上述美元数沿用 conversation_usage；执行强杀、取消或续行时并非每个请求都能回填该表。逐请求用量已回传的 69 项按仓内费率合计约 0.100522 美元；3 项缺最终响应，不能填零，也不能将两种口径相加。72 是本轮已捕获的诊断请求数，未取得供应商账单、存储流量与本机渲染的货币成本。测试账户使用应用原有授信，3 笔 hold、release 和 capture 均可按账号核对。导出次数已到约定上限。

## 首错、复测与边界

| 项目 | 结论 | 证据与限制 |
|---|---|---|
| 两张同名图、用户要求唯一目标 | 首次未通过；复测通过 | 首轮 Provider 没收到本轮点名清单。模型准备多个资产后 remove_clip / insert_visual，违背“其他不变”。修正项目引用投影后，对同一对实际附件及原句返回 ask_user“2–4 秒要放哪一张产品图？”，无新增编辑。复测起点是保留首错的 v4；另一个干净工程确认首问零写入，随后通过新 opening 加明确 mention 成功选择绿色图；该调用不经过 Dock answer，旧问题行仍未结算。跨模型重复率未验证。 |
| 收官前的 QuestionDock 点选后续行 | 两次浏览器实测未通过 | 首次测量脚本本想选绿图，却匹配了描述含“竖版”的粉色选项。应用收到的合法点击是粉色，应插入粉图，却请求另生成封面。原 opening 时间和素材约束丢失。修复 service 恢复上下文，改用明确绿色选项复测，模型仍重复询问。逐请求发现 ToolLoop 有 dialogue 时会丢弃 opening_text，在 project_reply 下只发送最后一条用户发言。最终在 application_context 投影已持久化 opening 的原请求、问题及已选择项，保留原附件/mention 与最后用户发言。定向 Provider 载荷验证覆盖流式和非流式；出现重复异常后停止付费复测。两笔均无 MediaJob、ExportJob 或 capture。 |
| 误选对象、重复插图、第二轮改错对象 | 有条件通过 | 两组独立单图均选中指定素材，只插入一次并左移同一对象。真实重放、不同调用同参的独立对象身份和错误重放拒绝分别验证。歧义首次失败单列。 |
| 字幕遮挡、原声丢失、生成 MP4 未达标 | 有条件通过 | 三个已交付样本均检查实际字幕带与音频。刻意遮住字幕后模型能否持续发现、修复并如实交付，或不达标时能否拒绝宣称完成，未验证。 |
| 版本冲突、Stop 后续写、刷新不一致 | 有条件通过 | Postgres 定向测试使用两个独立事务竞争同一 base，只有一方提交；异参 replay 被拒绝。真实空边界 Stop 后重新读取历史为零行，成功样本硬刷新保住版本与交付。双浏览器同时对同图写入、中途付费拒绝和所有设备一致性未验证。 |
| 只要预览即出报价、重复扣费 | 通过 | 3 条首轮无报价；第二轮各 1 次真实报价、许可、Job、capture 和交付。无索取额外额度。 |
| Dev 和验收工具首次错误 | 有条件通过 | 原库 schema 阻塞及修复见 P0。首个诊断客户端通过系统代理访问 localhost，返回 Connection Closed；对 loopback 配置 NO_PROXY 后正常。临时 5173 端口页面刷新等待超时，默认 3000 后续重播成功。Stop 初版观测脚本错误地要求撤回后保留用户行，依真实 retracted 语义重测。 |
| 定向与回归 | 通过 | 早期 2 个 Provider 断言失败：已授权续行意外暴露 ask_user，修复实际投影；旧断言检查 Prompt 中的 create_video 拼写，改验 Provider Schema。新增 mention 断言后测试 helper 一度未接参数，修正后完整 core 通过。默认 Home 在完成 hydration 并跳过真实引导后，示例填入 MentionEditor，未请求 Persona。Web 的 tsc、42 文件 340 项与生产构建通过。末次旧上传凭据和旧 overlay wire 清理后另行执行全 core，并对既有真实调用重放。 |

运行命令为 `(cd apps/api && uv run --extra dev python -m pytest test/core -q)`、`(cd apps/web && pnpm exec tsc --noEmit && pnpm test && pnpm build)`、`bash -n scripts/dev.sh` 和 `git diff --check`。遗留 SQLAlchemy 连接回收及 Pillow 弃用警告已记录；QA 解码程序同时加载 PyAV 与 OpenCV 时有 FFmpeg 动态库同名提示，三次完整解码均返回测量。QA 测试期间的 Provider 凭据、登录令牌、签名媒体地址和原始请求正文未进入仓库。

## QuestionDock 收官复测

**指定旅程通过。** Chrome 实际上传两张同名绿色 PNG，一张横版深绿 LAMP 08，一张竖版亮绿 LAMP 12。用户原话为“把第 2–4 秒加入我提供的绿色产品图片，保留字幕和原声，做好后播放。”测试夹具提供带可闻音轨与原生字幕的六秒 v1；随后开场、上传、选择、播放、刷新均使用真实 Web，未注入回答或伪造 HTTP 响应。测试浏览器将同一开发 Web 的 API 请求发向启用脱敏取证的本地 API 实例，共用独立 Dev 库、真实 MiniMax、存储及 Renderer。

| 本次新项目，按发生顺序 | 结果 | 模型请求 / 响应 | 应用会话美元 |
|---|---|---:|---:|
| 首测 `4bf2f8f0` | 未通过。两图都符合，问前将窗口拆成两个一秒片段，两次插图。原始 v1–v3 保留。 | 4 / 3 | 无落账行 |
| 附件投影修后 `82de1a2b` | 未通过。正确选图，v2 只写一次；实际播放 0–6 秒。点击后现场缺预览，刷新才显示。 | 7 / 7 | 0.011401 |
| 跨刷新续行 `909bfe53` | 通过。测量脚本试建第二标签页失败，后续在已持久的同一问题恢复；现场和硬刷新均播放 2–4 秒。 | 7 / 7 | 0.010797 |
| 不中断复测 `2f38c10c` | 未通过。点击与刷新一致，插图为 2–4 秒，模型为预览增加了前后各半秒。 | 7 / 7 | 0.010884 |
| 最终不中断复测 `69174ffe` | 通过。只选亮绿竖图，保存唯一 v2，现场与硬刷新只播放 2–4 秒。 | 7 / 7 | 0.010928 |
| 独立早停 opening，复用首测项目 | 通过。收到 turn.started 后 Stop，opening 撤回，历史零行，仍为三版。 | 1 / 1 | 无落账行 |

这些是同一组素材的故障复现与回归。前面七个历史样本及三次正式导出的分母保持原值。

- **Tool 与 Context**　首错发生在开场决策。模型看到两个相同的附件名，但项目资产列表没有标明用户附件顺序。现在服务端按实际上传顺序投影项目内 Asset ID，准备结果带来源 Asset ID。写前的歧义通过持久问题结算。续行 Provider 实收原话、问题、选项文字、两个 Asset ID、v1 与费用范围。可在 12 秒内直接播放的已改 Clip 随当前版本提供精确的 `preview_range` 参数，渲染端仍校验实际窗口。
- **Chat**　答案 HTTP 携带问题 ID 与 `option_id=a`。终帧带 v2、2–4 秒与原 opening。修复回答终帧对账时的时序，先核对活跃回合，再按本次问题与正文键提交 React 更新。最终样本实播两次，刷新前后各一个播放器、八条相同顺序的成功回执、零待答按钮。[待选择](questiondock-question.png) · [点击后播放](questiondock-live.png) · [硬刷新后播放](questiondock-reload.png)
- **Execution**　v1 `b5756071` → v2 `86e6c4f2`，唯一新 Clip 固定到所选 Asset 的快照 `23a819e4`。原两条轨道、场景、设置和已有来源逐项相同。核对发给 Provider 的真实窗口 MP4 与相同时间段的 v1 渲染，共 60 帧，字幕带平均绝对差 0.388/255，48 kHz 单声道解码相关系数 1.0。先前 Output `4943e94e` 经授权重新读取，文件 SHA-256 与历史验收一致。
- **Recovery**　另一真实标签页再点同一选项，SSE 返回 `question.already_answered`。重放实际 insert_visual 调用返回原 v2；版本总数仍为二。早停单列。另在当前代码读了两次旧强杀样本，均只返回原恢复行；本次没有重新执行 SIGKILL、双浏览器同时写或全栈冷启动。
- **费用**　本次共 33 个请求，32 个有响应，已知 306,937 输入、6,044 输出、115,879 缓存 Token。应用会话账本合计 0.044010 美元；含首错和 Stop 的已回传请求按仓内费率估计 0.049667 美元。两者口径不同。一个请求无最终回执，供应商最终账单未验证。所有本次项目均无 MediaJob、ExportJob、新 Output 或媒体积分扣款。[逐请求 Schema、上下文、调用、版本、回执与账本](questiondock-evidence.json)

最终业务树的 API core 477 项、Web 340 项、TypeScript 检查和生产构建通过。历史素材、强杀、并发及上线风险仍按原证据范围登记。此处仅关闭指定双图旅程。
