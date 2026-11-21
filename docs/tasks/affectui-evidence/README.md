# affectUI Clean 迁移验收

## 范围和现场

开工基线为 `fab4017b`，当时远端为 `a83ee492`。U0 为 `eaed729d`，U1 为 `b0fd324d`。共享工作树在 U2 施工期间纳入独立 6C 提交 `ca29ce54`。本目录只记录 Web 迁移。

## 组件与主题

组件取自授权 affectUI MCP 的 Clean 源码。安装到 `apps/web/src/components/ui/` 的实际 Registry slug 如下。

`avatar-clean`, `badge-clean`, `button-clean`, `card-clean`, `checkbox-clean`, `dialog-clean`, `dropdown-menu-clean`, `empty-state-clean`, `icon-button-clean`, `popover-clean`, `segmented-control-clean`, `select-clean`, `skeleton-clean`, `spinner-clean`, `switch-clean`, `text-area-clean`, `text-field-clean`, `tooltip-clean`.

这些组件依赖 React 19，自带局部 CSS。Button 接受 primary / secondary / ghost / destructive、size、loading 及原生表单属性。IconButton 需要 label 和 icon。TextField 与 TextArea 使用原生输入事件，Checkbox 与 Switch 使用原生 checked/onChange。Select 使用 options/value/onChange。Dialog 与 AlertDialog 使用 open/onOpenChange，后者的异步 onConfirm 拒绝后保留弹层。DropdownMenu 使用 items 和 trigger，Popover 使用 open/onClose。Card 的标题链接提供主点击区域。各组件的导出类型与实现同文件。

通用视觉源是 Clean 源码中的尺寸、样式及 `src/styles.css` 的 `--aui-*` 明暗值。Tailwind 语义色读取这些值。原 ThemeProvider 保存 Light / Dark / System，首屏脚本按系统偏好解析。Studio 使用 App Shell Inset 的主面板、侧栏和断点，自行接入真实路由；Home 接入真实 Skill 与上传状态。注册器配置里的 shadcn style 是 CLI schema 使用的值。项目卡的多态元素适配了当前 TypeScript；原生 Dialog 通知既有 Sonner 把同一个提示区域移入当前弹层。

## 删除与消费者

统计范围为 `apps/web/src` 的 TS、TSX、CSS。每个组件的消费者数为不同文件数，识别别名和相对导入，包含测试 mock。Base UI 直接引用按 import 语句计数。未跟踪的其他施工文件不进入基线。

| 指标 | 开工 | U2 |
|---|---:|---:|
| 旧 button 直接消费者 | 43 | 15 |
| 旧 input 直接消费者 | 13 | 1 |
| 旧 dialog 直接消费者 | 9 | 1 |
| 旧 select 直接消费者 | 5 | 1 |
| 旧 UI 文件 | 34 | 16 |
| 其中直接导入 Base UI 的旧文件 | 24 | 12 |
| 全 Web 直接 Base UI import | 31 | 15 |
| 含这些 import 的 Web 文件 | 25 | 12 |
| 不同 Arc token 定义 | 83 | 0 |

U1 删除 `alert`、`checkbox`、`progress`、`scroll-area`、`switch`，以及 animate-ui 下 progress 的组件、原语和 counting-number 原语。U2 删除以下零消费者旧文件。

`badge.tsx`, `card.tsx`, `dropdown-menu.tsx`, `empty-state.tsx`, `input-group.tsx`, `separator.tsx`, `sheet.tsx`, `sidebar.tsx`, `skeleton.tsx`, `tabs.tsx`, `textarea.tsx`, `toggle-group.tsx`, `toggle.tsx`。

删除 26 条已退出的 sidebar/chart 主题声明（含 Tailwind 映射），3 个旧 CSS utility（media-scrim、scroll-fade-x、ambient-glow），2 个无调用的封面动画（rc-lineGrow、rc-qPulse），以及下线的 post、quote、carousel 封面选择器。保留现有 5 种素材封面实际使用的样式和媒体覆盖层语义色。移除 3 个直接依赖及锁文件记录（@base-ui-components/react、tailwindcss-animate、@fontsource-variable/geist）。

### 仍在使用的基线文件

