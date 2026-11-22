# Repurposer · affectUI Design System Migration
## 统一设计系统、基础组件破坏性替换与旧 UI 彻底退役

**状态：U0–U4 和 U4R 技术迁移已完成。** 分批浏览器、费用、恢复与未验收项见 [迁移验收](affectui-evidence/README.md) 与 [U4R](agent-editor-evidence/iteration-6/final-closure.md)。当前组件选型和交互沿用下列规则。I8 的编辑行为与施工归 [阶段合同](i8.md)。

---

# 0. 总裁决

## 0.1 为什么要进行这次迁移

Repurposer 的产品方向已经明确：

> 通过自然语言自主操作持久视频工程的专业 AI 剪辑师。

产品不再以传统时间线工作台、Graph、Canvas 或 Run 作为用户主要创作界面。

主要体验围绕：

- Home；
- Projects；
- Agent Thread；
- 真实 Tool Activity；
- 当前 Composition；
- 媒体预览；
- 授权与确认；
- 正式 Output；
- 设置和账户。

过去的 UI 经历多轮局部迭代，产生了大量不同来源的样式、组件、token 和页面组织方式。

虽然每一个局部组件可能可以使用，但整体存在：

- 基础控件视觉不统一；
- 同类组件重复实现；
- 页面层级和间距不一致；
- 弹层和菜单样式分散；
- 不同页面使用不同交互结构；
- Arc token 和通用语义 token 并存；
- 旧 Canvas/Run 时代的视觉规则残留；
- 大量自定义 CSS 维护成本；
- 新页面需要反复选择使用哪一套控件。

**本次迁移的目标不是让旧 UI 更整洁，而是终结旧通用 UI 体系。**

affectUI Clean 将成为新的唯一通用视觉标准。

## 0.2 最终结果

期望形成：

```text
affectUI Clean
    ↓
统一主题与通用视觉 token
    ↓
统一基础组件
    ↓
Home / Projects / Settings / Login
    ↓
Studio / Agent Thread / Tool Activity
    ↓
媒体与作品界面
```

用户在整个产品里看到一致的：

- 字体；
- 字号层级；
- 间距；
- 圆角；
- 边框；
- 表面颜色；
- 阴影；
- 动画；
- 按钮；
- 输入；
- 弹窗；
- 菜单；
- 卡片；
- 反馈状态。

不保留一套长期并存的 Arc 通用视觉系统。

---

# 1. 不可妥协的原则

## 原则 A：affectUI 决定通用视觉

采用 affectUI 的 **Clean** 风格。

不要把新组件的完整视觉变量永久映射到旧 Arc token。

不允许出现：

```css
--aui-surface: var(--arc-surface);
--aui-ink: var(--arc-foreground);
--aui-border: var(--arc-border);
```

作为最终设计系统。

最终应以实际安装的 affectUI Clean 源码和主题约定为准。

具体变量名、组件导出、依赖和 Props 必须通过实际 Registry 源码核对，不能凭本合同中的示意名称猜测。

## 原则 B：基础组件全面替换

Button、Input、Dialog、Popover、Select、Dropdown 等通用组件，最终统一使用 affectUI 体系。

允许为了对接产品业务做轻量适配。

不允许重新创建一套带独立视觉规范的 Repurposer Button / Dialog / Input 设计系统。

## 原则 C：迁移完成就删除旧实现

当一个旧组件的真实消费者全部迁移后：

- 删除旧组件；
- 删除旧样式；
- 删除旧测试；
- 删除失效 Story / Demo；
- 删除不再使用的依赖；
- 删除重复 token；
- 删除无效注释和文档。

不要以“未来可能用到”为理由保留旧组件。

## 原则 D：保留真正的产品能力

以下不是通用视觉组件，不要求用 affectUI 重新实现：

- 视频解码和播放；
- Remotion 预览；
- 时间窗预览；
- 音频波形；
- 视频选区；
- 字幕与时间定位；
- 媒体上传；
- SourceSnapshot 引用；
- Output 下载；
- 签名地址续期；
- 真实 Chat SSE；
- Stop；
- 授权与费用；
- 历史消息恢复。

