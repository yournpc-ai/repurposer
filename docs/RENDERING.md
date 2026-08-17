# Rendering — 渲染链架构（clip-spec 契约 · 烘焙缝 · 渲染服务 · 共享包）

> Status: 活跃（2026-08-17 建）。本文是 **clip-spec 字段级契约与渲染链的唯一事实源**（2026-08-17 自 VIDEO_EDITOR.md §4/§6/§9 迁入）；§8 轨道模型 = **正式契约（ADR-044，2026-08-17 过会）**。
> 上游决策：ADR-016（契约锁定 / 渲染器黑盒）/ ADR-018（服务拆分 + 共享包）/ ADR-020（stills 第二源）/ ADR-023（音乐入库烘焙）/ ADR-024（存储缝）/ ADR-026（C2PA 读 spec）/ ADR-032（Operation Model 快照）。
> 分工：本文 = 契约 + 渲染链架构 + 函数地图 + 概念命名。编辑器交互形态与 L2/L3 分工线归 VIDEO_EDITOR.md；竞品渲染技术调研归 `research/RENDERING_TECH.md`（原始素材层）。

## 1. 一条链

```
生成/编辑（写）                                          渲染（读）
──────────────                                          ──────────
select_clips → build_clip_spec ─┐
chat ops / editor 手势 ─────────┤  一切写经 operations/service.py
                                ▼
                    outputs.render_spec（JSONB，锚定真相）
                                │  render_status PENDING（worker 认领谓词）
                                ▼
                    pipeline/rendering.py 烘焙缝（fold 唯一发生地）
                      _absolutize：相对键 → 绝对 URL
                      （轨道模型落地后：+ 泳道投影 fold）
                                ▼  POST /render {spec, outputs:{put_url}}
                    apps/render（Node 黑盒：spec → MP4+SRT）
                      stage 落盘 → bundle → renderMedia → loudnorm
                                ▼  预签名 PUT 直传对象存储
                    outputs.files（带时间戳键，旧对象删除）

预览面：apps/web 编辑器 <Player> 与渲染服务共用同一个 <Clip> 组件（packages/clip）——
preview == 成片 是结构性的，不是测试出来的。
```

两条铁律（ADR-016）：**spec 只描述"是什么"，零 Remotion/React 概念**（渲染器可换，§7）；**渲染器是黑盒**——不读 DB、不吃相对 URL、不知项目/人设，一切在烘焙缝解析完毕。

## 2. 三个包与一个 API 侧

| 家 | 角色 |
|---|---|
| `packages/clip`（@repurposer/clip） | **单一画笔**：`<Clip>` 组件 + spec TS 镜像 + 字幕样式目录；web `<Player>` 与 render 服务共用——parity 之根（ADR-018） |
| `apps/render` | Remotion 渲染服务（express + @remotion/bundler + @remotion/renderer + 内置 ffmpeg，pnpm 独立于 uv），`POST /render` 黑盒：渲染到临时目录 → 预签名 PUT 上传，无共享卷 |
| `apps/web` | 编辑器预览（`<Player>` 包 `<Clip>`），手势 → ops HTTP |
| `apps/api/app/pipeline/` | spec 构建（`clip_spec.py`）+ 烘焙与驱动（`rendering.py`）+ 写纪律（`operations/`） |

## 3. clip-spec 字段级契约

**原则**：renderer-agnostic，只描述"是什么"；样式限预设枚举（CSS ∩ libass 双可表达，保手写 FFmpeg 后路，§7）。

