# 原生 export_video 接管与验收

2026-11-21。在隔离环境中，真实 MiniMax、API、PostgreSQL、Worker、既有 Renderer、私有对象存储和 Chrome 已完成接缝与片尾卡两条链路。**功能闭环已跑通。新加坡 TOS 上线验收待建桶。** 表内积分均为应用账本值。

## A · Git 与施工范围

在现有 main 施工，核对起点和远端为 fdd21443bed58a8b3a1eea1f7322d501e27f5e91。6A 审计提交为 31c673505d6230a2eb5dd4e8a02e92b24b83499e。6B 变更涉及原生工具、版本依赖、队列、计费、Chat、Renderer 上传、Output 播放、数据库新增表以及配置。没有迁移旧 Output 或改写历史账本。保留了用户在 .dockerignore、主合同及未跟踪文件中的既有修改。Git 交付状态见随报告提供的 git.txt。

## B · 执行路径

旧路径把 export_video 改写为 produce_video TaskItem，经 submit_confirmed_tasks、create_run、compile_graph 创建 Run 和生产 Step。随后 Output 又有一次独立渲染领取，Render Step 镜像和 Run 完成事件参与费用与续行。一个文件因此受到两套执行身份影响。

现在工具检查固定版本、媒体依赖、实际预览和费用授权，持久化 ExportJob。Worker 只负责按冻结规格渲染、上传及解码校验。成功事务写入 Output、账本和工具回执，Agent 在原 opening 上决定 review_video 与 deliver_video。原生入口的 TaskItem 转换和编排器上的 export_receipt 特例已经删除。两例在最终隔离库中均没有 WorkflowRun、WorkflowStep 或 Render Step 镜像。[原生调用和执行结果](native-and-recovery.json)

## C · 三项首错

| 原失败样本 | 最早可定位的错误 | 原始账本和结果 |
| --- | --- | --- |
| 接缝 | 真实预览与 v2 已保存。Step 领取以 PostgreSQL now() 记时，同一 Worker tick 的过期回收以宿主机 UTC 减 900 秒比较。宿主机实测领先 23,699 秒。单 Worker 用原函数领取后立即被回收，旧 token 写入命中零行。 | 两次 Run 领取 262、647 次。各 hold 16、全额释放，零 capture、零 Output。 |
| 图片标题与片尾卡 | v3 已保存。同一时钟混用使合法 Step 失去执行权。claim 没有限制被 reap 后的重新领取次数。 | 两次 Run 领取 239、508 次。各 hold 13、全额释放，零 capture、零 Output。 |
| 固定旁白 | 供应商原音已固定，VideoNarration 为 done，有 trace、26 个字符的用量和四份同 digest 快照。独立事务保存原音后，旧 Step 无法可靠提交 Run 结果。 | 671 次领取。hold 3、释放 3、零 capture。没有重发 TTS 或追扣。 |

两端均按 UTC 比较，实测差值来自时钟。历史未逐次记录 token 或 Worker PID，因此无法还原首次换权的具体进程和时间。启动全扫会撤销其他 Worker 的活跃旧 Step，领取也只排除 cancelled Run，这两处均为独立缺陷。保留原始取证和消费者表。[6A 审计](README.md) · [数据库与重现](audit.json)

## D · ExportJob 与固定来源

- 原生 call ID、opening、参数指纹和用户授权保存在现有消息中。Job 钉住项目、版本、包含 digest 的 video-spec、费用上限及回执。Job UUID 同时预留唯一 Output ID。新增表不复制作品、媒体或钱包。
- PostgreSQL 行锁和数据库时钟授予 claim_token、45 秒租约和心跳。最多领取三次。按入队时间调度，同一 owner 同时最多一个有效执行者。全局 32 个未终结请求，每个 owner 最多 4 个。API 读历史与重新签名均独立于 Worker。
- Stop 和成功提交争用同一 Job 行。成功在同一事务释放预占、以原账本幂等键 capture、落 Output 与回执。已上传的同键不可变对象经过重新探测即可恢复。接缝恢复后模型又发了一次 export_video，获返已有回执，没有再入队、扣费或交付。
- 新成片的持久地址包含实际桶和键，形如 `tos://<private-bucket>/private-exports/<owner>/<project>/<output>.mp4`。签发时同时核对 Output、项目、owner 及预期地址。历史消息保存 Output 身份。浏览器播放、续签和下载直接读取对象存储，封面在同一私有桶。默认有效期 300 秒，过期验收配置为 5 秒。
- 清点了 9 个含 speech 和 18 个含 generator 的当前作品中的 37 个片段。已固定的原音、对齐和生成物可复用。4 个旁白片段涉及 2 个已确认生成的 digest，但在开发库配置的存储中未找到可读原件。关联的 3 个历史成片也未能在该配置下验证。未修改这些作品、触发替代生成或判定文件永久丢失。[逐项来源清单](source-audit.json)
- 缺失依赖会在创建 Job 和 hold 前返回类型、片段及可用操作。Agent 可以使用现有媒体工具，经过账户授权后用 bind_clip_source 将拥有的快照以 CAS 绑定到新版本。实测待生成图片返回未就绪、零 Job，绑定现有真实图片后成功导出。此项覆盖固定媒体复用，付费媒体执行全面迁移属于 6C。[固定来源验收](fixed-dependency.json)

## E · 五面证据

