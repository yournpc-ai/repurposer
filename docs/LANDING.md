# LANDING — 落地页叙事与当前结构

> Status: 活跃工作文档（2026-11-06）——落地页叙事、媒体与公开入口的唯一事实源；排期只引用 `PROGRESS.md`。

## 1. 当前结构

首页为长页：`LandingHeader → LandingHero → CreationShowcase → CreationStory → LandingFaq → EarlyAccess → Footer`。Hero 使用 `#f9f8f6` 暖纸色背景（只覆盖 Landing 的 `--landing-background`，不改全站背景）、定位小字/原主标题/说明三层文字和主按钮，移除 ASCII 波场与光晕；缩短高度以在首屏露出演示。Header 吸附顶部，桌面为 64px 高、独立 1360px 容器，品牌图标 24px，中央导航使用等宽左右轨道保持真正居中，Header CTA 为 14px；主题与语言入口只留在 Header。当「说说你想做的视频」section 顶部到达 80px sticky 起点、故事舞台真正接管页面后，桌面 Header 在原 64px 占位内以 500ms 收缩为带 8px 顶部间距的 56px 居中全圆角玻璃浮条；浅色玻璃为 `#F2F1EE` 93% + 4px blur，深色为 `#171612` 93% + 4px blur，背景与模糊共用同一 pill 边界并隐藏主题/语言按钮，滚回上方恢复通栏实色，移动端保持原形态。App 沿用既有登录及 `/home` 链路。

旧的 VideoShowcase、Manifesto、AppShowcase、Channels、订阅 Pricing、FAQ、FinalCta、Testimonials、旧文本 Gallery 与社群 mock 已移除，不保留一套等待恢复的旧营销叙事。

## 2. 叙事立场

- 定位为对话式视频 Agent，服务有产品或知识表达需求、不会也不希望学习剪辑的人；无需安装软件或配置环境。Skill、制作方法与渲染是内部能力，不要求用户理解或安装。
- 单助手叙事：用户提出目标，通过对话完成创作与修订；内部工具与子 agent 不承担品牌主语。
- 当前视频产品表达统一为**产品宣传、口播动效、文字动画、知识讲解**。多形态是能力，不是一次输入固定生成全套的承诺。
- 不虚构发布、合规、渠道、社交链接、折扣或质量承诺。多语言文案只陈述当前真实规则。

## 3. Hero、导航与内测商业面

- Landing 品牌、版权与 SEO/分享 meta 使用 **Rookie Cut**；公开域名继续读取当前实际配置，未确定新域名前不改 URL。Hero 小字为 `Your AI video agent / 你的 AI 视频 Agent`，主标题为 `Rookies can make great videos too. / 新手也能做出好视频。`；英文说明为 `No complex timelines or keyframes. Create animated promos and explainer videos—just by chatting.`，中文说明保持现有功能描述；Hero 主按钮为 `Create now / 立即制作`，Header 与移动导航主按钮为 `Get started / 开始体验`，均点击登录或进入应用。
- 桌面 Hero 上/下间距为 32/48px；主标题沿用现有响应式 clamp，上限 72px、常规字重，使用自托管的 Cormorant Garamond + Noto Serif SC 高对比衬线字族。说明限宽 32rem，中英文按语义显式分为两行，不在词语中间断行；与主按钮间隔 48px，主按钮文字为 14/16px。`CreationShowcase` 桌面顶部间距为 40px，面板最大宽度仍保持 1200px。
- 配置真实 Discord 地址后，Hero 显示「加入社群」外链；未配置时不显示第二入口。
- Header 使用「定价 / 常见问题」两个正文锚点，撤掉悬浮的重复功能介绍。移动 Sheet 保留内测入口及相同两个锚点，另保留主题、语言和主按钮。
- `#pricing` 指向 FAQ 的计费问题，锚点访问自动展开对应答案。对话免费与重新制作消耗积分分别说明。
- 不恢复订阅套餐卡。Footer 只链接当前存在的锚点与已配置真实目的地。

### 首屏动态演示与滚动叙事