```jsonc
{
  // kind="video": 真人实拍，url 为视频；kind="stills": 图片音频幻灯，
  // url 为可选语音轨（无录音为空串），image_urls 为背景图（0→纯色 / 1→满屏 / N→均分硬切）
  "source": { "asset_id": "uuid", "kind": "video", "url": "/api/v1/files/...mp4", "image_urls": [], "fps": 30, "duration": 120.5 },
  "aspect": "9:16",                         // 9:16 | 1:1 | 16:9 三档画幅
  "segments": [                              // 保留区间列表；删句 = 标 hidden（非破坏）。agent 规划后每保留段 ≥5 秒
    { "start": 12.4, "end": 31.0, "hidden": false }
  ],
  "crop": { "x": 0.5, "y": 0.5, "scale": 1.0 }, // 归一化中心 + 缩放；transform 实现，非 object-position
  "caption_track": [                         // ASR 词级时间戳；用户可改字
    { "start": 12.4, "end": 12.9, "text": "So", "lang": "en" }
  ],
  "translation_track": [                     // 双语对照轨：单元级译文 cue（无逐字 karaoke 时轴），与 caption_track 原文行按时间重叠配对；空 = 单语。渲染 = 译文主行 + 原文小行在下（stack 布局只画原文轨）
    { "start": 12.4, "end": 16.8, "text": "Donc une entreprise d'Oxford…", "lang": "fr" }
  ],
  "caption_style_preset": "clean-bottom",   // 预设枚举，非自由样式
  "caption_position": { "x": 0.5, "y": 0.84 }, // 归一化中心点（拖拽定位）；null → 默认底部
  "title": { "text": "The hook", "enabled": true, "size": 56, "position": { "x": 0.5, "y": 0.12 } },
  "music": { "music_id": "uuid", "url": "https://<bucket>/music/<music_id>.mp3", "enabled": true, "gain_db": -18 },
  "dub": { "url": "/api/v1/outputs/.../dub_fr.mp3", "enabled": false, "gain_db": 0 }, // 声纹克隆配音；enabled 时原声静音
  // brand 块由 API 在生成时从人设皮肤块（persona.brand）烘焙；渲染器不读 DB
  "brand": {
    "caption_color": "#22c55e",
    "caption_size": 56,
    "caption_font": "lilita",                 // lilita | inter | playfair | source-serif
    "intro": { "kind": "text", "text": "From the keynote", "duration_seconds": 2 },
    "outro": { "kind": "video", "media_url": "/api/v1/files/.../outro.mp4" },
    "fill_mode": "fill"                       // fill (cover) | fit (contain)
  },
  "brand_ref": "persona_uuid",                // 血统：哪个人设的皮肤
  "target_language": "en"
}
```

- **非破坏**（Descript 同款）：删句 = 标 `hidden`，不真删，可恢复；恢复语义归快照层（N-16）。
- `caption_track` 双驱动：内嵌烧录字幕 + 直接导 SRT（交接 CapCut 的交付物）。
- 样式只走 `caption_style_preset` 枚举目录（`captions.ts` CAPTION_PRESETS），**无自由布局**——preview=成片与 libass 可换性的前提。
- **Brand 入渲染**：`brand` 块由 API 在**生成时**从 `persona.brand` 合并系统默认皮肤烘焙（ADR-038）；渲染服务/预览只读 spec 不读库。
- **音乐入渲染**：`music.url` 为曲目的公开对象 URL（生成时自 `Music.file_path` 烘焙，ADR-023）；`<Audio>` 循环混音，`gain_db` 控增益。
- **头尾卡**：`brand.intro/outro` 存在时，主视频时间轴前后各插一张卡（`duration_seconds`，null → 2s 默认）；卡 = `{kind: text|image|video, ...}`——text 渲染标题卡样式，image/video 满帧填充、超长截断；视频体 `<Sequence>` 后移，字幕 remap 自动对齐。
- **双源形态**（ADR-020）：`kind="video"` 走 `<OffthreadVideo>`；`kind="stills"` 图片音频幻灯——`image_urls` 为背景视觉（1 满屏 / N 均分硬切 / 0 纯色兜底），`url` 为可选语音轨；有语音复用 ASR 词级 `caption_track`，无语音为定长幻灯（每图 `SECS_PER_IMAGE` 秒，后端写合成段）。背景视觉优先级：**slides PDF 页图（`Asset.slide_pages`）优先**，上传照片其次；源选择优先级 VIDEO→AUDIO→SLIDES/IMAGE。**刻意不做**：转场 / Ken-Burns / 多句动效文字轨 / B-roll（L2 停线，ADR-020）；PROGRESS 需求池的 motion 枚举（P2）若做，限于 **video 源** crop 动态预设，落地需新 ADR 明确与 Ken-Burns 拒绝的边界（ADR-028 关联）。
- **文本拖拽定位**：`caption_position` / `title.position` 为归一化中心点（= libass `\pos`，可移植），null → 渲染默认；`title.size` / `caption_size` 是 **1080×1920 竖屏参考系上的参考值**——渲染端按帧高等比缩放（9:16 不变，1:1/16:9 ≈ ×0.56；双语对照译文主行再 ×0.82、原文小行 ×0.55；字幕块宽 84% = 两侧 8% 边距随帧宽自适应）。人设页皮肤分区的预览叠透明层支持拖拽 marker 改位置/字号（无独立盒宽高、无关键帧动画）。
- **声纹克隆配音（dub）**：`POST /outputs/{id}/dub` 用人设声纹经 voice_clone + T2A 把（翻译后的）字幕合成目标语言语音，烘入 `dub` 轨；渲染时 `dub.enabled` ⇒ **原声静音**、播放 dub（overlay，无唇形同步，ADR-037）。

