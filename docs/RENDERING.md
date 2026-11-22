# Rendering — video-spec 与交付链

正式成片上传至当前公开 TOS 桶的 exports/ 路径。交付消息绑定已审阅的 Output 和不可变版本。

> Status: 现行契约（2026-11-16）。作品与预览见 [VIDEO_PROJECT](VIDEO_PROJECT.md)，发布和视听验收见 [统一视频合同](tasks/skill-package-promo-video.md)。

## 1. 一条链

`CompositionVersion → preview_range → export_video → ExportJob → Renderer → Output → review_video → deliver_video`

export_video 在事务内固定版本、digest、授权上限与原生回执。Worker 按 token 和租约执行，编译后的 video-spec 只引用已固定的来源。上传后验证真实字节与流信息，成功时同事务提交成片与账本。

导出续行的审片输入包含固定版本及其直接父版的实际时长，逐个与解码文件核对。预览窗口和正式导出共用 compile_video_spec。作品关键帧使用片段局部 tick，Renderer 在局部帧上读取量化后的值。OxValue 第二镜头共 270 帧。v15 基线与 v14 已交付镜头对应；修复后的 v17 局部预览与同版正式 MP4 的第 105–374 帧分别解码对齐。按 384×216 RGB 比较，修复版平均绝对像素误差为 0.165/255。[双版本比对与画面](tasks/agent-editor-evidence/iteration-7/README.md)

## 2. 代码地图

| 座位 | 职责 |
|---|---|
| `apps/api/app/tools/video/export.py` | 固定版本的规格与报价 |
| `apps/api/app/editing/video_spec.py` / `packages/video-spec` | Python 编译与共享 TS schema、定时/动画契约 |
| `packages/video-remotion` | 共享视频画笔 |
| `apps/render/src/server.ts` / `video/` | `/render` 与 `/upload`、渲染、上传与缓存 |
| `apps/render/src/component-runtime/` | 受控 Generator 的隔离烘焙 |
| `apps/api/app/pipeline/rendering.py` / `render_probe.py` / `export_jobs.py` | 编排、探测、围栏、缓存重传与结果落库 |

## 3. video-spec 字段契约

字段与类型由 `packages/video-spec/src/schema.ts` 和 API 编译器定义。时间、画幅、动画、图像和音轨使用该合同；预览按确切版本切片。spec 只含最终合成需要的固定数据与媒体引用，不含 React/Remotion 对象、程序源码、业务数据库引用、生成请求或预签名上传控制字段。

**网页状态仍是 WebObject**：CapturePlan 的 populated/full/cutout/blank_plate/hero 制品冻结为同一 web SourceSnapshot 下的独立 `view_id`；普通网页层仍由 `WebObject + view_id` 引用。受控 Generator 的显式派生 image Snapshot 资源由上游准备层校验 owner、原 web/view 与精确 digest，不能直接将 web 清单当 image 使用。共享相机的 RGBA cutout 按配对目标盒无缩放补齐透明全画布，保存原裁切与配对 digest；renderer 只消费固定 Generator 视频与独立原生文字，不拼采集坐标。selected 特写使用冻结元素盒与既有相机数学，before/after 使用普通 centered crossfade，原生 plate/cutout 使用普通 opacity/transform 动画；video-spec 不新增网页状态或 renderer 字段。

## 4. 预览

分镜默认静态。显式局部 Scrub 使用确切版本、digest 和目标窗口，经过同一媒体与动画求值边界。浏览器预览只产生该版本的预览观察；连续视听与正式交付各自取证。

## 5. 传输与缓存

- **上传与恢复**：源下载的响应头/空闲等待为 300 秒；上传的响应头、空闲等待与单次尝试上限均为 600 秒，每个文件最多尝试 4 次，共享 720 秒总预算（包含退避）。连接重置/断管/临时网络错误/超时及 HTTP 5xx/408/429 可重试；每次重建连接池，指数退避带抖动并遵守 `Retry-After`，等待超出剩余预算则结束。鉴权、证书及未知错误不盲重试；错误日志不含预签名 URL。API 请求默认上限 1800 秒，上传签名至少有效 3600 秒。生成、上传与恢复错误分别返回 `stage=render|upload|recovery`；上传失败提示已生成但未交付，缓存失效只要求重新渲染，不伪装成重传。
- **成片缓存**：`artifacts.ts` 按 Output 身份、规范化 spec 和渲染器缓存版本定位，完整生成后原子写 ready marker，保留 24 小时。变更 spec 或缓存版本需重新生成；签名改变不导致 miss。
- **代理**：`dev.sh` 按显式 `RENDER_PROXY` → 已导出 HTTP(S) 代理 → macOS 系统 HTTPS 代理 → 本地 6152 默认值选择；`RENDER_PROXY=off` 明确关闭。探测失败保留配置并提示，不自动回退直连；选择结果写 render 日志。

## 6. 渲染与交付约束

- 渲染器不访问产品数据库。媒体 staging 在取帧前准备，音频响度处理由 `apps/render/src/audio.ts` 承担。
- 成功提交需要适用的完整性 probe、`render_status=COMPLETED` 与实际 `files.video`；部分成功只统计可交付产物。
- 商业发布前需核对实际运行方式下的 Remotion 许可，覆盖最终 Renderer 与上游 Generator runner，同时完成部署环境的隔离、能力、成本与动态视听验收。

## 7. 渲染器替换

替换画笔时保持 video-spec、时间与动画求值合同。以同版预览/成片帧、音频、失败恢复、许可和成本验收替代实现。

## 8. 轨道模型

Composition 的 Track/Clip/Object、源窗、输出窗和锚点以 [VIDEO_PROJECT](VIDEO_PROJECT.md) 的编辑契约为准。字幕、旁白与其他媒体通过普通对象参与同一时间线和编译链。

## 9. 导出执行权与 Stop

每个 ExportJob 的 ID 同时保留给该次 Output，上传地址绑定所有者、项目、导出 ID 和上传身份。条件 PUT 防止覆盖；Worker 重新认领后先探测实际字节与对象元数据。已开始的上传在结果未知时保留预占与核对凭据，核对有界。

Stop 先于成功事务提交时，原 opening 停止，用户不获得该成片。待外部副作用核清后全额释放、扣费为零。只有能证明属于该次上传且无引用的对象才能清理。Output 先合法提交时，Stop 只影响后续操作。正式交付需审阅确切 Output，持久消息保存其引用。真实条件 PUT 和隔离库竞争测试见 [6D 证据](tasks/agent-editor-evidence/iteration-6/6d.md)。
