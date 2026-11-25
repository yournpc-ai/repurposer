# Rendering — video-spec 与交付链

正式成片上传至当前公开 TOS 桶的 exports/ 路径。交付消息绑定已审阅的 Output 和不可变版本。

> Status: 现役契约与候选研究边界。作品与预览见 [VIDEO_PROJECT](VIDEO_PROJECT.md)，现行施工与视听验收见 [I8](tasks/i8.md) 和 [进度 §0](PROGRESS.md)。

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

Motion Block 的节拍按幕内秒数声明。居中转场扩展的入幕预卷参与镜头入场，旁白高光、卡片揭示、光标点击和多步框选以原切点为零。截图、光标和框选共用一个原尺寸比例平面，镜头对整个平面求值。Skill 蓝图保存镜头、舞台、转场和节拍时间，实例化时用新视图的元素重新解算坐标。每个蓝图最多 48 幕、96 条音效提示，短拍下限为 0.2 秒。`kinetic_beat` 和 `ui_montage` 在服务端与 Player 共用逐帧渲染器。Chat 的八种动效预览沿用 `video_preset_set`，2.8 秒内联规范固定示范字形和界面线框，并继承选中作品的风格。

## 4. 预览

分镜默认静态。显式局部 Scrub 使用确切版本、digest 和目标窗口，经过同一媒体与动画求值边界。浏览器预览只产生该版本的预览观察；连续视听与正式交付各自取证。

## 5. 传输与缓存

- **上传与恢复**：源下载的响应头/空闲等待为 300 秒；上传的响应头、空闲等待与单次尝试上限均为 600 秒，每个文件最多尝试 4 次，共享 720 秒总预算（包含退避）。连接重置/断管/临时网络错误/超时及 HTTP 5xx/408/429 可重试；每次重建连接池，指数退避带抖动并遵守 `Retry-After`，等待超出剩余预算则结束。鉴权、证书及未知错误不盲重试；错误日志不含预签名 URL。API 请求默认上限 1800 秒，上传签名至少有效 3600 秒。生成、上传与恢复错误分别返回 `stage=render|upload|recovery`；上传失败提示已生成但未交付，缓存失效只要求重新渲染，不伪装成重传。
- **成片缓存**：`artifacts.ts` 按 Output 身份、规范化 spec 和渲染器缓存版本定位，完整生成后原子写 ready marker，保留 24 小时。v3 键区分当前视觉引擎，并包含锁定 Renderer 的音频补丁 SHA-256。切换前由原 Renderer 和原缓存卷排空已 prepare 的上传。上传结果未知时先按原上传身份核对对象并保留预占。变更 spec 或缓存版本需重新生成；签名改变不导致 miss。
- **代理**：`dev.sh` 按显式 `RENDER_PROXY` → 已导出 HTTP(S) 代理 → macOS 系统 HTTPS 代理 → 本地 6152 默认值选择；`RENDER_PROXY=off` 明确关闭。探测失败保留配置并提示，不自动回退直连；选择结果写 render 日志。

## 6. 渲染与交付约束

- 渲染器不访问产品数据库。媒体 staging 在取帧前准备，音频响度处理由 `apps/render/src/audio.ts` 承担。
- 成功提交需要适用的完整性 probe、`render_status=COMPLETED` 与实际 `files.video`；部分成功只统计可交付产物。
- 商业发布前需核对实际运行方式下的 Remotion 许可，覆盖最终 Renderer 与上游 Generator runner，同时完成部署环境的隔离、能力、成本与动态视听验收。

## 7. 渲染器替换

现役 Remotion Renderer 消费固定媒体。专业视觉创作采用受控 React/TSX/CSS 的方向已确定。自有薄渲染核心 C 的技术可行性研究已阶段收官，C 继续作为生产候选。它让 Chromium 处理 DOM、CSS、遮罩、混合、背景模糊和视频合成，FFmpeg 负责编码，必要处适配媒体。八秒样本在一棵 React 树中合成两路真实视频与两个 Motion Blocks，并对同一作品的参数和层序作了定向修改。[合成实验](experiments/mg-render/native-css/REPORT.md)

浏览器自走动画曾在同一作品帧输出不同像素。对指定标题块，宿主暂停 Web Animations API（WAAPI）动画，每次取帧都按 Composition 帧时间显式设置 `currentTime`。固定 Chromium 的 30 fps 样本中，全部 240 帧与显式帧函数逐像素相同；乱序、重复取帧和独立进程逆序均匹配。只改标题颜色后，150 个活动帧的变化限于标题包围盒，其余 90 帧无差异。其他动画类型仍需各自验证。[时钟与局部修订复核](experiments/mg-render/native-css/clock/REPORT.md)

实时播放、第三方 TSX 安全、长片资源、高并发与缓存成本、相对 Remotion 的总维护成本仍待验证。正式 Chat-Origin Motion Block 纵向集成尚未实施，生产 Renderer 替换尚未获准。video-spec 保持渲染器中立，不扩成逐效果滤镜语言。

原 AAC/ADTS 中间路径在指定样本增加 2,048 个前导采样。PCM MOV 修正了该样本；25 fps 动态 loudnorm 的尾部 PTS 间隙与 Linux 30 fps Matroska 毫秒量化各有隔离修正。生产正确性、缓存切换和真实 Chat 五面仍未签收。当前候选及平台验收状态见 [进度 §0](PROGRESS.md)。[基线](experiments/renderer-aac/REPORT.md) · [候选评审](experiments/renderer-aac/CANDIDATE-REVIEW.md) · [时钟与缓存边界](experiments/renderer-aac/clock-boundaries/REPORT.md)

替换画笔时保持 video-spec、时间与动画求值合同。以同版预览/成片帧、音频、失败恢复、许可和成本验收替代实现。

## 8. 轨道模型

Composition 的 Track/Clip/Object、源窗、输出窗和锚点以 [VIDEO_PROJECT](VIDEO_PROJECT.md) 的编辑契约为准。字幕、旁白与其他媒体通过普通对象参与同一时间线和编译链。

## 9. 导出执行权与 Stop

每个 ExportJob 的 ID 同时保留给该次 Output，上传地址绑定所有者、项目、导出 ID 和上传身份。条件 PUT 防止覆盖；Worker 重新认领后先探测实际字节与对象元数据。已开始的上传在结果未知时保留预占与核对凭据，核对有界。

Stop 先于成功事务提交时，原 opening 停止，用户不获得该成片。待外部副作用核清后全额释放、扣费为零。只有能证明属于该次上传且无引用的对象才能清理。Output 先合法提交时，Stop 只影响后续操作。正式交付需审阅确切 Output，持久消息保存其引用。真实条件 PUT 和隔离库竞争测试见 [6D 证据](tasks/agent-editor-evidence/iteration-6/6d.md)。