可以替换这些功能的外层控件和视觉呈现。

**不能为了统一外观删除已经验证的业务逻辑。**

## 原则 E：不新增第二套 UI 业务状态

affectUI 组件是呈现层。

用户数据和业务状态仍由现有 API、React 状态、Chat 消息及真实执行结果提供。

不得把 affectUI Demo 中的：

- 模拟聊天；
- 模拟任务；
- 本地假执行；
- 示例上传；
- 自动成功状态；

接入生产业务。

## 原则 F：允许破坏性修改，不允许无证据回退

旧外观不需要兼容。

但真实交互行为必须得到保留或明确的产品裁决。

不允许通过修改测试断言掩盖：

- 按钮不能点击；
- 焦点丢失；
- 弹窗不能关闭；
- 手机端无法提交；
- 输入值丢失；
- 上传中断；
- 权限确认重复；
- 播放器失效。

---

# 3. 最终基础组件目录

以下是目标类别，不是未经核对即可执行的安装 slug。

| 类别 | 目标组件 |
|---|---|
| 操作 | Button、Icon Button |
| 输入 | Text Field、Text Area |
| 选择 | Checkbox、Radio、Switch、Select |
| 表面 | Card、Badge、Separator |
| 弹层 | Dialog、Alert Dialog、Popover |
| 菜单 | Dropdown Menu、Context Menu |
| 提示 | Tooltip、Toaster |
| 反馈 | Spinner、Skeleton、Progress、Empty State |
| 布局 | App Shell、Sidebar、Navigation |
| AI 展示 | Thinking Loader、Tool Call Card、Tool Call Group |
| 授权 | Approval Card、Permission Request |

对于当前 Registry 不提供、未授权或与产品不适用的组件，必须说明实际情况。

可以保留必要的最小业务组件，不允许虚构组件或重新搭建大型基础组件库。

## 3.1 Button

核对现有消费者的：

- variant；
- size；
- loading；
- disabled；
- icon；
- icon-only；
- form submit；
- destructive；
- keyboard focus；
- pointer interaction。

新 Button 应成为唯一标准。

若旧 API 与新 API 不一致，优先按页面迁移调用方。

不为了保留旧 `variant` 和 `size` 协议而永久增加兼容 Adapter。

## 3.2 Input / Textarea / Select

必须保留：

- 受控 value；
- onChange；
- disabled；
- validation；
- label；
- error；
- focus；
- keyboard；
- mobile input behavior。

不允许仅更换边框和颜色，却留下旧控件作为视觉标准。

## 3.3 Dialog / Popover / Dropdown

真实验收：

- 打开；
- 关闭；
- Escape；
- backdrop；
- focus trap；
- focus return；
- keyboard navigation；
- mobile sheet；
- z-index；
- nested overlays。

尤其要防止替换 Dialog 后破坏现有媒体 Lightbox 和费用确认。

## 3.4 Loading / Feedback

所有加载状态使用 affectUI 的统一视觉。

但加载动画不得自己决定业务状态。

Spinner 不代表 Job 正在执行。

Success 状态必须有真实执行回执。

不能通过固定计时器假装生成完成。

---

# 4. Token 与 CSS 的最终归属

## 4.1 affectUI Clean 是唯一通用主题

字体、颜色、圆角、间距、边框、阴影、动画和基础状态由 affectUI Clean 决定。

实际变量名以安装源码为准。

Tailwind 继续作为现有样式技术基础，不要求重建 CSS 工具链。

`styles.css` 允许拆分和删除。

`studio.css` 可以随着实际组件迁移而收缩。

不再新增 Arc 视觉 token。

## 4.2 旧 Arc 的处理

对每一个 `--arc-*`：

1. 查找定义；
2. 查找消费者；
3. 确定是否属于通用视觉；
4. 是否已经有 affectUI 对应语义；
5. 迁移对应消费者；
6. 删除旧 token；
7. 验证浅色和深色。

