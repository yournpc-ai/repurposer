# Film 采集升档（skill 能力复刻）：引擎换血 + 元素相机 + 节拍锁 + 子页发现

> Status: **未开工**。母法 = ADR-121（短式）；拍板 = 2026-10-15 用户（「全上」——B2 元素相机第一批就进，不拆先后）。
>
> 起源：ADR-120 三批（E1 分镜核对 / E2 配音 BGM / E3 画幅）收口后，与原 launch-film skill（`/Users/sylas/skills/launch-film/`）的残余差距全部在**采集与素材侧**：① one-shot CLI 截图无滚动无等待，撞 canvas/JS 首屏即黑（2026-10-15 linear.app 实证：fold 截图除 nav 条全黑，ui 幕忠实渲染了黑截图）；② ui 幕 `focuses` 的 x/y/zoom 由模型盲猜，validator 只查 [0,1] 界；③ BGM 只铺床不锁节拍；④ 一次只采一个显式 URL。skill 侧四件做法均已验证（capture.mjs / elements.json / beats.mjs），本批 = 复刻而非发明。
>
> 接续会话先读：`docs/DECISIONS.md` ADR-121、本简报全文、`app/tools/research/capture.py`（现行引擎与三律）、`/Users/sylas/skills/launch-film/scripts/capture.mjs`（移植母本）。

> 边界（与 chat 读面共存）：`get_web_page` / `search_web`（chat 感知族读工具，`tools/research/web.py` 的文本抓取投影）是**讨论高度**的读——用户丢链接「你看看？」走它，零资产产生。本批动的 `capture.py` 是**素材高度**——链接进 `material_urls` 才走它，产 web_page 资产。两个高度共享 `tools/research/` 一个包，互不替代；本批不动 web.py。已知限制：fetch_text 对 JS 重渲染页面（SPA）文本稀薄——degrade-honest 兜住，讨论高度可接受；若成真实抱怨，B1 的 playwright 会话可复用为浏览器级文本读（ future option，本批不做）。

## 1. 目标形态

贴一个官网 URL，采集产出的素材足以撑起 75–120s keynote 片：

```
首页 URL → playwright 会话（政策代理内）→ 关弹窗 → 滚动预载（触发懒加载）
→ fold 截图 + 逐 section 截图（anchors 探测，≤6 张）+ 元素清单（带坐标）
→ 同 host 子页发现（≤3，BAD_LINK 过滤）→ 每页同法复采
→ storyboarder 看到的宇宙 = 多张真实截图 + manifest + 元素表
→ ui 幕相机点名元素 id（服务端确定性解坐标，模型永不发明坐标）
→ 成片幕边界 snap 到配乐节拍网格
```

## 2. 施工切分

| # | 件 | 座位 | 工期 |
|---|---|---|---|
| B1 | **采集引擎换血**：`_screenshot_with_policy` 的 Chrome CLI one-shot → playwright-python 驱系统 Chrome（`executable_path=resolve_chrome_path()`，免浏览器下载；proxy 指 `_PolicyProxy` 端口——它已是完整 CONNECT 隧道，零改动）。移植 skill 四段已验证 JS 为 `page.evaluate()` 字符串：`settle`（networkidle+600ms）/ `preload`（400px×180ms 步进滚动，40k px 帽，图片 complete race 5s）/ cookie 关闭（CONSENT/REJECT/ACCEPT 三族正则 + hide 兜底）/ `anchors`（大标题探测，chrome 排除）。产出 = fold + N section 截图（≤6），存资产前缀 `web-capture-<uuid>-s<i>.png`。Schema：`WebPageMeta.shots: list[ShotRef{key,y,heading}]`（`extra="allow"` 天然容忍旧行），`screenshot_key` 保留 = fold。`FilmSceneUi` 加 `shot: int = 0` + validator 范围检查 + `build_film_spec` 取 `shots[shot].key | screenshot_key`。**渲染侧零改动** | `tools/research/capture.py` / `models/schemas.py` / `tools/film/storyboard.py` | ~1 天 |
| B2 | **元素清单 + 相机点名**：同一 browser session 跑 skill 的 `elements()` evaluate（每 shot 一份，元素 id 全页唯一）。`WebPageMeta.elements: list[PageElement{id,kind,text,box}]`（capture 侧 cap）。prompt `_assemble` 印元素表（id/kind/text/box）。`FilmFocus` 加 `element: str | None`；`build_film_spec` 确定性解出 x/y/zoom（元素盒中心归一化 + 盒尺寸推 zoom）；裸 x/y 保留为读容忍降级路径。渲染侧零改动 | 同 B1 + `prompts/film_storyboard.j2` | ~0.5 天 |
| B3 | **节拍锁剪辑**：音乐库 seed 期离线分析一次（beat grid + bpm 存 `Music.meta`，`scripts/seed_default_music.py` reconcile 同座——缺则补算）。`build_film_spec` 尾部把幕边界 snap 到最近 beat（仅 ±0.2s 容差内才动）；顺序钉死：narration 合成 → snap → 越界幕按既有 1.35× 律重合成 | `pipeline/music.py` / `tools/film/storyboard.py` / seed 脚本 | ~0.5 天 |
| B4 | **子页发现**：capture 入口收首页 URL 后，从 manifest links 挑同 host 链接（移植 skill `BAD_LINK` 过滤正则），cap 3，逐条复用现有 capture 入口产独立 web_page 资产。`StoryboardPage` 列表本就一对多，**零 schema 改动** | `tools/research/capture.py` / `pipeline/web_capture.py` | ~0.5 天 |

