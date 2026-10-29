# Home 创作入口与真实样片——当前状态

> Status: 前端货架、composer 预填与可见性暂停已有代码层结果。**Home 的 Ads 族只展示 Text Animation（文字短片）与 Product Promo 两个子 tab；Text Animation 使用项目 `9345ddc2` 与 `f52c489c` 的真实文字源 Film，Product Promo 前三张为 ZYMIX / AgentVeil 真片，第三张使用项目 `bd2b2f2e` 最新交付 `558c6547`，第四张仍复用既有片作布局占位。** 下一步由用户选定 Product Promo 第四张真实样片后做数据替换，并分别完成对应制作能力验收。

## 1. 数据来源与职责

- MG demo 货架来自前端 `components/home/recipeFamilies.ts:RECIPE_FAMILIES`，视频 URL 为内容寻址的 `demo/` 对象，不走 recipes API。
- 服务端 `GET /api/v1/recipes` 只提供 RecipeCard 配方卡；前端 `RECIPE_CARD_FAMILY` 决定其货架归属。新增/隐藏卡片不能只改一边后宣称全站一致。
- 空 shelf/sub/family 不渲染；保留座不是可见占位卡。`DEMO_HIDDEN_CARDS` 只控制货架曝光，不删除服务端能力或 prompt 注册。
- 货架以用户任务组织，不以输出介质堆砌；首屏 hero 与 composer 仍是主入口，货架位于其下。

## 2. 当前样片真值

| 货架 | 当前内容 | 可以证明什么 | 不能证明什么 |
|---|---|---|---|
| Text Animation：`text-short-gentle-close` / `text-short-genesis` | 当前文字源 Film 链真实产物：`9345ddc2` / Output `a9701fe0`（20.6 秒）与 `f52c489c` / Output `50a6b40d`（68.1 秒），均 16:9 | 两条文字短片样例的内容、画幅、货架布局、预填与播放交互 | 新预填文案的完整 Chat→制作旅程；其他文字短片需求都必然成功 |
| Product Promo：`product-demo-zymix` / `product-demo-highlights` / `product-demo-captioned` / `product-demo-walkthrough` | `product-demo-zymix`（项目 `8577f1ff`、Output `8beb17c9`）与 `product-demo-highlights`（项目 `b7530c00`、Output `8cac9bf1`，81.0 秒）均为当前 Film 链真实产物，16:9，含独立屏上说明字幕；第三张 `product-demo-captioned` 使用项目 `bd2b2f2e` 最新交付 Output `558c6547`（AgentVeil in Motion，88.1 秒、1920×1080 / 30fps），第四张复用既有片 | ZYMIX / AgentVeil 真片来源与画幅；当前代码中的排序与预填映射 | 第四张对应能力；任何卡片的完整 Chat→制作旅程；新第二卡的浏览器货架与播放表现 |

占位事实留在注册表条目注释和本文，不在 UI 加“占位”横幅；因此任何评审、营销或验收都不得仅凭卡面把占位称为真实能力。

第三张样片已按用户指定复制到内容寻址 `demo/outputs/product-demo-agentveil-in-motion-420b7ffe.mp4`，与源 Output 字节哈希一致；公开 URL 返回 200。此项仅替换样片和横屏展示，不改变卡片预填需求，不宣称新的制作能力验收。浏览器货架与播放未验证。

## 3. 交互合同

- 卡片点击唯一归宿是 composer 预填 `promptTemplate`/demo prompt；不自动发送、不建项目/run、不打开模板编辑器。
- 草稿为空或仍等于上次预填原文时，点另一卡可替换预填；已有用户文字或 @-mention 时保留原文并换行追加，不静默清空。
- prompt 是完整用户口吻需求，不暴露工具/spec/版本，不锁死用户未要求的画幅、幕数、时长或配音；卡片明确写出的制作要求仍可编辑，后续 chat 修改优先，缺素材由正常 Chat 补问。
- `product-demo-zymix` 与 `product-demo-highlights` 的 prompt 使用网站入口，按 Film 的网站 capture 合同执行与验收；AgentVeil 第二卡预填明确“说明字幕 + 无旁白 + 适度运镜和文字动画”，对应该样片的制作请求。其余 Product Promo 的 prompt 只承诺使用用户上传的视频/录屏，不承诺自动打开网站录屏。
- Demo 视频静音循环；IntersectionObserver 离屏暂停、回视口恢复，声音遵循全局单例互斥。每个货架独立滚动，画幅按真实文件，不拉伸。
- en/zh 同步；窄屏无页面级横向溢出。组件复用现有 RecipeTabs/RecipeShelf，不为每条货架复制实现。

## 4. 真实样片替换

1. 用户先选定目标样片，并确认它确实由对应当前制作链生成；不要用另一配方成片顶替。
2. 在 `recipeFamilies.ts` 对应 demo entry 替换 `url`，按真实文件更新 `orientation`；保留稳定 id，非必要不改 prefill。
3. 若真片语义要求调整 prompt，只改 `recipes.shelf.demos.<id>.prompt` 的 en/zh 镜像；不得借换片引入“保证同样效果”承诺。
4. 新片继续使用 `demo/` 保留前缀与内容寻址，不覆盖共享 key；上传/发布是独立授权操作。
5. 替换后分别验收：货架交互、样片内容真实性、对应 Chat→方案→授权→制作→交付全旅程。三者不可互相代替。

## 5. 当前验证边界