下表路径相对于 `apps/web/src/`。U3 覆盖消息与 Activity，U4 覆盖共享 Composer、预览与媒体控件。依赖链中的旧原语在最后一个消费者切换后删除。Tour 的定位与交互服务首次引导，Sonner 服务全局反馈，二者已接入本轮 Clean 按钮或主题。

| 旧文件 | 直接消费者 | 处理范围 |
|---|---|---|
| `components/ui/attachment.tsx` | `components/chat/AgentThread.tsx`, `components/chat/rows/UserMessage.tsx` | U3/U4 |
| `components/ui/avatar.tsx` | `components/composer/PersonaPanel.tsx` | U4 |
| `components/ui/bubble.tsx` | `components/chat/rows/UserMessage.tsx` | U3 |
| `components/ui/button.tsx` | `components/chat/AgentThread.tsx`, `components/chat/ChatConversation.tsx`, `components/chat/ChatOutputViewer.tsx`, `components/chat/QuestionDock.tsx`, `components/chat/video/StoryboardCard.tsx`, `components/chat/video/TextSizeScrubInput.tsx`, `components/chat/video/WaveformPlayer.tsx`, `components/chat/video/preview/CompositionPreview.tsx`, `components/composer/ComposerIconButton.tsx`, `components/composer/ComposerSendButton.tsx`, `components/results/MediaLightboxStage.tsx`, `components/results/MediaRegionSelectionOverlay.tsx`, `components/ui/attachment.tsx`, `components/ui/dialog.tsx`, `components/ui/message-scroller.tsx` | U3/U4 |
| `components/ui/dialog.tsx` | `components/results/MediaLightbox.tsx` | U3/U4 |
| `components/ui/input.tsx` | `components/chat/QuestionDock.tsx` | U3 |
| `components/ui/label.tsx` | `components/chat/video/TextSizeScrubInput.tsx` | U4 |
| `components/ui/marker.tsx` | `components/chat/rows/MetaRow.tsx` | U3 |
| `components/ui/message-scroller.tsx` | `components/chat/ActivityStream.mount.test.tsx`, `components/chat/ActivityStream.tsx`, `components/chat/AgentThread.mediaJourney.mount.test.tsx`, `components/chat/ChatConversation.mount.test.tsx`, `components/chat/ChatConversation.tsx`, `components/chat/blocks/RunBlock.tsx` | U3 |
| `components/ui/message.tsx` | `components/chat/AgentThread.tsx`, `components/chat/AnsweredQuestion.tsx`, `components/chat/CandidateSurface.tsx`, `components/chat/ChatConversation.tsx`, `components/chat/blocks/ComponentSlot.tsx`, `components/chat/blocks/RunBlock.tsx`, `components/chat/rows/AssistantText.tsx`, `components/chat/rows/UserMessage.tsx`, `components/chat/video/AudioCandidateSurface.tsx`, `components/chat/video/VideoPresetCandidateSurface.tsx` | U3 |
| `components/ui/popover.tsx` | `components/chat/video/TextSizeScrubInput.tsx`, `components/composer/ComposerPanelButton.tsx`, `components/results/MediaLightboxStage.tsx` | U4 |
| `components/ui/select.tsx` | `components/chat/video/TextSizeScrubInput.tsx` | U4 |
| `components/ui/slider.tsx` | `components/chat/video/TextSizeScrubInput.tsx` | U4 |
| `components/ui/sonner.tsx` | `routes/__root.tsx` | 已迁移，全局反馈服务 |
| `components/ui/tooltip.tsx` | `components/composer/ComposerPanelButton.tsx`, `routes/__root.tsx` | U3/U4（根 Provider 随最后一个调用方移除） |
| `components/ui/tour.tsx` | `components/home/HomeComposer.tsx` | 已迁移按钮，保留 Spotlight 定位 |

直接导入 Base UI 的剩余文件如下。

- `components/ui/attachment.tsx`，2 处。
- `components/ui/avatar.tsx`，1 处。
- `components/ui/bubble.tsx`，2 处。
- `components/ui/button.tsx`，1 处。
- `components/ui/dialog.tsx`，1 处。
- `components/ui/input.tsx`，1 处。
- `components/ui/marker.tsx`，2 处。
- `components/ui/popover.tsx`，1 处。
- `components/ui/select.tsx`，1 处。
- `components/ui/slider.tsx`，1 处。
- `components/ui/tooltip.tsx`，1 处。
- `components/ui/tour.tsx`，1 处。

