# Tour 组件 — 实施简报

> Status: 📋 待开工（2026-07-23）
> 目标形态：**完整可用、随处可挂的通用 Tour 组件**，不绑定具体使用场景（挂哪由调用方以后决定）
> 质量口径：**shadcn 组件级别**——复制进仓库、吃项目 design token、调用方拥有行为；验收标准 §5 逐项可查

## 1. 一句话目标

在 `components/ui/tour.tsx` 交付一个受控的聚光灯分步引导组件：steps 进、回调出，视觉/动画/键盘可达达到 shadcn 生态 tour 组件水准，且零新增依赖。

## 2. 技术选型

**手搓，不引库。** 定位引擎 = base-ui Positioner（底层 floating-ui，与 Radix 系 tour 同源）；popover = 项目卡片语言；聚光灯挖孔 = `box-shadow: 0 0 0 9999px` 经典技巧。

| 候选 | 否决理由 |
|---|---|
| driver.js | popover 是它自己的 DOM + 自带样式表，设计保真要靠覆盖对抗 |
| Onborda / Radix registry 块 | 引入第二原语层（Radix）+ Next.js 耦合 |
| Tour Kit headless | 生态太新，维护风险不值得为一个可控范围组件承担 |

## 3. API 设计

```tsx
interface TourStep {
  target: string          // CSS 选择器，如 "[data-tour='composer']"
  title: string
  description: string
  side?: "top" | "bottom" | "left" | "right"   // 默认 bottom
  align?: "start" | "center" | "end"           // 默认 center
}

interface TourProps {
  steps: TourStep[]
  open: boolean                     // 受控——何时开始由调用方决定
  onOpenChange(open: boolean): void
  onComplete?(): void               // seen 持久化归调用方（对接 users.preferences）
  onSkip?(): void
}
```

- chrome 文案（Next/Prev/Skip/Done）组件内置走 `t()`，i18n 加 `tour.*` keys（en/zh 同步）；
- steps 内容由调用方传入已翻译字符串；
- 组件**不碰** localStorage / preferences / analytics——纯机制，无行为锁定。

## 4. 行为规格

- 聚光灯 = 目标 rect 上的 `rounded-md` 高亮环 + 全屏暗化，步骤间**平滑滑动/缩放**（CSS transition on rect）；
- 每步 `scrollIntoView`（尊重 `prefers-reduced-motion`，降级为即时跳转 + 无过渡动画）；
- 目标元素不存在 → 自动跳步；全部不存在 → 不渲染；
- Esc 关闭（= skip）；←→ 切步；焦点进 popover，Tab 圈在 popover 内；
- 遮罩拦截背景点击（点击不关闭，防误触）；
- resize / scroll（capture）/ 目标尺寸变化（ResizeObserver）→ 重算 rect；
- SSR：mounted 前不渲染任何东西；
- popover 定位 = base-ui Positioner anchor 到目标元素（spike 验证 anchor API；不行则 fallback 手动 rect + floating-ui，base-ui 已传递依赖）。

## 5. 验收标准（"shadcn 级别"口径）

- [ ] 聚光灯在步骤间平滑滑动/缩放（非瞬移）
- [ ] popover 进出场动画（transform/opacity-only，与项目 Dialog/Popover 既有模式一致）
- [ ] 贴边目标 popover 自动翻转/偏移（floating-ui 碰撞处理生效）
- [ ] Esc / ←→ / Tab 焦点圈全部可用
- [ ] 进度指示（dots 或 1/N）
- [ ] 明暗两主题视觉正常；全部颜色走 theme 变量，无硬编码色值；`rounded-md` 纪律（无 rounded-full）
- [ ] 边界 case（`/dev/tour` 验收页覆盖）：可滚动容器内目标 / 目标不存在自动跳步 / 视口边缘目标 / resize 中切步
- [ ] SSR 安全：首屏服务端/客户端渲染一致，无 hydration 报错
- [ ] `pnpm lint` + `pnpm build` 绿

## 6. 验收场

`apps/web/src/routes/dev.tour.tsx`——mock 靶元素（含滚动容器内目标、视口边缘目标）+ 触发按钮 + 回调 console.log。作为组件常驻回归场保留。

## 7. Prohibited Behaviors

- **禁止**新增 npm 依赖（定位用 base-ui 自带能力；spike 失败须先回报再议）；
- **禁止**引入 Radix / framer-motion（动画一律 CSS transition，transform/opacity-only）；
- **禁止**硬编码色值——全部走 shadcn theme 变量；
- **禁止**组件内置 localStorage / 持久化 / 埋点——open 受控，回调留给调用方；
- **禁止**多页跳转功能（API 预留 `target` 为 selector 即可，不实现跨路由续走）；
- **禁止**在 SSR 期触碰 `document` / `window` / `matchMedia`（仅 useEffect / 事件处理器内）。