## 4. 隐式轨道解剖（代码实证）

spec 已是隐式多道组合——每道的时间轴归属是**字段级**事实（轨道模型只是将其正名，§8）：

| 道 | spec 字段 | 时间轴 | Clip.tsx 渲染位置 | 写者 |
|---|---|---|---|---|
| 主轨（序列） | `source` + `segments` | 源时间轴（保留区间连接） | `<Series>` 逐段 `<OffthreadVideo>`/`Audio`（stills 走 `<Img>` 均分） | select_clips / materialize_source |
| 裁切 | `crop`（静态单值） | —（整条常量） | 主轨外层 `transform: scale+translate` | select_clips（→ crop_track 演进） |
| 字幕 | `caption_track`（词级 cue） | **源时间轴**，渲染时按 sourceTime 反查 | `groupLines` → single/stack 两布局 | ASR / translate_clip |
| 对照字幕 | `translation_track`（单元级） | 源时间轴，与原文行按时间重叠配对 | 译文主行 ×0.82 + 原文小行 ×0.55 | translate_clip |
| 标题 | `title` | 输出时间轴（片头区淡入；stack 布局下 ~3s 自动退场） | 绝对定位 div | director/skill |
| 音乐 | `music`（url/enabled/gain_db） | **输出时间轴**，循环铺满 | `<Audio loop>` | add_music / set_music |
| 配音 | `dub`（url/enabled/gain_db） | **输出时间轴整段**（生成时已按 cue 拼接对齐）；enabled ⇒ 原声静音 | `<Sequence from=introFrames>` 内 `<Audio>` | dub_clip |
| 头尾卡 | `brand.intro/outro` | 输出时间轴两端（视频体整体后移 introFrames） | 独立 `<Sequence>` + `IntroOutroCardView` | persona.brand 烘焙 |

时间轴规则的实证：`Clip.tsx` 内 `timeline` 累加（kept segments → outStart）建正向映射，`sourceTime = seg.start + (localOutput - outStart)` 做反映射——**字幕按源时间存、按输出时间显示**，双向换算集中在这两行。dub 反例：segments 映射发生在 dub 文件**生成时**（skills/dub/procedure.py 按 cue 起点拼接），spec 层它是输出时间轴整段文件。

## 5. 重要函数地图

### packages/clip（TS，双端共用）

- `types.ts`
  - `keptSegments` / `videoDurationSeconds` / `introSeconds` / `outroSeconds` / `totalDurationSeconds` — 输出时长推导链（intro + kept + outro）。
  - `removeRange(spec, start, end)` — 非破坏删段：相交部分切出 `hidden` 段（可恢复），区间内 caption cue 真删（N-16：恢复语义归快照层）。**Python 同名镜像**（NAMING §1）。
  - `setTrim(spec, start, end)` — 移动首/末保留段边界。`trimBounds` / `sourceDuration` 为滑杆供数。
  - `ASPECT_DIMENSIONS`（9:16/1:1/16:9 三档）/ `COMPOSITION_FPS=30`（合成 fps，与源 fps 无关）。
