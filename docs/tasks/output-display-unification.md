# 产物/输入展示统一——MediaKind 类型驱动 + 单一画幅解析 + 前端展示脊柱

> Status: 📋 已立项未实施（2026-08-27 拍板；与画廊 v3 同批——ADR-048 后果条：本简报承接"产物按类型正确展示"的展示层清算）
> 依据：2026-08-27 全表面审计（读码，见 §1 汇总）；ADR-046（卡片深度纪律）/ ADR-048（证据层 = overlay 示例 tab）/ CLAUDE.md（fill-first、无运行时 Tailwind 类）
> 前置读：`docs/RENDERING.md` §3（aspect 契约）、`docs/RECIPES.md` §7.1（example_* 数据包）

## 0. Context

用户判词（2026-08-27）：model 的 outputs 没有统一组件处理各种屏幕尺寸和类型——后端应给出类型（视频/图片/文字等），前端按类型正确展示产物和输入。审计证实：前端 **10 个展示面各自为战**，同一逻辑（画幅映射 ×5、内置尺寸探测 ×4、静音循环播放器 ×3、类型→图标 ×4、文档 tile ×3、下载 ×2、URL 拼接 ×3）大量重复且已发生漂移（audio 图标 Music/Mic2 不一致）；后端类型信息存在但**不到线**（`render_spec.aspect` 只挂 clip、image 产物无尺寸、example 的 JSON 产物 `kind="image"` 说谎），前端被迫用卡 id 硬分支和运行时探测兜底。

## 1. 审计结论汇总（读码实证，2026-08-27）

**已发生的真实 bug**：`QuotesCard` 硬编码 `aspect-square`（结果页 QuotesCard.tsx:46-75）——后端 08-25 起烘 9:16 叠卡 PNG，展示裁错；`ProjectCard` 固定 `aspect-video` + object-cover 裁竖屏 clip，而 `thumbnail_aspect` 字段**已下发从未被读**（ProjectCard.tsx:87-127 vs schemas.py:906-910）；`ExampleOutput.kind` 只有 `video|image`，post/carousel 的 JSON 注册为 `kind="image"`，overlay 靠 `card.id ===` 硬分支才知道去 fetch JSON（RecipeInspectOverlay.tsx:123-166）。

**重复清单（应收敛）**：画幅→样式映射 5 份（ExampleCard 运行时 Tailwind 类 hack / ClipCard / ClipDetailModal / layout.ts 两组像素表 / 编辑器 inline）｜内置尺寸探测 4 份｜静音循环+发声开关播放器 3 份｜类型→图标 4 份｜文档 icon tile 3 份｜"slide 小卡"文本 tile 4 份｜下载逻辑 2 份｜URL 绝对化 3 份。同一 `Output` 行有**三种渲染**（结果网格卡 / 画布 ProductCard / chat OutputChatCard）。

**后端缺口**：① example JSON 产物无 kind 可表达 ② `files.image/video` 无尺寸/时长 ③ Asset 无 dims（5+ 面各自探测）④ aspect 只挂 `render_spec`（前端到处不安全 cast）⑤ "original" 哨兵值处处特判 ⑥ Asset 无 poster 字段。

## 2. 设计

### 2.1 原则

1. **类型驱动，永不用卡 id 分支**：渲染族由数据类型推导（`MediaKind`），卡 id 永不进展示逻辑。
2. **声明优先，探测兜底**：aspect/尺寸能由后端声明的不再运行时探测；探测（loadedmetadata/naturalWidth）只是声明缺失时的 fallback，且探测逻辑全站一份。
3. **一份脊柱，处处消费**：画幅解析 / 播放器 / 图标 / 文档 tile 全站各一份，表面只组合不重造。
4. **零新表**（RECIPES §10）：一切走序列化字段与注册表枚举扩展。

### 2.2 后端薄层（只加字段，不加机制）

| 改动 | 位置 | 说明 |
|---|---|---|
| `ExampleOutput.kind` 扩枚举 `video\|image\|audio\|document` + 可选 `aspect`（缺省回落卡级 `aspect`）+ 可选 `doc_format: "post"\|"carousel"` | `pipeline/recipes.py` | JSON 产物注册改 `kind="document"`，overlay 按 kind fetch，卡 id 分支删除 |
| `OutputResponse` 序列化加 `aspect: str\|None` | `models/schemas.py` | 服务端单点推导：`render_spec.aspect`（clip 族）→ 产物写入时声明（image 产物，合成器知道尺寸）→ None；"original" 归一为 None |
| 图片产物写入时记 aspect | `derivative_dispatch.py` 等写入点 | 叠卡 PNG / 帧卡 = 9:16 落字，QuotesCard 方框 bug 根治 |
| （P3）`AssetResponse` 加 `width/height`（视频/图片处理期探测落 `Asset.meta`，序列化透出） | `asset_processing.py` + `schemas.py` | 杀 5+ 面重复探测的源头 |