最终目标：

**不再由 Arc 决定通用 UI 的字体、表面、按钮、阴影和间距。**

不得为了追求零字符串而删除仍有真实消费者的媒体领域 token。

## 4.3 保留媒体领域语义

例如：

- video-canvas；
- timeline；
- waveform；
- caption-overlay；
- selection-mask；
- playback-controls；
- media-lightbox。

这些可以保留独立领域 token。

但它们的通用文字、按钮、菜单、弹窗和外层表面应尽可能跟随 affectUI。

## 4.4 禁止永久双主题

迁移期间可以有短暂的 Arc 与 affectUI 并存窗口。

但每个切片完成后必须减少旧消费者数量。

不得无限增加：

```text
Arc Token
→ Semantic Token
→ affectUI Token
→ Repurposer Override
```

这样的多层映射。

最终应由一套明确的通用主题控制整个应用。

---

# 7. 旧代码与旧 CSS 的删除裁决

本次必须提供实际删除，而不仅是新增 affectUI 文件。

## 7.1 旧组件

对 `components/ui` 每个旧组件标记：

- 已迁移，可删除；
- 仍有实际消费者；
- 被 affectUI 源码依赖；
- 属于 Repurposer 媒体领域能力。

失去消费者后直接删除。

不要求保留旧导出名和旧 Props 的永久兼容文件。

## 7.2 Base UI

目标是退出旧 Repurposer 自建的 Base UI 组件体系。

但不要机械地以零 `@base-ui/react` 安装包为唯一完成标准。

如果实际 affectUI 源码使用 Base UI 作为底层可访问性交互依赖，它可以继续存在。

判断标准是：

**谁决定通用组件 API、视觉和交互组织？**

最终应是 affectUI，而不是旧 base-mira 封装。

`@base-ui-components/react` 等旧依赖在没有真实消费者后必须删除。

## 7.3 Arc CSS

所有通用 Arc token 最终应删除。

删除前逐项核对消费者。

不要把旧 Arc 外观重新复制成一组 `--aui-*` 变量。

允许保留真正的媒体领域 token，命名应清楚并有实际消费者。

## 7.4 旧全局样式

清理：

- 重复 overlay 工具类；
- 失效页面专用样式；
- 旧 Canvas 样式；
- 已删除组件的 CSS；
- 重复深色主题；
- 不再使用的字体导入；
- 无消费者的动画。

不为了减少 CSS 文件数量，把所有组件样式集中复制到新的巨大 `styles.css`。

组件自己的视觉规则应跟随相应源码。

## 7.5 依赖

每次删除一组旧组件后，核对依赖图。

没有真实消费者的依赖从 package manifest 与 lockfile 中移除。

不能只删除 TSX，却留下永久无用的包和 CSS。

---

# 8. 视觉与交互验收

必须在真实浏览器验证，不接受只有静态截图。

至少覆盖：

| 维度 | 验收 |
|---|---|
| 桌面 | 1360×900 或类似宽度 |
| 平板 | 约 768px |
| 手机 | 390×844 和至少一个较窄宽度 |
| 主题 | Light / Dark / Follow System |
| 输入 | 鼠标、键盘、触摸 |
| 弹窗 | 打开、关闭、Escape、焦点恢复 |
| 导航 | 路由、返回、刷新、深链 |
| 表单 | 输入、提交、错误、禁用 |
| 加载 | 实际状态，不使用虚假进度 |
| 动画 | reduced-motion |
| 文案 | 中文与英文基本布局 |
| 历史 | 用户项目和 Output 不丢失 |

视觉核对重点：

- 字体是否统一；
- 信息层级是否清楚；
- 组件高度是否一致；
- 间距是否系统化；
- 表面与弹层是否统一；
- 圆角是否统一；
- 手机端是否可操作；
- 深色模式是否出现错误对比度；
- 是否有新旧视觉混用。

对于关键页面，保留改造前后截图。