Text Animation 两片均已核对项目 Output、1920×1080 / 30fps、实际时长与多个时间点画面，并分别复制为新的内容寻址 `demo/` 对象，两个公开 URL 均已返回 200；ZYMIX 首卡此前已核对真实文件与画面。Product Promo 第二卡现为项目 `b7530c00` 的 Output `8cac9bf1`：用户提供本地下载文件（MD5 `28f35353`），与链上 Output 的存储对象 MD5 逐字节一致，上传为新的内容寻址 `demo/` 对象（`product-demo-agentveil-28f35353.mp4`），公开 URL 已返回 200 且回读 MD5 一致。逐帧画面核对覆盖的是同项目上一版（Output `d0247a98`，破折号已修、home 静态定场卡、reveal 引子与卡片正常）；`8cac9bf1` 本身只做了哈希同源核对与 81 秒时长核对，**未做逐帧画面复核**，浏览器货架/播放回归也未做。

当前两 tab 阵容、第二卡替换、重命名、预填和 composer 光标修复只有代码层结果，**尚未做浏览器货架/播放与光标回归、tsc/vitest 或新预填对应的真实 Chat 全旅程复验**。这些证据不覆盖 Product Promo 第四张占位卡的制作能力，也不代替任何新卡对应制作链的完整验收。

网页 Film 相机取景已改为 director 从实际 UI shot 的元素清单选择 `camera_focuses`，代码负责 section 截图输入、元素盒解析、主推 1.6× 上限与防露边 camera walk；默认字幕改为只在 Chapter 的 `ch*_ui`、`prove` 与 `plate` 缺槽时自动补轨，`open` / `hero` / `home` / `divider` / `reveal` / `end` 默认无轨但允许显式覆盖，文字源默认不变；Hero、reveal 副文案和 closing card 的引用 accent 星号改由 renderer 消费为强调样式。项目 `0400185c` 样片评审后又落一批确定性修复：home 概览幕改为静态定场卡（3s 固定窗口、修订带 2–6s、无运镜，`camera_focuses` 拒收 home）；`_pick_focus` 默认选择器改为 heading → video/image → text → button（修复"heading 死 kind 导致 Copy 徽章赢过卡片主题"），capture 端开始给 h1–h6/role=heading 发 `heading` kind（存量 capture 库存无此 kind，靠 text 层兜底改善）；字幕 cue 文本在装配与 spec 构建两处剥除 `*...*` 强调标记（字幕无强调通道，存量 storyboard 重渲染自愈）；reveal 引子 `lead_seconds` 封顶 3s（修复 14s 幕 8.4s 单行静止）。项目 `b7530c00` 样片（已吃到第一批修复：home 静态 2.9s、reveal 引子 4.5s、字幕无星号）评审后再落引用文案两条确定性守则：所有上屏槽位（引用与创作 alike）剥离首尾悬挂连接符（"AgentVeil —" 的页标题 head-fit 残段曾在 hero 大字旁烧出一根孤"—"；前导 "-" 永不剥——可能是负号）；`fit:"head"` 截断优先取窗口内最后一个完整句子（修复 reveal 副文案 "…Team and Enterprise add" 断句残段）。交付可见性一批（项目 `b7530c00` v2 换 BGM 后用户仍看到 v1 的取证结论）：画布媒体节点挂载默认从"首版（出生序）"改为"最新版"（null = 最后一行，与 DocumentCard 同约定；灯箱与 dossier 的未上报回退同步改为最新行），消息列表 RunCard 交付收据的 `OutputChatCard` 补 `film` case（复用 ClipCard，film payload 无 `hook`，标题回退链补 `payload.name`）——此前 film 交付在消息列表渲染为 null，桌面端锚卡又被 canvasVisible 门禁压住，唯一可见播放器只有画布节点且默认 v1。同批再收口两处同族缺口：锚卡 `anchorCardOf` 名字回退链补 `payload.name`、时长规格覆盖 film（此前 chip 只剩裸类型词 + 黑首帧空方块；en/zh 补 `chat.anchorCards.types.film`）；历史 detached run 收据 `RunCard` 从展开逐步骤行改为复用 `RunTaskList`/`WorkSegmentRow`（终态收成一条可展开的「Worked for Xm」工作记录，回放无 delivery seal 时诚实回退到 run 可观察步骤跨度），rich 产物卡不变——attached 活 run 的收据形态仍是锚卡 chip（ADR-118 单一渲染面律），detached 历史行的档案形态仍是 rich 卡。以上仅有代码与现行合同结果，**尚未运行 pytest/check_gates、prompt_gate、tsc、真实分镜/revision 或新渲染对照**。既有 AgentVeil Output 与第二位 demo 仍是旧版画面，不因代码修复自动更新；`0400185c` 这部影片需在 chat 走一次 revision（不要 keep_cut，否则冻结时间轴保留旧 home 时长）再重渲染才能吃到修复。

真实样片到位前，Film progress 与 PROGRESS 必须继续保留此欠账；不要因“首页已能点”关闭。

## Prohibited Behaviors

- 禁把占位片写成真实能力证据或用于制作链验收。
- 禁为换片新增后端接口、组件副本、模板编辑器或第二预填入口。
- 禁静默覆盖用户草稿、自动发送、自动建 run、无真片上架空壳。
- 禁覆盖共享 demo key、拉伸画幅、绕开声音互斥或让离屏视频继续无界解码。
