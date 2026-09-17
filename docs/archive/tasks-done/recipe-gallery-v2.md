# 配方画廊 v2 施工简报（recipe-gallery-v2）

> Status: 已拍板未实施（2026-08-23 用户拍板，ADR-048；施工窗口待指认——PROGRESS 第十周 10-09 行为当前占位）
>
> 母决策：`docs/DECISIONS.md` ADR-048（八卡阵容 / 示意图封面 / 证据层移交 / 两级闸门）。
> 卡面规格唯一事实源：`docs/RECIPES.md` §4（八卡阵容表 + §4.5 配音卡 + §4.6 文本族 + §4.7 撤座 + §4.8 闸门）与 §7.3（布局条款）。
> 封面几何与动画稿：`docs/tasks/recipe-gallery-v2-covers.html`（8 张封面 SVG 草稿 + CSS 关键帧，逐卡可开浏览器核对）。
> 本文只管施工：改动点、分期、验收、禁令。设计论证不复述——查 ADR-048。

---

## 1. 背景一句话

画廊从「真实 teaser 海报墙」改为「黑白灰工艺示意图菜单」：卡面零真实素材、零媒体请求，真实成对前后对比移交 overlay 示例 tab（= 准入验收闸）；阵容 5 → 8（4 live 原样 + 原声AI配音复座 + 文本族三卡新增；虚拟视频出列进需求池；语音转观点否决）。

## 2. 已核实事实（动工前复核，勿凭记忆）

- 配方注册表在**服务端**：`apps/api/app/pipeline/recipes.py`（`RecipeEntry` × 5：4 live + 1 reserved 虚拟视频），经 `GET /api/v1/recipes` 下发；前端 `apps/web/src/lib/recipes.ts` 是消费方/类型层。
- 卡面文案在 i18n：`recipes.<id>.*`（en.ts 为源，zh.ts 镜像）；共享键 `recipes.flow.*` / `recipes.tags.*` / `recipes.materials.*`。
- 卡面组件：`apps/web/src/components/home/RecipeCard.tsx`（218 行，当前 = poster + capability chip + aspect badge + hover 视频/声音状态机）。
- 网格：`apps/web/src/components/home/MasonryGrid.tsx` 仅被 `apps/web/src/routes/_app.home.tsx` 消费（featured span:2 只有 image-video 一张）。
- overlay 已有：`apps/web/src/components/recipes/RecipeInspectOverlay.tsx` + `recipeFlow.ts`（示例 tab = example_assets/example_outputs 平铺，已存在，本批不动结构）。
- 烘焙物料 URL 清单：`apps/web/src/lib/recipes.assets.ts`（**生成物**，`apps/api/scripts/upload_recipe_assets.py` 重生成；demo/ 桶受 reset 保护）。
- 验收闸：`apps/api/scripts/accept_prompt_surface.py`（CARDS 表逐卡 × 双语 × 3 试；locale 真串漂移断言已在）。
- `RecipeEntry.aspect` 字段**保留**：卡面 badge 退役 ≠ 字段删除——overlay 示例区输出卡仍按 `card.aspect` 出框（08-14 走查拍板）。

## 3. 设计决策索引（全部已定，施工照做勿再开题）

