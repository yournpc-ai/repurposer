/** cameraPanDelta contract suite (Workspace 合同 v4.2 C5) — pins the window-
 * shift sign law: a target beyond the RIGHT edge gets a POSITIVE dx (the
 * window shifts right toward it); the inverted-sign regression panned the
 * camera into empty space away from newborn nodes. */

import { describe, expect, it } from "vitest"

import { cameraPanDelta, framesBBoxCenter } from "./camera"

const SAFE = { left: 100, top: 100, right: 900, bottom: 700 }

describe("cameraPanDelta", () => {
  it("already inside → zero move (已在安全区：不动)", () => {
    expect(
      cameraPanDelta({ minX: 200, minY: 200, maxX: 400, maxY: 400 }, SAFE),
    ).toEqual({ dx: 0, dy: 0 })
  })

  it("target beyond the RIGHT edge → positive dx, minimal shortfall", () => {
    // The observed case: a chain growing rightward (transcript → translation
    // → Translate captions) births nodes past the safe right edge.
    const { dx, dy } = cameraPanDelta(
      { minX: 950, minY: 200, maxX: 1200, maxY: 400 },
      SAFE,
    )
    expect(dx).toBe(300) // window shifts right by maxX - right
    expect(dy).toBe(0)
    // After the shift the right edge lands exactly on the safe edge.
    expect(1200 - dx).toBe(SAFE.right)
  })

  it("target beyond the LEFT edge → negative dx", () => {
    const { dx } = cameraPanDelta(
      { minX: -300, minY: 200, maxX: 50, maxY: 400 },
      SAFE,
    )
    expect(dx).toBe(-400) // minX - left
    expect(-300 - dx).toBe(SAFE.left) // left edge lands on the safe edge
  })

  it("target above / below → dy sign follows the target", () => {
    expect(
      cameraPanDelta({ minX: 200, minY: -200, maxX: 400, maxY: 50 }, SAFE).dy,
    ).toBe(-300)
    expect(
      cameraPanDelta({ minX: 200, minY: 800, maxX: 400, maxY: 1000 }, SAFE).dy,
    ).toBe(300)
  })

  it("a cluster wider than the safe region aligns its near (left) edge", () => {
    const { dx } = cameraPanDelta(
      { minX: 500, minY: 200, maxX: 2000, maxY: 400 },
      SAFE,
    )
    expect(dx).toBe(400) // minX - left, not maxX - right
  })

  it("an over-tall cluster beyond the bottom aligns its near (top) edge", () => {
    const { dy } = cameraPanDelta(
      { minX: 200, minY: 400, maxX: 400, maxY: 2000 },
      SAFE,
    )
    expect(dy).toBe(300) // minY - top
  })

  it("a cluster straddling both left and right aligns the left edge", () => {
    const { dx } = cameraPanDelta(
      { minX: -500, minY: 200, maxX: 2000, maxY: 400 },
      SAFE,
    )
    expect(dx).toBe(-600) // minX - left (first branch wins)
  })
})

describe("framesBBoxCenter", () => {
  it("empty cluster → null (the caller spends the request silently)", () => {
    expect(framesBBoxCenter([])).toBeNull()
  })

  it("a single frame centers on itself", () => {
    expect(framesBBoxCenter([{ x: 100, y: 50, w: 280, h: 660 }])).toEqual({
      cx: 240,
      cy: 380,
    })
  })

  it("a cluster centers on its union bbox (the fitView centering math, zoom untouched)", () => {
    const center = framesBBoxCenter([
      { x: 524, y: 588, w: 280, h: 660 },
      { x: 1572, y: 500, w: 280, h: 660 },
    ])
    expect(center).toEqual({ cx: (524 + 1852) / 2, cy: (500 + 1248) / 2 })
  })
})
