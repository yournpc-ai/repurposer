/** 谓词真值表 (flora-parity-ui 验证仪式链 · ADR-118 §6): 双键 → 锚卡分
 * 支。两钉 = 桌面 true/true 零锚卡、移动 false/false 锚卡；移动世界已
 * 揭幕（false/true）同律 —— 画布在 768px 以下永不挂载。桌面
 * plan-ready reveal 前的中间态（true/false）本套件刻意不钉 —— 真值表
 * 未定其语义，待拍板（见批次报告开放问题）。 */

import { describe, expect, it } from "vitest"

import { anchorCardsVisible, canvasVisible } from "./canvasVisibility"

describe("canvasVisible — 环境谓词真值表 (ADR-118 §6)", () => {
  it("桌面 = 可承载 ∧ 已揭幕 (true/true) → 画布在屏,零锚卡", () => {
    const desktop = { canvasAvailable: true, worldLive: true }
    expect(canvasVisible(desktop)).toBe(true)
    expect(anchorCardsVisible(desktop)).toBe(false)
  })

  it("移动 = 不可承载 ∧ 未揭幕 (false/false) → 无画布,锚卡渲染", () => {
    const mobile = { canvasAvailable: false, worldLive: false }
    expect(canvasVisible(mobile)).toBe(false)
    expect(anchorCardsVisible(mobile)).toBe(true)
  })

  it("移动世界已揭幕 (false/true) → 画布在 768px 以下永不挂载,锚卡照常渲染", () => {
    const mobileLive = { canvasAvailable: false, worldLive: true }
    expect(canvasVisible(mobileLive)).toBe(false)
    expect(anchorCardsVisible(mobileLive)).toBe(true)
  })

  it("锚卡渲染 ⟺ !canvas_visible —— 同一环境的两个谓词永不相悖", () => {
    for (const canvasAvailable of [true, false]) {
      for (const worldLive of [true, false]) {
        const env = { canvasAvailable, worldLive }
        expect(anchorCardsVisible(env)).toBe(!canvasVisible(env))
      }
    }
  })
})