| # | 决策 | 出处 |
|---|---|---|
| D1 | 八卡阵容（id 定死）：`highlight-clips` / `multilingual-subs` / `voice-dub` / `reframe` / `image-video` / `social-post` / `quote-cards` / `carousel` | ADR-048 ①，RECIPES §4 |
| D2 | 封面 = 内联 SVG 工艺示意图（三档灰阶 token 驱动，16:10，左素材→右成品，hover CSS 关键帧过程动画）；真实素材永不上卡面 | ADR-048 ② |
| D3 | 卡下三行文字：菜名 / 承诺句（2 行 clamp）/ 适用素材（meta 行，新 i18n 字段） | ADR-048 ③ |
| D4 | 画幅 badge、类别 chip、featured 跨列、MasonryGrid 全退役；统一 `grid-cols-2 md:grid-cols-3 lg:grid-cols-4` | ADR-048 ④ |
| D5 | 渠道不进卡面：品类名（社媒帖，非「LinkedIn 帖」）；默认渠道住预填模板；chat 恒胜 | ADR-048 ⑤ |
| D6 | 证据层 = overlay 示例 tab 真实成对前后对比；拿不出成对示例的卡不进网格；`reserved`/Soon 形态退役 | ADR-048 ⑥ |
| D7 | 准入两级闸门：① 场景真实性 ② 形态或环路不可替代（ChatGPT 测试，环路价值上卡面可豁免） | ADR-048 ⑦，RECIPES §4.8 |
| D8 | hover 带声裁决（2026-08-21）迁入 overlay 示例 tab（点击 = 手势，声音原生合法）；网格 hover 只剩 CSS 动画 + Remix/expand 双件 | ADR-048 ⑧（ADR-046 附⑯ 修订） |

## 4. 改动点

### Phase A — 网格与卡面换骨（4 live 卡先换新装）

1. **封面组件族**：新建 `apps/web/src/components/recipes/covers/`——每卡一个 React 内联 SVG 组件（`HighlightClipsCover.tsx` 等 8 个，Phase A 先落 4 个 live 卡），几何直接誊 `recipe-gallery-v2-covers.html` 对应卡片 `<svg>`；另加 `index.ts` 按配方 id 映射。**色律铁规**：三色只用 `currentColor` 三档透明度（结构 `opacity-40` / 主体 `opacity-85` / 结果实心）或 `fill="currentColor"` + 父级 `text-foreground/*`——**禁任何 hex / 硬编码色值**，双主题反相由 token 免费获得。动画 = 演示稿里的 CSS 关键帧原样搬进（`transform-box: fill-box` + nth-child 错峰 delay）；`prefers-reduced-motion` 降级静止帧。
2. **RecipeCard.tsx 重写**：删视频/poster/声音全部机械（`<video>`、unmuted play 逻辑、声音开关、badge、capability chip）；封面井 = `bg-inset` 圆角块承 SVG（fill-first，无 ring 无影）；hover = 动画播放 + 白色 stadium Remix 丸（`Wand2`，居中）+ expand 右上（双件同开 overlay，ADR-040 唯一发射路径不变）；卡下三行文字（承诺句 `line-clamp-2`，适用行 `text-meta`）。
3. **网格**：`_app.home.tsx` 换统一 grid 容器；**MasonryGrid.tsx 删除**（消费方唯一，无遗留 import）；`recipes.ts` 消费侧同步去掉 featured/span 概念（若类型层有）。
4. **i18n**：新增 `recipes.<id>.inputScenario`（适用素材行）× 现有 4 卡；en 先写 zh 镜像。

### Phase B — 新四卡 authoring（受示例烘焙闸门约束）