但“截图变漂亮”不能代替交互测试。

---

# 9. 技术验证

每批至少执行与修改范围匹配的：

```bash
pnpm test
pnpm exec tsc --noEmit
pnpm build
```

按当前 workspace 实际命令执行。

若路由变化，重新生成并验证路由类型。

对于新增或迁移的 Dialog、Select、Menu，补充实际键盘及焦点验证。

对于共享基础组件，检查所有真实调用方。

不得通过删除失败测试或降低断言使构建通过。

如果无法运行浏览器，必须明确写“未运行”，不能冒充已通过。

---

# 11. 施工 Agent 的报告格式

每个 U 批次完成后必须报告：

## A. Git 与现场

- HEAD；
- origin/main；
- 工作树；
- 本轮提交；
- 实际修改文件；
- 实际删除文件；
- 用户原有修改是否保持。

## B. affectUI 接入

- 实际获取的组件；
- Clean 样式；
- 来源；
- Props；
- 依赖；
- 与原组件的差异。

## C. 迁移范围

- 完成的基础组件；
- 完成的页面；
- 未完成的页面；
- 当前旧组件消费者数量。

## D. 旧体系删除

- 删除的 Base UI 封装；
- 删除的 CSS；
- 删除的 Arc token；
- 删除的依赖；
- 仍存在的真实消费者；
- 为什么尚未删除。

## E. 产品交互

- 登录；
- 导航；
- 表单；
- 设置；
- 项目；
- Chat；
- 媒体；
- 权限与费用。

只报告本批涉及的部分。

## F. 视觉验收

- 桌面；
- 手机；
- 浅色；
- 深色；
- 中英文；
- 截图或实际浏览器证据。

## G. 回归与剩余

- 测试；
- 类型检查；
- 构建；
- 真正失败；
- 未运行；
- 下一批入口。

不允许只写“已全面升级”。

---

# 12. 禁止过度设计

本次不得新增：

- 第二套 Design System；
- 第二套 Token Engine；
- 通用组件编译器；
- 大型旧组件兼容 Adapter；
- 自制 Theme Framework；
- 新状态管理系统；
- 新 Chat Runtime；
- 新 Workflow UI；
- Canvas；
- 模拟执行系统；
- 无真实消费者的通用 UI 平台。

affectUI 已有成熟组件就直接采用并适配实际业务。

不要为了未来未知需求提前封装复杂抽象。

如果某个产品特有交互没有 affectUI 对应组件，保留实际业务能力并统一外观即可。

**不破不立，核心是删除真正不再需要的东西，而不是用另一套自定义架构替换旧自定义架构。**

---

# 13. 遇到复杂问题的停止条件

以下情况应暂停相关改动并请求裁决：

1. affectUI 实际源码与预期功能明显不一致；
2. Registry 授权或许可证不允许当前使用；
3. 替换基础组件会破坏重要键盘或无障碍行为；
4. 某个旧组件仍承担无法安全迁移的业务功能；
5. 需要修改其他施工者尚未提交的内容；
6. 删除 CSS 将破坏尚未迁移的核心页面；
7. 必须引入大型兼容层才能继续；
8. 现有用户设置或主题持久化将丢失；
9. 新 UI 无法正确呈现授权、Stop 或执行结果；
10. 无法证明媒体播放器或下载仍然可靠。

提问时必须说明：

- 实际代码；
- 失败场景；
- 选项；
- 推荐方案；
- 风险；
- 被阻塞的具体范围。

普通 TypeScript 错误、样式适配和组件 Props 问题应自主解决，不反复请示。

---

# 14. 完成定义

整个 affectUI Migration 完成时必须达到：