`CreationShowcase` 使用四个产品 Tab、左对话/右样片的展示界面和各自的通栏彩色背景。四个 Tab 共用 `#f8f7f5` 暖白基底与左下、右上、底部三层浅色径向光场，分别以粉蓝淡黄、薰衣草青浅杏、薄荷蓝粉、粉紫浅绿区分；外部背景还包含斜向柔光与静态 SVG 颗粒噪点，噪点沿左上至右下斜向渐显，内部对话面板、输入框和选中 Tab 使用 `bg-card`（浅色主题为纯白）与暖色页面底拉开层级，预览区保持实色媒体表面；噪点不动画，reduced-motion 不增加额外动态。桌面展示区为 160svh，面板 sticky，Tab 在该区域经过视口期间固定于视口底部，离开区域随区块退出。8 秒自动切换；四个类别分别使用符合自身制作链的工序名称，执行中使用进行时与省略号，完成后切换为完成时动词短语、去除省略号并将文字与图标降为 `text-meta-foreground`；当前工序状态行使用 `shimmer`，完成回复按类别给出交付摘要和可操作的修订示例。回复与视频在约 4 秒的交付节拍同步淡入，视频此时才开始静音播放；手动选择重置计时并继续轮播。后台、离屏与 reduced-motion 不自动播放，Tab 支持方向键/Home/End。左侧使用用户气泡、活动图标、Agent 回复和多行发送框；发送框入口进入真实应用，不在 Landing 调用制作接口。手机收起活动与辅助回复。移除演示说明标签、独立播放按钮、创作按钮与 Tab 进度条。复用公开候选媒体，动画为展示投影，并非真实 Studio / Chat 制作回放。

`CreationStory` 使用 520svh 滚动区与同一个 sticky 对话舞台：输入文字、发送为用户气泡，首轮只呈现 3 条 Agent 回复与 3 条状态行，顺序为开场说明 → 梳理目标 → 设计分镜 → 分镜摘要 → 制作画面与字幕 → 交付样片；随后进入修改要求、建议确认与第二次交付。舞台与发送按钮不做滚动缩放，只保留高度、透明度和文字揭示过渡。首次制作和修订制作的工序均靠左并与正文穿插，执行中使用进行时与省略号，完成后切换为完成时动词短语、去除省略号并降为 `text-meta-foreground`；只渲染已经到达的步骤，当前步的 `shimmer` 结束后正文逐字出现，正文完整后才出现下一行状态，不提前展示未来步骤。分镜摘要与修订说明不虚构素材参数或工作耗时。消息区限定视口高度，随内容展开自动跟随末条消息，但容器不接收独立滚轮滚动、不截获页面滚动。用户气泡按内容宽度排列并保留 85% 的最大宽度，短句不撑满整行。两次交付当前复用同一公开样片以演示交互，不作为修改前后效果证据。标题在原位置变化，不另起三个场景或重挂载舞台；继续滚动提示固定于底部。倒滚可回看，离屏/后台暂停视频；reduced-motion 直接显示完整对话。删除样片和修改要求的说明文字。开场输入卡展示图片缩略图与 PDF 文件 chip，发送后输入卡消费附件、首条用户消息保留同一组附件；这些附件只演示素材输入形态，不响应选择或上传。对话卡与输入框使用 `bg-card`，输入框以 `border-subtle` 在同色卡面上分出边界。该演示仍为展示投影，不调用制作接口，也不展示未经验证的修改后成片。

## 4. Final CTA（保留 Early access 锚点）

FAQ 后使用简洁的单列收尾 CTA，标题为 `Make videos without waiting until everything is ready.` /「做视频，并不用等准备好一切。」。说明无需研究工具或 Skill，描述需求即可创作，并可指出具体时间与画面继续修订；不重复素材列表和 Gallery 产品类型，不使用圆角背景面板、三列图标、横向分隔线或规格表。桌面居中限宽，移动端自然换行且按钮全宽；保留 `early-access` 锚点供既有导航使用。

- 主按钮为 `Create a video / 开始制作视频`，沿用登录与 `/home` 链路。
- 按钮下说明新账号赠送 **1,000 credits**、注册无需绑卡。公开文案与运行时 `configs.wallet.signup_grant` 必须一致；修改代码默认值不会覆盖数据库已有配置。
- 按钮下仅保留赠送积分和注册无需绑卡的一行说明。预估消耗见 FAQ，内测状态见顶部 Banner，不在收尾重复。

## 5. 四产品 Gallery（当前不在首页挂载）

### 布局与滚动