5. **注册表 5→8**：`recipes.py` 新增 `voice-dub` / `social-post` / `quote-cards` / `carousel` 四条 `RecipeEntry`（status 直接 `live`——reserved 形态退役，进网格前必须已过闸）；**虚拟视频 reserved 条目删除**（出列入需求池，PROGRESS 有行）；`RecipeEntry.status` 的 `Literal["live","reserved"]` 收窄为 `"live"`（含 `RecipePublic`）， Soon 渲染分支前端同步删。
6. **i18n 四卡全套**：`recipes.<id>.{name,promise,inputScenario,promptTemplate,inputTitle,inputHint}` + 所需 `recipes.flow.*` / `recipes.tags.*` / `recipes.materials.*` 新键，en 源 zh 镜像。卡名定死：voice-dub = **原声AI配音**（en: Original-voice AI dub）；social-post = 社媒帖；quote-cards = 金句卡；carousel = 轮播。**承诺句戒律**：社媒帖必须带环路价值句（「用你的风格写，发哪个平台你定」义），禁营销形容词；渠道名只准出现在 promptTemplate 内（默认渠道），卡面文案零渠道名。
7. **示例烘焙（硬闸门）**：voice-dub 复用 dub 对照包（零新烘焙，`subs-contrast-*` 同桶 dub 四片已在）；文本族三卡走真管线跑批 harvest（先例脚本 `bake_dub_contrast.py` / `bake_reframe_demos.py` 形态），成对「输入素材 ↔ 输出产物」内容寻址入 demo/ 桶，`upload_recipe_assets.py` 重生成 manifest。**拿不出成对示例的卡不进网格**（D6）——可以先合 Phase A，单卡示例不齐就压着不注册。
8. **验收闸扩展**：`accept_prompt_surface.py` CARDS 表补 4 新卡（模板串镜像 locale 真串，漂移断言自动生效）；4 新卡 × 双语 × 3 试全绿才准点亮。

## 5. 验收清单

- [ ] 200px 无字测试：封面缩 200px 宽 + 隐藏全部文字，每对近邻可区分（字幕 vs 配音：视频帧+字幕行 vs 人头+波形+语言 chip；金句卡 vs 社媒帖：大引号卡 vs 头像+互动条 feed）——逐对截图入 PR 描述。
- [ ] 双主题截图：8 卡 × light/dark，封面灰阶正确反相，无 hex 色（grep covers/ 证明）。
- [ ] 网格零媒体请求：home 加载 Network 面板无 mp4/poster 请求（gallery 区域）。
- [ ] hover：CSS 动画播放 + Remix/expand 双件开同一 overlay；`prefers-reduced-motion` 下静止。
- [ ] overlay 示例 tab：8 卡每张至少一对真实成对示例；hover/点击带声原生可用。
- [ ] `accept_prompt_surface.py` 8 卡 × 双语全绿。
- [ ] `reserved`/Soon/MasonryGrid/featured/aspect-badge/capability-chip 全站 grep 清零；`recipes.py` tsc 等价物（`compileall`）+ web `tsc` 绿。
- [ ] SSR：home 首屏 200 无 hydration 警告（封面 SVG 纯静态，天然 SSR 安全）。

## 6. Prohibited Behaviors

- 禁真实素材上卡面（视频/poster/图片一律不许；卡面零媒体请求是验收项）。
- 禁复活 badge / chip / featured 跨列 / MasonryGrid / Soon 占位卡——形态已退役，不是「先留着」。
- 禁卡面出现渠道名（LinkedIn/TikTok/ins/X）；渠道只住预填模板文案。
- 禁封面 hex 色 / 硬编码色值 / 第四档灰阶；禁产品截图式封面（封面 = 过程图解，不是输出承诺——配音卡不画字幕即此条款的判例）。
- 禁营销形容词与造词进承诺句（文案纪律 = CLAUDE.md 定位节）；社媒帖承诺句必须带环路价值，否则过不了闸门②。
- 禁给新卡发明第二发射路径（点击/Remix/expand 都进同一个检视 overlay，ADR-040）。
- 禁在 overlay 里加生成按钮/直接跑 run（A 形态否决不变）；发射 = 预填 + 上传 + 发送进 chat。
- 禁动 `RecipeEntry.aspect` 字段（overlay 示例区仍消费它）。
- 新卡未过「成对示例烘焙 + 验收闸全绿」双闸，禁止注册进 `recipes.py`（没有 reserved 中间态可挂）。
- i18n 禁只写一端；en 是源，`zh: Resources` 类型会抓漏键。

## 7. 排期锚

PROGRESS 第十周五 10-09 行（画廊 v2 八卡施工收口，随运营端批次验收）；窗口若再提前，改 PROGRESS 一处即可，本文不另记日期。