命名：`doc_format` / `aspect` 字段随实施过 NAMING §7；`document` kind 进 RECIPES §9 词汇表。

### 2.3 前端脊柱（`components/ui/` 新增 4 件 + `lib/` 2 件）

| 件 | 职责 | 杀掉的重复 |
|---|---|---|
| `lib/media-kind.ts` | `MediaKind = "video"\|"image"\|"audio"\|"doc"\|"text"` + 三个推导函数（`outputKind(output)` / `assetKind(asset)` / `exampleKind(example)`） | 类型判断散落 |
| `lib/aspect.ts` | `aspectStyle(declared?) → CSS aspect-ratio`：档内映射 + 任意比 inline style（**禁运行时 Tailwind 类**）；"original"/null → 探测 → 默认 | 画幅映射 ×5 |
| `ui/media-frame.tsx` | 单一装框原语：`{aspect, fit: "contain"\|"cover", className}`——letterbox 纪律一处（产物永远 contain 不裁，RECIPES §4.1 条款） | 各面自造框 |
| `ui/ambient-video.tsx` | 静音循环 + 单卡发声开关（media-frame 内） | 播放器 ×3 |
| `ui/type-icon.tsx` | `typeIcon(kind)` 单一图标注册表（lucide 唯一来源） | 图标映射 ×4 + Music/Mic2 漂移 |
| `lib/useIntrinsicAspect.ts` | 共享探测 hook（声明缺失时 fallback） | 探测 ×4 |

### 2.4 表面收敛（消费脊柱，删本地重复）

| 表面 | 收敛动作 |
|---|---|
| RecipeInspectOverlay ExampleCard | kind=document 驱动 fetch（删卡 id 分支）+ media-frame/aspect.ts（删运行时类 hack）+ ambient-video + type-icon（删本地 fileIconFor） |
| 结果网格卡（Clip/Quotes/Post/Carousel/ArticleCard）+ ClipDetailModal + MediaLightbox | 统一 `Output.aspect`（删 render_spec cast 与方框硬编码）+ media-frame + downloadOutput.ts 全量采用 |
| 结果画布 FlowNodeCard（ProductCard/ThumbCard） | aspect.ts 替换 layout.ts 两组像素表输入（布局数学不变，只换 aspect 来源）+ ambient-video + type-icon |
| chat（OutputChatCard / UserBubble / 上传 chips） | OutputChatCard 改派生 media-kind；chips 用 type-icon |
| composer（AssetChips/AssetsPanel） | type-icon + useIntrinsicAspect（stagedFiles 探测逻辑并入共享 hook） |
| ProjectCard | 读 `thumbnail_aspect`（字段已下发）+ media-frame contain（竖屏不再裁） |
| 编辑器 clips.$clipId | aspect.ts 一处（"original" 特判随归一删除） |

**不在范围**：editor 的 Remotion Player（真渲染非展示壳）、landing（营销豁免）、persona skin-editor 预览（9:16 定死有理由）、下载/URL 收敛顺做不顺挡（`toAbsoluteUrl` 三处手卷随 P2 清）。

## 3. 分期与验收

| 期 | 内容 | 验收 |
|---|---|---|
| **P1 后端薄层**（0.5 天，随 08-28） | §2.2 前三行 + recipes 三 JSON 条目改 kind + QuotesCard 方框修复（随 Output.aspect） | 结果页叠卡 9:16 正确出框；overlay post/carousel 无卡 id 分支正常渲染 |
| **P2 前端脊柱 + 收敛**（1.5 天，W7 周初，与 quote-cards P2 并行） | §2.3 全件 + §2.4 前四行 | grep 清零：`aspect-[${` 运行时类 / `PRODUCT_THUMB_PX` 直引 / 本地 fileIconFor / assetTypeIcon；tsc 绿；五表面走查双主题 |
| **P3 资产 dims + 清场**（0.5 天，W7） | Asset dims 落 meta + 序列化 + ProjectCard + URL/下载手卷清理 | 画布/video 资产节点零探测即出框；ProjectCard 竖屏 contain |

## 4. Prohibited Behaviors

1. **禁**展示逻辑用 `card.id` / recipe id 分支——类型驱动（MediaKind）唯一合法。
2. **禁**运行时拼接 Tailwind 类名（`aspect-[${w}/${h}]`）——画幅走 `aspect.ts` inline style。
3. **禁**新增第四份同义逻辑（播放器/图标/探测/画幅映射）——先查脊柱再动手。
4. **禁**产物媒体 object-cover 裁剪（RECIPES 永不裁剪条款）；输入素材缩略可 cover（素材不是产品）。
5. **禁**为统一而统一 landing / Remotion 预览（§2.4 不在范围条款）。

## 5. 实施导引（新会话零讨论施工版）

### 5.0 基线状态