### Arc 定义与消费位置

以下为开工版本中每个定义及直接 var 引用的源位置。Tailwind 工具类经 styles.css 间接消费这些值。U2 后源码中无 `--arc-*`。

| token | 定义（styles.css 行） | 直接消费（styles.css 行或其他文件） |
|---|---|---|
| `--arc-accent` | 687, 838 | 814 |
| `--arc-accent-foreground` | 690 | 815 |
| `--arc-accent-strong` | 688, 839 | 无直接 var 引用 |
| `--arc-accent-subtle` | 689, 840 | 无直接 var 引用 |
| `--arc-background` | 677, 826 | 690, 757, 812 |
| `--arc-border` | 684, 835 | 786, 789 |
| `--arc-border-strong` | 686, 837 | 788, 790, 819 |
| `--arc-border-subtle` | 685, 836 | 787, 818 |
| `--arc-control-fill` | 698, 847 | 610 |
| `--arc-control-glyph` | 693, 842 | 605, 773 |
| `--arc-control-on` | 692, 841 | 604, 698, 699, 772 |
| `--arc-control-on-subtle` | 699 | 无直接 var 引用 |
| `--arc-control-thumb` | 696, 845 | 608 |
| `--arc-control-thumb-on` | 697, 846 | 609 |
| `--arc-control-thumb-shadow` | 700, 848 | 583 |
| `--arc-control-track` | 694, 843 | 606 |
| `--arc-control-track-hover` | 695, 844 | 607 |
| `--arc-danger` | 707, 855 | 785 |
| `--arc-ease-enter` | 753 | 578, 963, 966 |
| `--arc-focus-ring` | 691 | 无直接 var 引用 |
| `--arc-font-body` | 739 | 563, 890 |
| `--arc-font-display` | 738 | 564, 895 |
| `--arc-foreground` | 681, 832 | 767, 769, 771, 775, 781, 813, 817, 875 |
| `--arc-gradient` | 721 | 无直接 var 引用 |
| `--arc-gradient-foreground` | 722, 864 | 无直接 var 引用 |
| `--arc-gradient-from` | 719, 862 | 721 |
| `--arc-gradient-ink` | 725, 867 | 无直接 var 引用 |
| `--arc-gradient-line` | 724, 866 | 无直接 var 引用 |
| `--arc-gradient-soft` | 723, 865 | 无直接 var 引用 |
| `--arc-gradient-to` | 720, 863 | 721 |
| `--arc-leading-body` | 752 | 577, 892 |
| `--arc-leading-display` | 751 | 576, 897 |
| `--arc-neutral-0` | 664 | 677, 678, 679, 821 |
| `--arc-neutral-1` | 665 | 无直接 var 引用 |
| `--arc-neutral-10` | 674 | 无直接 var 引用 |
| `--arc-neutral-11` | 675 | 681, 761, 764, 765, 820 |
| `--arc-neutral-2` | 666 | 680 |
| `--arc-neutral-3` | 667 | 762 |
| `--arc-neutral-4` | 668 | 无直接 var 引用 |
| `--arc-neutral-5` | 669 | 无直接 var 引用 |
| `--arc-neutral-6` | 670 | 无直接 var 引用 |
| `--arc-neutral-7` | 671 | 683 |
| `--arc-neutral-8` | 672 | 682 |
| `--arc-neutral-9` | 673 | 无直接 var 引用 |
| `--arc-paper-0` | 676 | 758 |
| `--arc-series-1` | 715 | 806 |
| `--arc-series-2` | 716, 860 | 807 |
| `--arc-series-3` | 717, 861 | 808 |
| `--arc-series-4` | 718 | 809 |
| `--arc-shadow-floating` | 712, 858 | 27, 582 |
| `--arc-shadow-raised` | 709, 857 | 581 |
| `--arc-shadow-resting` | 708, 856 | 580 |
| `--arc-space-1` | 726 | 579 |
| `--arc-space-10` | 733 | 无直接 var 引用 |
| `--arc-space-12` | 734 | 无直接 var 引用 |
| `--arc-space-16` | 735 | 无直接 var 引用 |
| `--arc-space-2` | 727 | 无直接 var 引用 |
| `--arc-space-20` | 736 | 无直接 var 引用 |
| `--arc-space-24` | 737 | 无直接 var 引用 |
| `--arc-space-3` | 728 | 无直接 var 引用 |
| `--arc-space-4` | 729 | 无直接 var 引用 |
| `--arc-space-5` | 730 | 无直接 var 引用 |
| `--arc-space-6` | 731 | 无直接 var 引用 |
| `--arc-space-8` | 732 | 无直接 var 引用 |
| `--arc-success` | 704, 852 | 782 |
| `--arc-success-subtle` | 705, 853 | 783 |
| `--arc-surface` | 678, 829 | 768, 793 |
| `--arc-surface-muted` | 680, 831 | 774, 776, 777, 780, 816, 868, 874 |
| `--arc-surface-raised` | 679, 830 | 770 |
| `--arc-text-2xl` | 745 | 570 |
| `--arc-text-3xl` | 746 | 571 |
| `--arc-text-4xl` | 747 | 572 |
| `--arc-text-5xl` | 748 | 573 |
| `--arc-text-base` | 742 | 567 |
| `--arc-text-lg` | 743 | 568 |
| `--arc-text-muted` | 683, 834 | 779, 810 |
| `--arc-text-secondary` | 682, 833 | 778 |
| `--arc-text-sm` | 741 | 566 |
| `--arc-text-xl` | 744 | 569 |
| `--arc-text-xs` | 740 | 565 |
| `--arc-tracking-body` | 750 | 575, 891 |
| `--arc-tracking-display` | 749 | 574, 896 |
| `--arc-warning` | 706, 854 | 784 |