- Gallery 桌面使用 170svh 外层与导航下方的 sticky 舞台，完整呈现四张 Bento 卡片后保留约 70svh 的滚动停留距离，让样片继续播放；不拦截滚轮，不强制计时。沿用共享内容轴与四类卡片，网格适配视口剩余高度。手机与 reduced-motion 保持正常文档流。
- Gallery 标题居中，不附用途引导段落。区块标题为 30/36px，卡片标题为 20/24px、500 字重，说明为 14px。底部 75% 使用 `media-scrim` 渐变，文字区保留高密度遮罩，说明使用 `media-foreground` 的 80% 透明度，防止白底或自带字幕的帧干扰阅读；不逐卡写死黑白。移除卡片上方创作按钮，整卡保留可聚焦创作入口。
- 小屏使用正常文档流的纵向卡片；`prefers-reduced-motion` 下所有尺寸都使用静态网格，不自动播放视频。
- 卡片进入视口后静音循环，离屏暂停。首页不提供开声或全屏查看控件，唯一卡片动作是「用它开始创作」。

### 创作入口

点击每张卡只暂存对应 Skill reference 与 `landing.gallery.items.<id>.prompt`，登录或直达 `/home` 后由 Home 消费一次并预填 composer。预填正文用普通用户要求，不出现「使用这个 Skill」与内部技术参数。不得自动发送、创建 Run 或形成第二意图入口；Home 继续从实时 Skill catalog 解算版本，离线回退沿用现有内置版本表。

### 媒体边界

`components/landing/content.ts` 集中登记卡片媒体、海报与 Skill。当前四条均为**已经公开的视觉候选**，用于第一版布局与滚动审阅；没有复制本地 pending 锚片。它们不关闭各类最终 Gallery 验收：对应类别仍须完成真实目标任务、制作与局部修订、完整音轨、连续观看、实际试听、公开权利和发布授权后，才能逐张替换为最终锚片。口播动效与知识讲解的新分类锚片尤其不得由旧公开 demo 冒充验收通过。

## 6. Footer 与真实公开入口

Footer 按参考采用左品牌、右公司/社交媒体两列、底部左版权的布局。品牌下方使用 Hero 主标题作为一句话说明，不另写第二套品牌文案。Company 只保留 Pricing、Changelog、Terms of Service、Privacy Policy；Social media 只保留 X、Discord、TikTok；Resources 整栏与 Docs、News、YouTube、LinkedIn、Instagram 入口均不渲染。移除主题/语言控件、大字 wordmark、图标排和分隔线。当前未有真实目的地的栏目只渲染不可点击文字，不用空 href、平台首页或弹窗冒充链接；发布前须接入真实目的地或移除这些文字。桌面品牌与导航各占一半，手机品牌在上、导航两列。

公开配置统一位于 `components/landing/content.ts`，经 Vite 环境变量注入；`apps/web/Dockerfile` 与根 `docker-compose.yml` 同步传递这些 build args，避免本地与线上曝光不一致：

| 变量 | 用途 |
|---|---|
| `VITE_DISCORD_URL` | Discord 正式邀请链接，同时开放 Hero 社群按钮 |
| `VITE_YOUTUBE_URL` | YouTube 频道 |
| `VITE_X_URL` | X 账号 |
| `VITE_WECHAT_GROUP_QR_URL` | 微信群二维码图片；Footer 以 Dialog 展示 |
| `VITE_SUPPORT_EMAIL` | 客服邮箱，生成 `mailto:` |
| `VITE_TERMS_URL` / `VITE_PRIVACY_URL` / `VITE_REFUND_POLICY_URL` | 已存在的法务页面 |

未配置的渠道或法务项不渲染，禁止使用平台首页、空锚点或“待接入”弹窗冒充真实入口。公开收款前的支付、税务、退款和法务上线门继续归 `PAYMENTS.md`。

## 7. 当前验证边界

当前公开页实现完整新版结构、中英文文案、自动/手动 Tab、滚动三阶段、静态 Gallery、FAQ 与三列 Footer。既有 TypeScript 与 landingCreate 定向检查通过，但最新 Landing 视觉与演示调整尚未复跑静态检查或浏览器验收。减少动态效果、其他尺寸、完整媒体播放、登录后 handoff、双主题仍需完整旅程验收；公开 1,000 积分文案前仍须核对数据库实际配置。媒体仍为公开视觉候选；真实制作与修改回放、类别锚片与公开授权验收未关闭。Footer 未配置栏目当前仅文字，无真实链接；上线前须逐项处理。

FAQ 与 Final CTA 桌面分别保留约 60svh / 50svh 的滚动停留距离，舞台 sticky 于导航下方，不拦截滚轮。FAQ 使用同名 `details` 互斥分组，展开一项会关闭其余项；展开后若内容超出可用视口，自动恢复自然文档流，保证答案可读；收起后恢复停留。手机与 reduced-motion 不固定。