| 面 | 验收结果 |
| --- | --- |
| Tool Call | 捕获 MiniMax 实际可见的 export_video 空参数 schema、原生调用 ID、参数及回执。 |
| Prompt / Context | 原版本 digest、实际 preview_range 结果、固定 Output 和续行事实进入模型上下文。两例实际模型系统消息中没有 WorkflowRun、WorkflowStep 或 compile_graph 字样。 |
| Chat | 排队取自入队，渲染、上传、校验由持有有效 token 的 Worker 在对应动作开始时写回执。完成与失败保存在原回执。两例各一张交付卡，均能硬刷新播放。 |
| Execution | 所有者、固定版本、video-spec、解码帧数、文件 SHA-256、账本与 Output 对齐。 |
| Recovery | Stop 先赢时释放且无成片。成功后 Stop 保留原输出。验证过期旧 token 被拒、同参重放、异参拒绝、双 Worker、限次、API 与 Worker 强杀。 |

[调用与恢复](native-and-recovery.json) · [播放器](private-playback-local.json) · [队列和限次](bounds.json)

## F · 十用户并发

第一组在原事件库的隔离副本中并行执行导出、Stop、即时编辑、CAS 竞争、短预览和越权读取。入队后约 0.35 秒保存新版，原版在约 3.89 秒完成。两次正式导出均绑定各自原版本，一人 Stop 后其他人继续完成。两次竞争编辑分别为保存和 StaleBase。[混合操作矩阵](concurrency.json)

第二组用 10 个独立用户、2 个 Worker 实际导出 10 个短成片，每个 Job 领取一次、每个 owner 一次 capture。随后 10 个独立 Chrome 上下文并发播放，10 次跨用户签发均为 403，匿名对象读取均为 403，授权下载返回真实字节。队列实验另验证每个 owner 的第五项在 hold 前被拒，三次过期后终结，零 capture。十人组使用生产工具函数和真实服务，每人未重复购买一轮模型对话。[十用户应用层](private-application-local.json) · [对象读取和过期](private-storage-local.json)

## G · 真实成片与事故恢复

| 作品 | 保存版本 | 解码 / 规格 | 应用实扣 | 输出 |
| --- | --- | --- | --- | --- |
| 原接缝 | v2，c2c66f86-1232-4843-873e-9d06a1cb07c2 | 240 / 240 帧 | 16 积分 | [接缝 MP4](seam.mp4) |
| 原图片标题与片尾卡 | v3，f772f104-24b5-4125-93f0-583c37807bba | 188 / 188 帧 | 13 积分 | [片尾卡 MP4](endcard.mp4) |

接缝在私有 PUT 成功后、probe 和数据库回执前实际 SIGKILL Worker，随后 SIGKILL 正等待的 API。恢复后第二领取复用同一对象，以前一 token 尝试写回被拒。原 Agent Turn 完成审片，最终一张卡、一次 capture。片尾卡首次领取完成。两例均实测浏览器旧地址 403，自动重新签发后可播放，硬刷新后仍指向原 Output。

初次功能验收使用旧路径的测试对象，另对历史 Output 83883407-0efb-4200-82c7-69930eb46476 完成硬刷新回放，解码 128 帧。[历史播放验证](playback.json) 共享 PostgreSQL 与 Docker 管理接口随后超时。最终私有链路在独立 PostgreSQL 中按原始 trace 恢复两个作品，逐项比对真实源文件 SHA-256、版本 ID 和内容 digest，使用真实 Renderer 与回环 MinIO 的签名网络读写。私有导出的两个成片与初次验收逐字节一致。仅保存一份样片。

## H · 云端边界和后续施工

现有 repurposer 桶无条件向通配主体允许对全部对象执行 GetObject。已核对新加坡区域端点与候选名。创建 repurposer-private-exports-sg 返回 403 AccessDenied，再列桶时该桶不存在。原历史桶策略和历史对象未变更。云端匿名拒绝、可播放签名、真实 TOS 签名过期及续签仍待新桶验证。[TOS 实际返回](cloud-bucket.json)

推荐由管理员在 ap-southeast-1 创建该私有标准桶。服务身份需要读取其 ACL 和桶策略、在私有成片命名空间读取和条件上传对象，并按既有删除功能列举与删除相应对象。也可以给施工身份授予创建桶的权限，两者都可避开修改历史桶。完成云端验证后再为 API 和 Worker 配置 S3_PRIVATE_EXPORT_BUCKET 并上线。现阶段私有存储未就绪会在费用预占前结束。火山引擎按存储容量与时长、请求、流出流量等计费，本次建桶请求未成功。[官方建桶权限](https://docs.volcengine.com/docs/torch-object-storage/creating-buckets?lang=zh) · [官方计费说明](https://docs.volcengine.com/docs/torch-object-storage/storage?lang=zh)

PrepareNarration、PrepareMusic、PrepareVisualAssets 仍由旧系统执行。历史已提交 Run 的结果读取、非原生制作的 render mirror、Run 完成协调仍有消费者。保留现存历史 FK 和独立的资产、旁白对齐、发布、支付告警与清理队列。6C 需要处理媒体生产恢复、Unknown 保护与旧回收器，6D 须逐个移除最后的真实消费者。未处置旧账本中无法归属或尚未释放的资金。

最后还以原生启动命令运行未替换的 API、Worker 和 S3 客户端，仅用环境变量连接独立 PostgreSQL 和本地两个存储桶。两名用户再次从原生工具导出、签名播放和下载成功，跨用户被拒。[原生客户端复核](native-client-smoke.json)

本轮回归共 512 项 API 核心测试与 411 项 Web 测试通过，Web 和 Renderer 的 TypeScript 检查通过。并发验收期间有一次 Chromium SVG 栅格化测试超时，独立全套复跑通过。