1. affectUI Clean 成为唯一通用视觉体系；
2. Home、Projects、Studio、Settings、Login 统一；
3. Button、Input、Dialog、Menu、Select 等基础组件完成替换；
4. Chat Activity、Approval、Tool Group 使用统一视觉；
5. Composer 的业务能力没有丢失；
6. 媒体播放器、波形、预览和 Output 继续可靠；
7. Light、Dark、System 主题正确；
8. 移动端与桌面端都可操作；
9. 旧 Base UI 自定义封装已无现役消费者并删除；
10. 无消费者的 Arc 通用 token 和 CSS 已删除；
11. 无用依赖已删除；
12. 不再维护两套通用组件 API；
13. 没有新增第二套业务状态；
14. 没有因视觉迁移引入 Agent 执行回退；
15. 真实用户旅程、测试、构建和浏览器验收通过。

如果 affectUI 实际依赖 Base UI 作为无头交互实现，可以保留该依赖；但 Repurposer 自建的旧 base-mira 通用组件不再是设计标准。

**最终目标不是仓库里再也没有 Base UI 字符串，而是 Repurposer 不再维护旧的通用视觉系统。**

---

# 附加合同：affectUI 官方组件发现、选型与源码复用

## 1. 施工前必须主动检索 affectUI

本次迁移不是将旧 Button、Input、Dialog 机械替换为同名新组件。

**每次改造一类产品界面，必须先使用已配置的 affectUI MCP、Skills 和 Registry 检索适合该用户场景的现有组件、Block 或 Screen。**

不能仅依据已有组件清单，不能根据组件英文名称猜测用途，也不能因为自己熟悉 React 就优先写自定义 UI。

组件检索要从用户行为出发，例如：

- 用户如何阅读 AI 的工作过程？
- 如何展示一次模型响应的多个 Tool Calls？
- 如何展示后台任务排队、执行、失败、取消和结果未知？
- 如何向用户请求费用授权？
- 如何让用户查看文件、视频、音频和历史 Output？
- 如何在 Chat 中进行附件上传、mentions 和发送？
- 如何在手机上展示长任务进度？

优先寻找官方已经针对这些问题设计的 UI。

## 2. 必须实际使用 MCP 和 Skills

开工时先核对 Codex 当前连接的 affectUI MCP 和相关 Skills。

确认：

1. MCP 是否正常连接。
2. Registry 是否可用。
3. Clean 组件是否可以读取源码。
4. 当前授权是否允许使用对应组件。
5. 是否有相关组件的安装、使用或组合指南。
6. 是否存在对应的 Block 或完整 Screen。
7. 组件实际 Props、导出、样式和依赖是什么。

若 MCP 查询成功，必须以真实返回的源码作为依据。

**不能仅阅读组件网页标题就宣称已完成技术选型。**

如果 MCP 或 Skill 不可用，先进行有界排查。确实无法恢复时，说明限制，使用已安装的真实组件或 Registry 源码继续可安全完成的部分，不得虚构查询结果。

## 3. 组件选型顺序

对于每一个 UI 场景，按照以下顺序决定实现方式：

**第一优先：affectUI Clean 已有完整组件。**

如果现有组件能够直接承担交互，使用该组件。

**第二优先：affectUI 已有 Block / Screen。**

如果官方已有适合的完整布局，参考其源码与交互组织，将所需内容接入真实业务。

不要原样复制示例数据、假消息或模拟执行逻辑。

**第三优先：组合多个 affectUI Clean 组件。**

例如 Tool Group、Badge、Card、Approval 等组合。

保持官方的尺寸、状态和视觉约定。

**第四优先：最小产品特有组件。**

仅当 affectUI 不提供相应能力，或者已有组件无法承担 Repurposer 的专业业务需求时，才保留或编写特有 UI。

典型需要自行维护的能力包括：

- Remotion 视频预览；
- 真实音频波形；
- 视频时间选择；
- CompositionVersion 定位；
- 媒体 SourceSnapshot 引用；
- 真实 Output 播放和签名续期。

这些属于产品能力，不是重复造通用 UI。

## 4. U3 的重点检索范围

开始 U3 时，必须检索并检查可能适合的：