- `Clip.tsx` — 唯一渲染组件。关键内部：`timeline` 累加映射与 `sourceTime` 反映射（§4）；`groupLines`（7 词一行）；`lineRevealFrame`（行级入场帧，sourceTime 映射的逆运算）；`captionEntrance`（entrance 原语 → opacity/transform，每值过 libass 映射闸）；stack 布局（锚点上下半场决定容器生长方向，滑窗 `maxLines`）；双语对照配对；`pointStyle`（归一化中心点 → CSS translate，= libass `\pos`）；尺寸按画面推导（`size × height/1920` 参考系）。
- `captions.ts` — `CAPTION_PRESETS` **字幕样式目录**（注册表先例）：样式 = 三原语（`layout` × `entrance` × `wordHighlight`）组合；**加样式 = 一行登记**（TS 类型由此推导，Python 只校验成员）；**加原语 = 过 libass 映射闸 + Clip.tsx 一分支**（CSS ∩ libass 子集纪律）。
- `fonts.ts` — `fontFamilyFor`（品牌字体枚举 → 字体族）。
- `Root.tsx` — `calculateMetadata`：aspect → 画幅尺寸、`totalDurationSeconds` → 合成时长；`DEFAULT_SPEC` 兜底。

### apps/render（Node 黑盒）

- `server.ts` — `POST /render`：校验 → 临时目录 → `renderClip` → 预签名 PUT 上传 → 返回对象键。`/cache` 静态服务把本地落盘的源经 loopback 喂回 Remotion（CORS `*` 因 bundle-server 跨源 fetch）。
- `render.ts`
  - `renderClip(spec, outDir, basename)` — 主流程：`stageRemoteSource`（源先落盘）→ 共享 bundle（一次构建复用）→ `selectComposition` → `renderMedia`（h264）→ SRT → `normalizeLoudness`。
  - `normalizeLoudness` — EBU R128 双 pass 响度归一（`-16 LUFS / TP -1.5`），ffmpeg 二进制取自 Remotion compositor 包（`resolveFfBinary`）；**增强不是正确性**——失败保留原音，永不翻车渲染；无声产物（stills 幻灯）跳过。
  - `stageRemoteSource`（stage.ts）— Remotion 内部 asset fetch 不走系统代理、整文件下载挤在取帧预算内（慢源 = delayRender 超时灾难）；staging 侧代理感知（`dispatcherFor` 读 HTTPS_PROXY）、按 URL 去重、LRU 驱逐。
- `srt.ts` — `captionTrackToSrt`：7 词成行、按 `clipStart`（首个保留段起点）重定基——SRT 与 MP4 同起点，交接 CapCut 的交付物。

### apps/api/app/pipeline（Python 侧）

- `clip_spec.py`
  - `build_clip_spec(source, segment, …)` — spec 唯一构建处。video / stills 两分支（stills：有声 → 词级字幕 + 语音轨；无声 → `SECS_PER_IMAGE` 定长幻灯 + 合成段）。
  - `locate_span(words, segment)` — 选段定位：agent 数值时间戳优先（**向最近词边界吸附**），否则 start/end marker 文本匹配（渐短探针容忍 LLM 改写），**永不 raise**，兜底全段。
  - `remove_range` / `set_trim` — TS 函数的 Python 镜像（同名同义，§1）。
