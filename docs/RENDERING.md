# Rendering — video-spec 与交付链

> Status: 现行契约（2026-11-16）。作品与预览见 [VIDEO_PROJECT](VIDEO_PROJECT.md)，发布和视听验收见 [统一视频合同](tasks/skill-package-promo-video.md)。

## 1. 一条链

`CompositionVersion → produce_video → 冻结执行输入 → video-spec → 渲染 → 上传 → probe → 交付`

授权后的 Run 固定作品版本与执行身份。普通媒体使用冻结来源，待准备的图像、语音与受控 Generator 先产出固定媒体。`editing/video_spec.py::compile_video_spec` 编译现行 `video-spec`，API 解析可供渲染器下载的 URL 并签发上传地址。渲染器根据 spec 生成 MP4，成功上传并通过文件检查后，API 按当前认领身份提交交付和扣费。

## 2. 代码地图

| 座位 | 职责 |
|---|---|
| `apps/api/app/tools/video/production/` | 版本钉版、报价、制作与成功扣费 |
| `apps/api/app/editing/video_spec.py` / `packages/video-spec` | Python 编译与共享 TS schema、定时/动画契约 |
| `packages/video-remotion` | 共享视频画笔 |
| `apps/render/src/server.ts` / `video/` | `/render` 与 `/upload`、渲染、上传与缓存 |
| `apps/render/src/component-runtime/` | 受控 Generator 的隔离烘焙 |
| `apps/api/app/pipeline/rendering.py` / `render_probe.py` / `upload_recovery.py` | 编排、探测、围栏、缓存重传与结果落库 |

## 3. video-spec 字段契约

字段与类型由 `packages/video-spec/src/schema.ts` 和 API 编译器定义。时间、画幅、动画、图像和音轨使用该合同；预览按确切版本切片。spec 只含最终合成需要的固定数据与媒体引用，不含 React/Remotion 对象、程序源码、业务数据库引用、生成请求或预签名上传控制字段。

**网页状态仍是 WebObject**：CapturePlan 的 populated/full/cutout/blank_plate/hero 制品冻结为同一 web SourceSnapshot 下的独立 `view_id`；普通网页层仍由 `WebObject + view_id` 引用。受控 Generator 的显式派生 image Snapshot 资源由上游准备层校验 owner、原 web/view 与精确 digest，不能直接将 web 清单当 image 使用。共享相机的 RGBA cutout 按配对目标盒无缩放补齐透明全画布，保存原裁切与配对 digest；renderer 只消费固定 Generator 视频与独立原生文字，不拼采集坐标。selected 特写使用冻结元素盒与既有相机数学，before/after 使用普通 centered crossfade，原生 plate/cutout 使用普通 opacity/transform 动画；video-spec 不新增网页状态或 renderer 字段。

## 4. 预览

分镜默认静态。显式局部 Scrub 使用确切版本、digest 和目标窗口，经过同一媒体与动画求值边界。浏览器预览不创建 Run/Output；连续视听与正式交付各自取证。

## 5. 传输与缓存

- **上传与恢复**：源下载的响应头/空闲等待为 300 秒；上传的响应头、空闲等待与单次尝试上限均为 600 秒，每个文件最多尝试 4 次，共享 720 秒总预算（包含退避）。连接重置/断管/临时网络错误/超时及 HTTP 5xx/408/429 可重试；每次重建连接池，指数退避带抖动并遵守 `Retry-After`，等待超出剩余预算则结束。鉴权、证书及未知错误不盲重试；错误日志不含预签名 URL。API 请求默认上限 1800 秒，上传签名至少有效 3600 秒。生成、上传与恢复错误分别返回 `stage=render|upload|recovery`；上传失败提示已生成但未交付，缓存失效只要求重新渲染，不伪装成重传。
- **成片缓存**：`artifacts.ts` 按 Output 身份、规范化 spec 和渲染器缓存版本定位，完整生成后原子写 ready marker，保留 24 小时。变更 spec 或缓存版本需重新生成；签名改变不导致 miss。
- **仅上传恢复**：`retry_upload` 只接受结构化上传失败，优先使用精确引用，其次使用唯一候选；歧义先确认。在途和已交付结果不重复上传。独立 `/upload` 使用同一 Output、spec 和已有缓存；miss 返回 409 / `ARTIFACT_CACHE_MISS`。保留原 Run/步骤，不触发重渲染或重复扣费。真实代理重传仍待验收。
- **代理**：`dev.sh` 按显式 `RENDER_PROXY` → 已导出 HTTP(S) 代理 → macOS 系统 HTTPS 代理 → 本地 6152 默认值选择；`RENDER_PROXY=off` 明确关闭。探测失败保留配置并提示，不自动回退直连；选择结果写 render 日志。

## 6. 渲染与交付约束

- 渲染器不访问产品数据库。媒体 staging 在取帧前准备，音频响度处理由 `apps/render/src/audio.ts` 承担。
- 成功提交需要适用的完整性 probe、`render_status=COMPLETED` 与实际 `files.video`；部分成功只统计可交付产物。
- 商业发布前需核对实际运行方式下的 Remotion 许可，覆盖最终 Renderer 与上游 Generator runner，同时完成部署环境的隔离、能力、成本与动态视听验收。

## 7. 渲染器替换

替换画笔时保持 video-spec、时间与动画求值合同。以同版预览/成片帧、音频、失败恢复、许可和成本验收替代实现。

## 8. 轨道模型

Composition 的 Track/Clip/Object、源窗、输出窗和锚点以 [VIDEO_PROJECT](VIDEO_PROJECT.md) 的编辑契约为准。字幕、旁白与其他媒体通过普通对象参与同一时间线和编译链。

## 9. 共享渲染所有权与验收

编译期为 Output 指定唯一 render owner，inputs 包含全部实际写入者。非 owner 不 re-pend / 建 render step；失败阻断 owner，归档对象不重新排队，跨 Run 不双重拥有。Worker 认领铸造 `render_claim_token`，终态写核对 token 和命中数，失势执行不覆盖结果或重复扣费。交错、取消、恢复和失败注入验收见 [VERIFICATION §5](VERIFICATION.md#5-共享机制与-ui-的当前验收)。

有 WorkflowStep 的正式导出使用项目、Output 及固定 step、版本与 render spec 派生的对象 key。首次上传以条件 PUT 写入，恢复时从该 key 重读实际字节并探测媒体流，提交时记录 SHA-256。已交付文件复用时复核摘要。既有历史对象仍按其持久引用读取。