依赖新增唯一：`playwright`（pip，B1）。其余全是代码。

## 3. 风险与缓解

- ⚠️ **playwright ↔ 系统 Chrome 版本兼容**：`executable_path` 驱 branded Chrome 是官方支持路径，但版本漂移可能断——fallback = `playwright install chromium` 专用浏览器双轨并存（`resolve_chrome_path` 增加 playwright 缓存目录探测序）。
- ⚠️ **_PolicyProxy 长会话稳定性**：现为 CLI one-shot 短会话设计，playwright 是长会话多请求复用（keep-alive + CONNECT 隧道复用）——B1 上午真站 smoke 先行（MG 批 D1 同款缓解：github.com + linear.app 双站取证后再铺功能）。
- 采集时长上升（滚动预载 ≈ 页面高度/400×180ms + settle）→ `web_capture_timeout_seconds` 与 processor 超时预算同批重估。

## Prohibited Behaviors

1. **三律不动**：`_PolicyProxy`（SSRF 浏览器级拦截）/ 系统 Chrome 优先 / degrade-honest（截图半败 = `screenshot=None` 链不炸，manifest 是本体）。
2. **禁第二条采集链**：发现、复采、section 截图全部骑同一个 playwright 会话工厂；禁为新能力开平行入口。
3. **相机目标永不发明坐标**：`element` id 点名是正路，裸 x/y 仅作旧数据读容忍；prompt 法条同批写明「camera targets name element ids」。
4. **节拍网格禁运行时测速**：aubio/librosa/essentia 一律不入依赖；seed 期预计算是唯一座位，运行时只读 `Music.meta`。
5. **子页发现三闸**：同 host + `BAD_LINK` 过滤 + cap 3；禁爬外站、禁递归深挖。
6. **容量 capture 侧 cap**：shots ≤6、elements 每 shot 截断——meta 膨胀防线在出生地，不在消费端。
7. **逐字 grounding 不扩到 narration**：配音 = 言语复述页面事实（E2 已拍板）；validator 的 manifest 覆盖律只管屏上文案。
8. **渲染侧本批零改动**：ui 幕消费的仍是 `image` + `focuses(x/y/zoom)`；任何渲染器改动说明 B1/B2 的 spec 投影设计错了，回炉。

## 4. 验收

- **B1**：重采 linear.app → section shots 出现 DOM 渲染的真内容（对照 2026-10-15 fold-only 黑截图）；fold shot 仍在（hero/end 幕图源不变）；degrade 实证（Chrome 缺席 → `screenshot=None` 链不炸）。
- **B2**：storyboarder 的 ui 幕 focuses 以 element id 为主（`film_stage_ledger` 仪表加观察位）；spec build 解出坐标 ∈ [0,1] 且落在元素盒内。
- **B3**：成片幕边界与 beat grid 对齐（容差内）；snap 后 narration 无越界截断。
- **B4**：贴首页 URL → 产出 1+≤3 个 web_page 资产；login/blog/legal 族链接不进。
- **端到端**：`scratch/demo-films/` 三片（16:9/1:1/9:16）重跑——ui 幕真内容、切点落拍、三画幅缩放律不变。
- **仪式链**：pytest + check_gates + prompt_gate（`film_storyboard.j2` 与 `_assemble` 都触 prompt 面）+ S11 复跑 + render tsc / web vitest 基线不动（渲染零改动声明的实证）。