## 验收记录

每片均在 apps/web 运行 `pnpm exec tsc --noEmit`、`pnpm test`、`pnpm build`。最终测试 44 个文件、411 项通过。产物包括浏览器端及 SSR 构建。

| 真实浏览器操作 | 结果 |
|---|---|
| Chrome 1280×820、768×820、375×820；中文深色与英文浅色 | Home、Projects、Settings、Login 在三种宽度通过。选择 Skill 后输入内容出现，搜索无结果，Escape 关闭弹层。 |
| 账户外观 | Light、Dark、System 切换写入原偏好；System 对操作系统明暗变更立即响应。 |
| 桌面与手机登录 | 请求验证码、错误验证码提示、焦点回到首格、正确码验证、跳转 Home 全部通过。使用隔离本地 API 邮箱接收验证码，未验证外部邮件投递。 |
| Home 首发 | 浏览器发起 1 次 staging 签名，1 次对象存储 PUT，1 次项目创建，1 次 attach，1 次 Chat POST；消息 API 返回 1 条持久用户消息。 |
| Projects | 真实项目列表、重命名并恢复、打开、等待详情加载后刷新并返回、按字段排序、搜索与清空均通过。 |
| 设置与焦点 | 真实偏好 PUT 成功后恢复原值。Settings → Add credits → Tooltip 分层 Escape；焦点回到 Add credits，再关闭回到账户触发按钮。 |
| 项目删除 | Space 勾选、焦点默认在取消、确认框拒绝 backdrop 关闭。注入批量接口 422 后，错误提示出现在当前 modal 且选择保留。使用真实 API 删除独立 QA 项目后返回项目库。 |
| reduced-motion | 三尺寸浏览器运行开启 reduce；弹层、切页、表单和键盘交互均完成。 |

此前一次快速详情刷新后立即后退在开发服务器触发 Router hydration 警告。等待详情加载再后退的回归通过。未验收实体设备、Safari/Firefox、外部邮件、外部支付或社交 OAuth。

截图按 `页面-宽度-主题.png` 命名。基线、U0 Home、U1 Login 与 U2 分别位于 [before](before)、[u0](u0)、[u1](u1)、[after](after)。Projects 基线测试账户为空；U2 使用隔离测试账户的真实首发项目。
