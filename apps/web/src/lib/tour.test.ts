import { describe, expect, it } from "vitest"

import {
  canOpenTour,
  shouldAutoOpenTour,
  tourVersionOf,
  type TourStepDef,
} from "./tour"

const STEPS: TourStepDef[] = [
  {
    target: "[data-tour='one']",
    titleKey: "tour.oneTitle",
    descKey: "tour.oneDesc",
  },
]

describe("canOpenTour — tour/auth 边界", () => {
  it("只在已登录且 LoginDialog 关闭时允许打开", () => {
    expect(canOpenTour(true, false)).toBe(true)
    expect(canOpenTour(false, false)).toBe(false)
    expect(canOpenTour(true, true)).toBe(false)
    expect(canOpenTour(false, true)).toBe(false)
  })
})

describe("shouldAutoOpenTour — 首访自动打开", () => {
  it("未见过当前版本且登录框关闭时才自动打开", () => {
    expect(shouldAutoOpenTour(null, "v1", true, false)).toBe(true)
    expect(shouldAutoOpenTour("old", "v1", true, false)).toBe(true)
    expect(shouldAutoOpenTour("v1", "v1", true, false)).toBe(false)
    expect(shouldAutoOpenTour(null, "v1", false, false)).toBe(false)
    expect(shouldAutoOpenTour(null, "v1", true, true)).toBe(false)
  })
})

describe("tourVersionOf — 版本即内容", () => {
  it("相同定义得到稳定版本", () => {
    expect(tourVersionOf(STEPS, { title: "A" })).toBe(
      tourVersionOf(STEPS, { title: "A" }),
    )
  })

  it("步骤变化会得到新版本", () => {
    const moved = [{ ...STEPS[0], side: "top" as const }]
    expect(tourVersionOf(moved, { title: "A" })).not.toBe(
      tourVersionOf(STEPS, { title: "A" }),
    )
  })

  it("EN 文案变化会得到新版本", () => {
    expect(tourVersionOf(STEPS, { title: "B" })).not.toBe(
      tourVersionOf(STEPS, { title: "A" }),
    )
  })
})
