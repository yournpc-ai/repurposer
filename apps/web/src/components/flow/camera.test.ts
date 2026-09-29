/** cameraPanDelta contract suite (Workspace 合同 v4.2 C5) — pins the window-
 * shift sign law: a target beyond the RIGHT edge gets a POSITIVE dx (the
 * window shifts right toward it); the inverted-sign regression panned the
 * camera into empty space away from newborn nodes. */

import { describe, expect, it } from "vitest"

import { cameraPanDelta, clusterGesture } from "./camera"

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

describe("clusterGesture", () => {
  it("empty cluster → null (the caller spends the request silently)", () => {
    expect(clusterGesture([])).toBeNull()
  })

  it("a single card → zoom-locked CENTER on itself", () => {
    expect(clusterGesture([{ x: 100, y: 50, w: 280, h: 660 }])).toEqual({
      kind: "center",
      cx: 240,
      cy: 380,
    })
  })

  it("multiple cards → FIT over the union bounds (2026-09-30 簇适应窗口拍板)", () => {
    // The image-#66 cluster: a station chain spread by the island cell +
    // fresh-column rise — bbox-center at a locked zoom was empty canvas.
    const gesture = clusterGesture([
      { x: 524, y: 588, w: 280, h: 660 }, // Clips (island cell, seq 1)
      { x: 1048, y: -176, w: 340, h: 560 }, // the doc companion station
      { x: 1572, y: -264, w: 280, h: 660 }, // the translate station
    ])
    expect(gesture).toEqual({
      kind: "fit",
      bounds: { minX: 524, minY: -264, maxX: 1852, maxY: 1248 },
    })
  })
})
