# LANDING — 落地页叙事与当前结构

> Status: 活跃工作文档（2026-11-26）——落地页叙事、媒体与公开入口的唯一事实源；排期只引用 `PROGRESS.md`。

## 1. 当前结构

首页为长页：`LandingHeader → LandingHero → CreationShowcase → CreationStory → LandingSkills → LandingFaq → EarlyAccess → Footer`。Hero 使用 `#f9f8f6` 暖纸色背景（只覆盖 Landing 的 `--landing-background`，不改全站背景）、眉标、主标题与主按钮，移除 ASCII 波场与光晕；缩短高度以在首屏露出演示。Header 吸附顶部，桌面为 64px 高、独立 1360px 容器，品牌图标 24px，中央导航使用等宽左右轨道保持真正居中，Header CTA 为 14px；主题与语言入口只留在 Header。当CreationStory 顶部到达 80px sticky 起点、故事舞台真正接管页面后，桌面 Header 在原 64px 占位内以 500ms 收缩为带 8px 顶部间距的 56px 居中全圆角玻璃浮条；浅色玻璃为 `#F2F1EE` 93% + 4px blur，深色为 `#171612` 93% + 4px blur，背景与模糊共用同一 pill 边界并隐藏主题/语言按钮，滚回上方恢复通栏实色，移动端保持原形态。App 沿用既有登录及 `/home` 链路。

旧的 VideoShowcase、Manifesto、AppShowcase、Channels、订阅 Pricing、FAQ、FinalCta、Testimonials、旧文本 Gallery 与社群 mock 已移除，不保留一套等待恢复的旧营销叙事。

## 2. 叙事立场

- Rookie 是通过对话操作同一部作品的 AI 视频剪辑师。用户提供素材和目标，看片后指出要改的画面，继续打磨到交付。Skill、制作方法与渲染是内部能力，不要求用户理解或安装。
- 品牌统一写作 **Rookie**。中英文官网文案禁用带有菜鸟感、新手自嘲或贬低读者的措辞。
- 官网文案直接描述创作动作和结果。禁用「你说我来剪」「你定方向我……」等仆从句式、「把某某剪成某某」的广告句式和用否定罗列卖点的防守型减法句式。营销层使用用户熟悉的语言，禁堆叠底层参数、引擎名或实现术语。
- 单助手叙事：用户提出目标，通过对话完成创作与修订；内部工具与子 agent 不承担品牌主语。
- 当前视频产品表达统一为**产品宣传、口播动效、文字动画、知识讲解**。多形态是能力，不是一次输入固定生成全套的承诺。
- 不虚构发布、合规、渠道、社交链接、折扣或质量承诺。多语言文案只陈述当前真实规则。

## 3. Hero、导航与内测商业面

- Landing 品牌、版权与 SEO/分享 meta 使用 **Rookie**。Hero 小字为 `Your next-generation AI video editor / 你的下一代 AI 视频剪辑师`，主标题为 `Explore the art of the cut. / 探索剪辑的艺术`，主按钮为 `Create now / 立即制作`。Header 与收尾按钮使用 `Start a chat / 开始对话`。
- 桌面 Hero 上/下间距为 32/48px；主标题沿用现有响应式 clamp，上限 72px、常规字重，使用自托管的 Cormorant Garamond + Noto Serif SC 高对比衬线字族。首屏无副标题，主标题与主按钮间隔 48px，主按钮文字为 14/16px。`CreationShowcase` 桌面顶部间距为 40px，面板最大宽度仍保持 1200px。
- 桌面 Header 中央为「Features / 功能」和 FAQ。功能按钮在悬停或键盘聚焦时展开黑白灰磨砂双列面板，展示对话式精剪、高质量影棚预设、模板一键同款、多素材与官网直采四项能力。移出、失焦或按 Escape 收起，停留在当前页。
- 移动导航用可折叠列表展示同一组双语内容，保留内测入口、FAQ、主题、语言与主按钮。计费说明位于 FAQ。
- 不恢复订阅套餐卡。Footer 只链接当前存在的锚点与已配置真实目的地。

### 首屏动态演示与滚动叙事

`CreationShowcase` 使用四个场景 Tab、左对话/右样片的展示界面和各自的通栏彩色背景。四个 Tab 共用 `#f8f7f5` 暖白基底与左下、右上、底部三层浅色径向光场，分别以粉蓝淡黄、薰衣草青浅杏、薄荷蓝粉、粉紫浅绿区分；外部背景还包含斜向柔光与静态 SVG 颗粒噪点，噪点沿左上至右下斜向渐显，内部对话面板、输入框和选中 Tab 使用 `bg-card`（浅色主题为纯白）与暖色页面底拉开层级，预览区保持实色媒体表面；噪点不动画，reduced-motion 不增加额外动态。桌面展示区为 160svh，面板 sticky，Tab 在该区域经过视口期间固定于视口底部，离开区域随区块退出。8 秒自动切换；四个类别分别演示与样片有关的编辑动作，执行中使用进行时与省略号，完成后切换为完成时动词短语、去除省略号并将文字与图标降为 `text-meta-foreground`；当前工序状态行使用 `shimmer`，完成回复按类别给出交付摘要和可操作的修订示例。回复与视频在约 4 秒的交付节拍同步淡入，视频此时才开始静音播放；手动选择重置计时并继续轮播。后台、离屏与 reduced-motion 不自动播放，Tab 支持方向键/Home/End。左侧使用用户气泡、活动图标、Agent 回复和多行发送框；发送框入口进入真实应用，不在 Landing 调用制作接口。手机收起活动与辅助回复。移除独立播放按钮、创作按钮与 Tab 进度条。首屏四条样片以 Pexels 公开素材剪辑，媒体和封面位于 `apps/web/public/gallery/showcase/`。预览区标注素材剪辑示例。