| 场景 | affectUI 候选 |
|---|---|
| AI 执行过程 | Thinking Loader / Thinking State |
| 单次工具调用 | Tool Call Card |
| 多个工具调用 | Tool Call Group |
| 用户费用同意 | Approval Card |
| 权限请求 | Permission Request |
| AI 消息正文 | AI Answer |
| 消息操作 | Message Actions |
| Chat 组织方式 | Agent Thread |
| 用户输入 | Chat Composer |

以上是查询关键词，不保证每个名称都是当前 Registry 的实际 slug。

必须通过 MCP/Registry 验证。

**尤其要实际检查 Agent Thread Screen 的完整结构，而不只是安装 Tool Call Card。**

评估它如何处理：

- assistant / user 消息；
- thinking；
- tool groups；
- approvals；
- attachments；
- artifacts；
- streaming；
- Stop；
- 失败状态；
- 移动端布局。

然后决定哪些官方结构可以直接采用，哪些必须连接 Repurposer 真实数据。

## 5. U4 的重点检索范围

Composer、媒体卡和 Lightbox 迁移时，必须检索：

- Chat Composer；
- Icon Button；
- File Attachment；
- Upload；
- Dialog；
- Popover；
- Dropdown Menu；
- Tooltip；
- Media / File Card；
- Audio 相关控件；
- 视频容器及操作栏；
- Empty State；
- Progress / Spinner / Skeleton。

如果 Registry 中没有直接对应的专业媒体组件，应说明查询结果，并保留产品自有的媒体能力。

不要因为没有找到官方视频编辑组件，就引入另外一套不相关的大型 UI 库。

## 6. 每次选型必须给出理由

每个主要 UI 场景都应记录：

| 项目 | 必填内容 |
|---|---|
| 产品场景 | 用户实际要完成什么 |
| 官方候选 | 查询到哪些组件或 Screen |
| 源码验证 | 是否实际读取源码 |
| 最终选择 | 采用哪一个 |
| 拒绝其他方案 | 具体不适合的原因 |
| 接入边界 | 哪些数据和交互由 Repurposer 提供 |
| 旧实现 | 将替换什么 |
| 删除结果 | 已删除哪些无消费者代码 |
| 验收 | 真实交互是否通过 |

不要求每个简单 Button 都写长篇报告。

但 Tool Group、Approval、Composer、Agent Thread、媒体查看器等核心区域必须有可复查的选型依据。

## 7. 不要复制 affectUI 的示例业务逻辑

通过 MCP 获取的组件源码可能包含：

- Mock messages；
- Demo tools；
- 示例项目；
- 模拟审批；
- 本地定时状态推进；
- 模拟文件上传；
- 默认成功结果。

这些只能作为展示示例。

生产版本必须使用 Repurposer 的：

- 真实 Chat 消息；
- Tool Call；
- MediaJob；
- ExportJob；
- 费用授权；
- Stop；
- CompositionVersion；
- SourceSnapshot；
- Output。

不得让视觉组件维护第二份执行状态。

## 8. 不要再建立通用 UI 兼容层

采用官方组件时，优先迁移真实调用方到对应 API。

不要永久保留：

```text
OldRepurposerComponent
    ↓
CompatibilityAdapter
    ↓
affectUIComponent
```

如果需要业务层适配，应只处理确实独特的业务数据，例如 Tool Receipt 转成展示 Props。

不能为了复用而重新创建一整套设计系统。

也不引入 Zustand、Redux、Jotai 或新的全局 Chat 状态。

## 9. 每批交付必须报告官方组件使用情况

报告中新增：

- 实际调用了哪些 MCP / Skills 能力；
- 查询了哪些 UI 场景；
- 候选组件；
- 实际采用组件；
- 组件的真实 Registry slug；
- 为什么适合；
- 哪些 UI 是产品特有、无法直接采用；
- 删除了哪些旧自定义实现；
- 是否出现重复造轮子。

**affectUI 是通用 UI 的事实来源，Repurposer 自己维护独特的 AI 剪辑能力。**

本合同为 U3/U4 及后续 UI 开发的强制要求。