- git 工作树有 ~2300 行未提交改动（上一迭代的 quote-cards/copy-writer 工作）——是**新基线**，不要 revert；其中 `RecipeInspectOverlay.tsx` 的 ExampleCard 改造（画幅自探测 + quote-cards 走 ExampleCard 网格）发生在上一迭代，本简报在它之上收敛，不回滚。
- 审计发现即修的两个真 bug 优先：`QuotesCard` 硬编码 `aspect-square`（`apps/web/src/components/results/QuotesCard.tsx:46-75`——后端 08-25 起烘 9:16 叠卡，展示裁错）；`ProjectCard` 固定 `aspect-video`+`object-cover` 裁竖屏，`thumbnail_aspect` 字段已下发未读（`apps/web/src/components/project/ProjectCard.tsx:87-127` vs `apps/api/app/models/schemas.py:906-910`）。

### 5.1 P1 逐项施工单（后端薄层 + 两个 bug，估 0.5 天）

| # | 动作 | 落点与思路 |
|---|---|---|
| 1 | `ExampleOutput.kind` 扩 `"document"` + 可选 `doc_format` + 可选 `aspect` | `apps/api/app/pipeline/recipes.py:83-91`（Literal 扩值 + 两个可选字段）；三个 JSON 注册条目改 kind：`social-post`（~:489）、`carousel`（~:587）改 `kind="document", doc_format="post"/"carousel"`；`quote-cards`（~:557）保持 `kind="image"` 但补 `aspect="9:16"`。`RecipePublic` 投影同步带出新字段；前端 `apps/web/src/lib/recipes.ts` 的 `RecipePublic` interface 镜像 |
| 2 | `OutputResponse` 序列化加 `aspect` | `apps/api/app/models/schemas.py:2047-2104` 的 Output 序列化处：推导 = `render_spec.aspect`（有 render_spec 的 clip 族，注意 `"original"` 归一为 None）→ payload 声明（image 产物写入点补，见 #3）→ None。前端 `apps/web/src/lib/types.ts` Output 类型同步加 `aspect?: string \| null` |
| 3 | 图片产物写入点记 aspect | `apps/api/app/pipeline/derivative_dispatch.py` 叠卡/帧卡 Output 创建处（~:344、~:415）在 payload 或专用字段落 `"aspect": "9:16"`，供 #2 推导消费 |
| 4 | QuotesCard 修复 | `apps/web/src/components/results/QuotesCard.tsx`：删 `aspect-square` 硬编码，改读 `output.aspect`（本 P1 先用最小修法——读 `aspect` 映射三个静态类；`media-frame` 统一在 P2） |
| 5 | ProjectCard 修复 | 读 `thumbnail_aspect`：9:16 时容器改 `aspect-[9/16]` + `object-contain`（产物不裁）；其余保持 16:9 |
| 6 | overlay 删卡 id 分支 | `RecipeInspectOverlay.tsx:123-166`（socialPost/carousel 两个 fetch useEffect）与 `:430-476`（条件渲染）：改由 `o.kind === "document"` 驱动 fetch（kind=document 的 example 才 fetch JSON），渲染分支按 `doc_format` 分派；`SocialPostPayload`/`CarouselPayload` 类型保留。卡 id 分支全删 |

### 5.2 P2 脊柱施工顺序（估 1.5 天）

1. 先落 `lib/aspect.ts` + `lib/media-kind.ts` + `lib/useIntrinsicAspect.ts`（纯函数/hook，零消费方改动）→ 2. `ui/media-frame.tsx` + `ui/ambient-video.tsx` + `ui/type-icon.tsx` → 3. 按 §2.4 表逐面收敛（每面一个 commit：ExampleCard → results 卡族 → FlowNodeCard → chat/composer chips）→ 4. grep 验收：`aspect-[${` / `PRODUCT_THUMB_PX` 直引 / 本地 `fileIconFor` / `assetTypeIcon` 清零 + `npx tsc --noEmit` 绿。
- FlowNodeCard 注意：`layout.ts` 的像素表是**布局数学输入**（节点尺寸），不是展示样式——收敛方式 = 表的输入从 aspect 字符串改走 `aspect.ts` 归一，表本身保留（布局需要固定尺寸）。
- chat `chatAttachmentType`（GenerationOverlay.tsx:443-447）的 file/image/video/audio 收窄是 wire 类型（`schemas.py:107-117`），不动 wire，只把图标查表换 `type-icon.tsx`。

### 5.3 验证

```bash
cd apps/web && npx tsc --noEmit
cd apps/api && uv run python -m compileall app && uv run python scripts/accept_prompt_surface.py
```

人工走查（双主题）：overlay 示例 tab（post=textarea / carousel=幻灯栈 / quote=9:16 视频卡）→ 结果页网格（叠卡 9:16 出框）→ 结果画布（竖屏节点不裁）→ /projects 列表（竖屏项目卡 contain）→ chat 产物卡。