- `rendering.py`
  - `render_output(output_id)` — 驱动主流程：读 spec → `_absolutize` 烘焙 → 预签名 PUT URL → POST 渲染服务 → 写 `files` + COMPLETED。**竞态守卫**：条件 UPDATE（`render_status == RENDERING`）——渲染中途 morph 重排（re-pend）时本次产物为陈品，删孤键、镜像 superseded，永不覆盖新 spec。
  - `_absolutize(spec)` — **烘焙缝现状形态**：spec 内存储相对键 → 绝对 URL（source.url / image_urls / brand 卡 media / music / dub）——轨道模型的泳道投影 fold 将来就加在这里。
  - `_mirror_render_node` — 渲染生命周期镜像到 run 的 render 步骤（可见性 + 成本的家；run-less 重渲染路径不受影响）。
- 认领谓词：`outputs.render_status`（NULL = 未请求 / PENDING 可认领），worker `FOR UPDATE SKIP LOCKED`（ADR-017）。

### 写纪律（Operation Model 联动）

`render_spec` 的一切修改经 `operations/service.py`（ADR-032）：op 注册表校验 → 应用 → 快照落 `spec_after`；undo/redo/版本跳转对全部 op 统一成立；`base_hash` 乐观锁 409。editor 与 chat 是同一能力层的两个薄适配器（ADR-033）。

## 6. 现状不变量（任何演进不得破坏）

1. **单一画笔**：preview 与成片同一 `<Clip>`——新增渲染行为只准进 packages/clip。
2. **契约无渲染器概念**：spec 只描"是什么"；样式走枚举目录，每个原语过 CSS ∩ libass 闸。
3. **渲染器不读库**：一切外部引用在烘焙缝解析为绝对 URL；spec 自足。
4. **写必经 operations**：快照 undo 与漂移自愈（hash 链校验失败补 `set_spec`）。
5. **时间轴分道**：`_track` 字段 = 源时间轴（经 segments 映射）；块字段 = 输出时间轴（dub/音乐/头尾卡）。新增字段必须显式归属其一——这是 §8 轨道纪律的现状形态。
6. **尺寸按画面推导**：字号是 1080×1920 参考系上的参考值，按帧高缩放；字幕块宽 84% 随帧宽自适应。

## 7. 渲染器替换路径（spec 不变）

| 触发 | 换成 | 成本 |
|:---|:---|:---|
| Remotion 成本 / 规模问题 | **手写 Python+FFmpeg+libass**：clip-spec→FFmpeg filtergraph 一遍出；字幕用 `.ass`，预览侧用 **libass.wasm（JavascriptSubtitlesOctopus）** 渲染同一份 .ass → 两端共享 libass 保 parity | 渲染逻辑自写；.ass 动画有天花板（我们碰不到） |
| 要"视频不出浏览器" + 降本 | **客户端 `@remotion/web-renderer`（WebCodecs)**：我们的合成落在其 CSS 子集内，现实可换 | alpha 阶段；GDPR 收益有限（ASR 仍在服务端）；可能仍需服务端代理 |

> GDPR 主线仍是**服务端全栈 + EU 区部署**；客户端渲染只是降本备选，不是合规答案。

## 8. 契约演进方向：轨道模型（已收敛，待 ADR 过会）

> 触发器：crop_track（关键帧轨）/ reframe_clip（分镜）/ layers（B-roll、双机位访谈）同时涌入。**2026-08-17 过会（ADR-044）转正**：同日用户拍板——破坏性更新授权（旧数据/旧规划不构成约束）+ P2 契约项（segments widen / layers / 锚 / 过渡枚举 / ops 寻址 / 泳道投影）提前至本批（08-17~18），由 12 操作闭包判据直接驱动（走查全表见简报 `tasks/track-model.md` 附录 §8）。

### 8.1 判据

**操作集闭包**：registry 合法 op/skill 的任意序列（用户聊 N 轮）产出的 spec 仍可表示、可渲染、可继续改。弹性验收机械化：spec 顶层字段 ⊆ 轨道注册表（启动自检对账，⊆ 同款代数）+ phantom track 自检（注册一条假轨，渲染/寻址/合规/计价自动接管，消费方零改动）。

### 8.2 形态：锚定 = 存储格式，泳道 = 编译产物

