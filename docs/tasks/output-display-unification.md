# 产物/输入展示统一——剩余合同

> Status: 后端薄层已有代码层结果（`ExampleOutput.kind="document"`、`doc_format`、`OutputResponse.aspect` 与图片 aspect 声明）；前端共享展示脊柱、资产 dims 和全表面收敛仍未完成。旧分批施工记录不再作为状态依据。

## 1. 当前目标

产物与输入都由**声明的数据类型和画幅**驱动展示，不靠 recipe/card id 或各页面重复探测。剩余工作分两层：

1. **前端脊柱**：`MediaKind`、画幅解析、装框、ambient video、类型图标和声明缺失时的 intrinsic-aspect fallback 各有一份实现。
2. **资产声明**：视频/图片处理期把 width/height 写入 `Asset.meta` 并序列化透出；声明缺失才共享探测。

不新增表，优先扩展序列化字段和注册表枚举。

## 2. 剩余实施范围

### 2.1 共享原语

- `lib/media-kind.ts`：`video/image/audio/doc/text` 与 output/asset/example 的推导；document 的 post/carousel 由 `doc_format` 分派。
- `lib/aspect.ts`：声明值 → CSS aspect-ratio；任意比用 inline style，禁止运行时拼 Tailwind 类；`original`/null 走共享 fallback。
- `ui/media-frame.tsx`：统一 aspect/fit；产物 contain 不裁，输入素材缩略可按现有规则 cover。
- `ui/ambient-video.tsx`：静音循环与单卡发声开关；`ui/type-icon.tsx`：lucide 图标注册表。
- `lib/useIntrinsicAspect.ts`：声明缺失时唯一 loadedmetadata/naturalWidth 探测座。

命名以现行 NAMING 和代码为准；以上是职责座位，不要求为匹配旧文档而新建重复组件。

### 2.2 表面收敛

- `OutputInspector` / `MediaLightbox` / `AnchorCards`：document 产物由 Output/payload 类型与 `doc_format` 驱动，post=文本、carousel=分页文档；删除任何残留 recipe/card id 分支。Home 配方仍是 prompt-only，**不得为统一展示恢复 RecipeInspectOverlay 或第二发射面**。
- 结果网格、ClipDetailModal、MediaLightbox：统一 Output.aspect 与 media-frame，quotes/quote-frame 不再各写画幅映射。
- FlowNodeCard：保留布局数学，但画幅归一只走共享解析；播放器与图标复用脊柱。
- Chat / composer / upload chips：统一媒体类型与图标，不改 wire 的 attachment 类型。
- **ProjectCard**：当前仍有固定 `aspect-video` 容器；必须实际消费已下发的 `thumbnail_aspect`，竖屏项目用正确比例和 contain，不能只保留未读字段。
- 编辑器：复用画幅归一，不改变 Remotion Player；landing 与 persona 固定预览不为了统一而改。
- 下载与 `toAbsoluteUrl` 收敛可在触及表面时完成，不单独扩大批次。

### 2.3 资产 dims

处理期探测并保存视频/图片 width/height，AssetResponse 透出；旧资产缺字段时走共享 fallback。不得让多个表面各自重新下载媒体只为知道尺寸。

## 3. 验收

- inspector / lightbox / anchor cards：post=文本、carousel=分页文档、quote=9:16，均无 recipe/card id 分支；Home 点击仍只预填 prompt。
- 结果网格与画布：9:16 产物不裁、不变方框；ProjectCard 竖屏缩略正确。
- chat/composer 图标一致；同一输出在 grid/canvas/chat 的类型和画幅一致。
- 声明存在时零运行时探测；缺失时只有一个 fallback；旧数据不崩溃。
- 静态检查无运行时 `aspect-[${...}` 拼接、无新增同义本地图标/画幅/播放器实现；web tsc 与相关纯测试通过。
- 双主题走查 inspector、lightbox、results、canvas、projects、chat 与 Home 货架；landing 和 Remotion 预览无回归。

## Prohibited Behaviors

- 禁 recipe/card id 驱动展示；禁运行时 Tailwind 类拼接。
- 禁新增第四份同义逻辑；禁产物 object-cover 裁剪。
- 禁为统一而改 landing、persona 固定预览或 Remotion 渲染契约。