- 产品宣传以滴管使用特写配产品片名。 [Los Muertos Crew](https://www.pexels.com/video/person-using-a-dropper-for-a-serum-7615790/)
- 口播动效用竖屏录音室镜头配栏目标签和入场标题。 [cottonbro studio](https://www.pexels.com/video/a-woman-talking-over-the-microphone-7599377/)
- 文字动画以霓虹灯镜头作为文字入场的背景。 [Maksim Goncharenok](https://www.pexels.com/video/a-neon-sign-turning-on-and-off-5820390/)
- 知识讲解将满月延时与月相解释并排。 [Dr Photographer](https://www.pexels.com/video/full-moon-across-night-sky-timelapse-30785080/) · [NASA 月相说明](https://science.nasa.gov/moon/moon-phases/)

`CreationStory` 在同一个吸附对话舞台展示提出剪辑目标、观看第一版和提出局部修改。桌面滚动区为 280svh，移动端为 240svh。首条消息带图片和 PDF 示例附件，示例对话用 AgentVeil 的公开样片展示高风险操作的审批界面。看片后用户希望在审批按钮处多停两秒，助手说明要在当前剪辑中延长该镜头。页面只播放第一版示例。消息区域跟随最新消息，页面滚动仍由浏览器处理，回滚可重新查看前面的步骤。离屏和切到后台时暂停视频，减少动态效果模式直接展示完整对话和样片封面。

### 技能滚动展示

`LandingSkills` 位于 FAQ 前。四组装饰图片来自 [Pexels](https://www.pexels.com/license/)，裁成 3:4 WebP 后存放在 `apps/web/public/gallery/skills/`。下列顺序对应文件后缀 `-1` 至 `-4`。

- 宣传视频：[滴管瓶](https://www.pexels.com/photo/brown-bottle-with-dropper-7796985/)、[镜面精华瓶](https://www.pexels.com/photo/brown-serum-bottle-on-a-round-mirror-7796455/)、[沙面香水瓶](https://www.pexels.com/photo/close-up-shot-of-a-green-perfume-bottle-on-the-sand-8361516/)、[棕色泵瓶](https://www.pexels.com/photo/brown-glass-pump-bottle-on-a-surface-7795404/)。
- 口播动效：[主播特写](https://www.pexels.com/photo/a-woman-talking-on-a-microphone-7598560/)、[双人访谈](https://www.pexels.com/photo/women-having-conversation-inside-the-studio-while-looking-at-each-other-7600887/)、[录音侧面](https://www.pexels.com/photo/a-woman-in-a-studio-7598559/)、[录音棚肖像](https://www.pexels.com/photo/a-woman-in-white-long-sleeves-with-her-hand-on-her-face-7600886/)。
- 文字动画：[竖排字标](https://www.pexels.com/photo/style-neon-signage-2442430/)、[手写霓虹](https://www.pexels.com/photo/good-vibes-only-neon-lights-11256676/)、[室内霓虹](https://www.pexels.com/photo/neon-light-signage-on-a-wall-5182375/)、[粉色霓虹](https://www.pexels.com/photo/pink-neon-on-a-wall-18262649/)。
- 知识讲解：[星空下的天文台](https://www.pexels.com/photo/stars-in-night-sky-over-observatory-buildings-26987730/)、[月相特写](https://www.pexels.com/photo/close-up-shot-of-a-crescent-moon-8810608/)、[望远镜与银河](https://www.pexels.com/photo/telescope-pointing-at-milky-way-galaxy-at-night-2646380/)、[夜间天文台](https://www.pexels.com/photo/observatory-during-nighttime-2928587/)。

## 4. Final CTA（保留 Early access 锚点）

收尾标题为 `What are you working on? / 你手上有什么想剪的？`，邀请用户带来素材、想法或已有剪辑。按钮沿用登录与 `/home` 路径，下方保留注册无需绑卡的说明。开户赠额由运行时 `configs.wallet.signup_grant` 决定，Landing 不展示固定数值。

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

Footer 按参考采用左品牌、右公司/社交媒体两列、底部左版权的布局。品牌下方使用 `AI Video Editing Agent / AI 视频剪辑 Agent`。Company 只保留 Changelog、Terms of Service、Privacy Policy；Social media 只保留 X、Discord、TikTok；Resources 整栏与 Docs、News、YouTube、LinkedIn、Instagram 入口均不渲染。移除主题/语言控件、大字 wordmark、图标排和分隔线。当前未有真实目的地的栏目只渲染不可点击文字，不用空 href、平台首页或弹窗冒充链接；发布前须接入真实目的地或移除这些文字。桌面品牌与导航各占一半，手机品牌在上、导航两列。

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

2026-11-23 核对线上旧版首屏与 Story 后，在本地生产构建以 Chrome 实测英文浅色桌面（1440×900）、中文深色手机（390×844），以及减少动态效果的英文手机（375×812）与中文桌面（1280×800）。覆盖首屏和分享标题、Showcase 键盘切换、媒体播放及离屏暂停、Story 样片和续改、Skills 选择、FAQ 展开。上述视口未见页面横向溢出或 hydration 报错。登录弹窗与模拟登录态进入 `/home` 已实测。TypeScript、构建和两份 Landing 定向测试（5 项）通过。真实邮箱登录、后台制作、修改后成片与公开授权另行验收。

FAQ 桌面保留约 60svh 的滚动停留距离，舞台 sticky 于导航下方，不拦截滚轮。FAQ 使用同名 `details` 互斥分组，展开一项会关闭其余项；展开后若内容超出可用视口，自动恢复自然文档流，保证答案可读；收起后恢复停留。手机与 reduced-motion 不固定。