```
静止面（ops/spec 落库）            渲染面（烘焙缝一次 fold，用完即弃）
─────────────────────              ──────────────────────────────
segments（源时刻）         ──求导──►  lane 铺平：绝对时间 + z 序
layers[{anchor, …}]                  （渲染器/FFmpeg 后路只吃这个）
transition（挂段进场边）
▲ ops 只动这里；undo 快照存这里      ▲ 永不编辑、永不落库、永不进快照
```

- 位置**不落库**：层条目挂语义锚，输出时间窗由求导派生——"剪两段、尾段后移"这类 ripple 手势在声明式模型里不存在（插入一段，尾部自动正确）。
- 锚三形态：**段锚**（`{segment_id + 源时刻偏移}`，内容跟随；段删则级联删并告知）/ **边锚**（`{head|tail + 偏移}`；intro/outro 本质即边锚块）/ **比例锚**（`{ratio}`，预留）。绝对时间永不在静止面出现。
- 双真相禁令：锚与泳道**不得平级共存在同一行数据**（双写必分歧）；泳道只是编译产物，永不可写。

### 8.3 词汇表（命名宪法 §8 登记草案）

| 中文 | 英文 | 定义 | 不是什么 |
|---|---|---|---|
| 轨道 | `track` | spec 命名分区 = 注册表一条声明；**裸用违规，必须带家族限定**（N-11 同款判例） | 不是 NLE 自由轨；用户永不见 |
| 主轨 | main track | `source` + `segments`，输出 = 数组序连接；唯一持剪辑语义（hidden/trim/reorder） | — |
| 段 | `segment` | 主轨一行：`{asset_id?（缺省=主源）, start, end, hidden}`；异源插入 = 带 asset_id 的段 | 不是 block（讨论期占位词，退役） |
| 数据轨 | data track（`*_track`） | 源时间轴时序数据：caption / translation / crop（关键帧采样） | 不参与叠放 |
| 层 | `layer`（字段 `layers`） | 锚定放置物列表：kind 枚举（`broll` / `text_callout` / `pip` / `motion_graphic`），z 序渲染，条目可带 `source_ref` 回放（PiP）与 `provenance`（ADR-026 必读） | 不是自由轨；不撞 UI 浮层（overlay 一词归 GenerationOverlay/overlay-surface，避让 N-27 同型撞车） |
| 锚 | `anchor` | 层条目的语义挂接；输出时间派生不落库 | 不是时间码 |
| 过渡 | `transition` | 段的进场边效果枚举（none/fade/dip），挂在段上随换序走 | 不是转场画廊（2-3 枚举封顶） |
| 块轨 | block track | 单值轨，输出时间轴：music / dub / title / 头尾卡 | dub⇄原声互斥在注册表声明 |

讨论期占位词 lane / blocks / junctions / placements 一律不采用（草稿阶段死亡，不留痕）。

### 8.4 轨道注册表（TRACK_REGISTRY）

每条轨一份声明，消费方全部 fold 注册表（不再逐字段特判）：

```python
TrackDef(
    family,        # sequence | data | layer | block
    timeline,      # source | output | derived——只声明不实现，remap 全库一个函数
    owner,         # 唯一写者技能（表归属契约的 spec 转置；撞轨 = 编译期 422）
    mutex,         # 互斥槽位声明（dub ⇄ original）
    provenance,    # C2PA 分类器 fold（ADR-026）
    url_fields,    # _absolutize fold
    checks,        # 确定性工艺检查（crop 不出人脸框 / 驻留达标 / 字幕不溢出——
                   # verify 的第一批住户，随技能包出生，不等 Phase 3 框架）
)
```

施工序（2026-08-17 拍板修订）：注册表随 12 操作闭包批建立（08-17~18——现有 8 轨 + layers 轨平移登记 + 两条自检 + segments widen / 锚 / 过渡枚举 / 六 op / 泳道投影，先锚后物顺序不反）；`crop_track`（keyframes 族首个渲染件 = 采样器）与 reframe 工艺检查项随 08-19 能力批同批——地基交付后它 = 一条登记 + 一个采样器，忘登记则字段分区自检直接红。
