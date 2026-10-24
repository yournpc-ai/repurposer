# Home 创作入口与真实样片——当前状态

> Status: 前端货架、composer 预填与可见性暂停已有代码层结果。**SaaS launch film 货架使用对应制作链真实样片；Text Animation 与 Product Demos 共 6 卡仍复用 SaaS 片作布局占位，不能当作这两种能力的验收产物。** 下一步是用户选定真实样片后做数据替换，并分别完成 Film/MG 制作能力验收。

## 1. 数据来源与职责

- MG demo 货架来自前端 `components/home/recipeFamilies.ts:RECIPE_FAMILIES`，视频 URL 为内容寻址的 `demo/` 对象，不走 recipes API。
- 服务端 `GET /api/v1/recipes` 只提供 RecipeCard 配方卡；前端 `RECIPE_CARD_FAMILY` 决定其货架归属。新增/隐藏卡片不能只改一边后宣称全站一致。
- 空 shelf/sub/family 不渲染；保留座不是可见占位卡。`DEMO_HIDDEN_CARDS` 只控制货架曝光，不删除服务端能力或 prompt 注册。
- 货架以用户任务组织，不以输出介质堆砌；首屏 hero 与 composer 仍是主入口，货架位于其下。

## 2. 当前样片真值

| 货架 | 当前内容 | 可以证明什么 | 不能证明什么 |
|---|---|---|---|
| SaaS / launch film | linear、snappify Code、snappify Frame、zymix 对应链真实渲染 | launch-film 货架与对应样片 | 其他货架能力、所有网站/所有时长都成功 |
| Text Animation：`text-anim-lines` / `text-anim-brand` / `text-anim-two-lines` | 复用 snappify/linear 片 | 布局、画幅、预填与播放交互 | 短句分组、逐字/逐行动画或品牌文字片制作能力 |
| Product Demos：`product-demo-walkthrough` / `product-demo-highlights` / `product-demo-captioned` | 复用 zymix/snappify 片 | 布局、画幅、预填与播放交互 | 操作演示、功能亮点或录屏文字叠加制作能力 |

占位事实留在注册表条目注释和本文，不在 UI 加“占位”横幅；因此任何评审、营销或验收都不得仅凭卡面把占位称为真实能力。

## 3. 交互合同

- 卡片点击唯一归宿是 composer 预填 `promptTemplate`/demo prompt；不自动发送、不建项目/run、不打开模板编辑器。
- 草稿为空或仍等于上次预填原文时，点另一卡可替换预填；已有用户文字或 @-mention 时保留原文并换行追加，不静默清空。
- prompt 是完整用户口吻需求，不暴露工具/spec/版本，不锁死画幅、幕数、时长或配音；缺素材由正常 Chat 补问。
- Product Demos 的 prompt 只承诺使用用户上传的视频/录屏，不承诺自动打开网站录屏；网站 capture 能力由 Film 合同另行授权与验收。
- Demo 视频静音循环；IntersectionObserver 离屏暂停、回视口恢复，声音遵循全局单例互斥。每个货架独立滚动，画幅按真实文件，不拉伸。
- en/zh 同步；窄屏无页面级横向溢出。组件复用现有 RecipeTabs/RecipeShelf，不为每条货架复制实现。

## 4. 真实样片替换

1. 用户先选定目标样片，并确认它确实由对应当前制作链生成；不要用另一配方成片顶替。
2. 在 `recipeFamilies.ts` 对应 demo entry 替换 `url`，按真实文件更新 `orientation`；保留稳定 id，非必要不改 prefill。
3. 若真片语义要求调整 prompt，只改 `recipes.shelf.demos.<id>.prompt` 的 en/zh 镜像；不得借换片引入“保证同样效果”承诺。
4. 新片继续使用 `demo/` 保留前缀与内容寻址，不覆盖共享 key；上传/发布是独立授权操作。
5. 替换后分别验收：货架交互、样片内容真实性、对应 Chat→方案→授权→制作→交付全旅程。三者不可互相代替。

## 5. 当前验证边界

已有货架证据只覆盖双语渲染、视频可播、滚动独立、离屏暂停、预填不覆盖用户草稿与窄屏布局；它**不覆盖** Text Animation/Product Demos 的真实制作链。本文本轮只做文档与只读代码核对，未重跑 tsc/vitest/CDP，也未生成或替换任何样片。

真实样片到位前，Film progress 与 PROGRESS 必须继续保留此欠账；不要因“首页已能点”关闭。

## Prohibited Behaviors

- 禁把占位片写成真实能力证据或用于制作链验收。
- 禁为换片新增后端接口、组件副本、模板编辑器或第二预填入口。
- 禁静默覆盖用户草稿、自动发送、自动建 run、无真片上架空壳。
- 禁覆盖共享 demo key、拉伸画幅、绕开声音互斥或让离屏视频继续无界解码。
