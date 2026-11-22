# 路线 B 生产候选复核

完整 diff 相对本地与远端基线 `057dca75d0de510f631fa03d82d35599b1b68ce2`，包含原先未提交的三文件候选、生产补丁文件与本轮接线。已在基线文件副本应用该 diff 并逐字节对照。本次提交仅发布研究归档。生产候选保留在工作树，供架构评审。

**评审结论：macOS 时钟通过，正式合并验收仍受阻。** Linux 三件作品和两个实际镜像的 frozen install 均未验证，Chat-Origin 五面尚未执行。

|作品|macOS 证据|有效采样|声部和尾段偏移 / 内部 PTS 间隙|相对原 4.0.484 的源帧、逐帧 PTS 与视频包差异|Linux ARM64|
|---|---|---:|---|---|---|
|24 fps / 191 帧|本轮复跑|382,000|0 / 0|零|BLOCKED|
|25 fps / 199 帧|复用同版归档|382,080|0 / 0|零|BLOCKED|
|30 fps / 240 帧|复用同版归档|384,000|0 / 0|零|BLOCKED|

- [完整候选 diff](candidate.diff) · [文件摘要](SHA256SUMS)
- [本轮 24 fps 原始测量](confirm24.json) · [MP4 edit list](confirm24-boxes.json) · [字节相同的已归档成品](../backport-4.0.484/media/24-loudnorm.mp4)
- [三作品与四出口时钟](../backport-4.0.484/evidence/clocks.json) · [两次缓存排空回执：生产 v1](drain-final.json) / [早期 v2](drain-provisional.json)
- [Renderer 实装文件比对](verified-render.json) · [构建检查](build-checks.json) · [Renderer 镜像失败记录](docker-render.log) · [Web 镜像失败记录](docker-web.log)

## 安装、运行与时钟

macOS 独立目录使用与 Dockerfile 相同的锁、声明及补丁，分别对 Renderer 与 Web 运行 pnpm 10.20.0 的 filtered frozen install。Renderer 安装的 653 个发布文件中，只有指定 CJS/ESM 的 adelay 表达式发生改变。新安装的 Renderer 类型检查通过。Web 依赖闭包实际包含 4.0.484 的 remotion 和 Player，SSR 与客户端构建成功。共享开发工作树的 node_modules 保持原状。实际镜像的两个 BuildKit 回执均在读取安装层之前报 metadata I/O 错误。Linux 环境调查已停止。

新安装的候选在 macOS 通过正式 renderVideo 复跑了 24 fps。首次写截图因本机临时盘 ENOSPC 中止，另用独立临时 RAM 卷重跑通过并卸载。新的 PCM MOV、响度前 MP4 和响度后 MP4 的 SHA-256、视频载荷、逐帧编号与 PTS、分轨与尾段时钟均与已签的 backport-4.0.484 归档一致。24 fps 的两个 MP4 edit list 直接取自本轮成品。25/30 fps、响度故障与正常跳过复用已校验的同版证据；候选 audio.ts 和 video/index.ts 与当时实际方案逐字节一致。跳过仅签响度函数边界。没有新 Linux 文件或 Chat-Origin 签收。

## 排空与回滚条件

在本地回环接收端复用 joint-candidate/cache/drain.mts，用固定成品种入 ready 缓存，实测两种老键。drain-final.json 的两个服务分别是原 v1 与含补丁 hash 的 v2。drain-provisional.json 的两个服务分别是未带 hash 的旧候选 v2 与含 hash 的 v2，原驱动的 version 数字仅表示服务先后次序。两次均见新服务读旧 ready 返回 409、PUT 为零，旧服务上传原字节成功，切换后新服务上传新成品成功。三项既有缓存测试全部通过。本机接收端没有连接产品账本或对象存储。

实际维护窗口尚未执行。暂停接纳新导出，保留旧 Worker、Renderer 与原卷，及时在 24 小时缓存保留期内让已经 prepare 的任务完成。按原 ExportJob、对象 key、upload_id 及 Output 对账。已 dispatch 且结果未知时沿既有恢复逻辑 HEAD 核验 export-upload 元数据、成品与回执，保留原预占；身份未确认、缓存 miss、旧任务未排空或出现重复交付时停止切换。新准备任务只在排空确认后进入新 Renderer 与独立缓存卷。切换后如需回滚，暂停新任务，由原生成这些字节的实例分别排空各自的 ready 和在途上传，再把后续新任务路由回旧实例。旧 Output、对象、账本和授权不做迁移或重放。
