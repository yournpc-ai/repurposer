import { describe, expect, it } from "vitest"

import {
  formatMediaTimeMs,
  makeMediaRegionSelection,
  videoContentRect,
} from "./mediaRegionSelection"

describe("media region selection", () => {
  it("maps object-contain letterboxing into the real content box", () => {
    expect(videoContentRect(
      { width: 1000, height: 1000 },
      { width: 1920, height: 1080 },
    )).toEqual({ x: 0, y: 218.75, width: 1000, height: 562.5 })
  })

  it("captures intrinsic pixels, normalized coordinates and the paused frame time", () => {
    const selection = makeMediaRegionSelection({
      viewportRect: { x: 250, y: 140.625, width: 500, height: 281.25 },
      viewportSize: { width: 1000, height: 562.5 },
      sourceSize: { width: 1920, height: 1080 },
      mediaTimeSeconds: 12.3456,
    })
    expect(selection.coordinateSpace).toBe("source_pixels")
    expect(selection.mediaTimeMs).toBe(12346)
    expect(selection.sourceRect).toEqual({ x: 480, y: 270, width: 960, height: 540 })
    expect(selection.normalizedRect.x).toBeCloseTo(0.25, 12)
    expect(selection.normalizedRect.y).toBeCloseTo(0.25, 12)
    expect(selection.normalizedRect.width).toBeCloseTo(0.5, 12)
    expect(selection.normalizedRect.height).toBeCloseTo(0.5, 12)
    expect(selection.viewportRect).toEqual({ x: 250, y: 140.625, width: 500, height: 281.25 })
  })

  it("clamps the captured rectangle to the media bounds", () => {
    const selection = makeMediaRegionSelection({
      viewportRect: { x: -20, y: 90, width: 200, height: 100 },
      viewportSize: { width: 100, height: 100 },
      sourceSize: { width: 1000, height: 1000 },
      mediaTimeSeconds: 1,
    })
    expect(selection.normalizedRect.x).toBe(0)
    expect(selection.normalizedRect.y).toBeCloseTo(0.9, 12)
    expect(selection.normalizedRect.width).toBe(1)
    expect(selection.normalizedRect.height).toBeCloseTo(0.1, 12)
    expect(selection.sourceRect).toEqual({ x: 0, y: 900, width: 1000, height: 100 })
  })

  it("formats millisecond frame timestamps without dropping sub-second precision", () => {
    expect(formatMediaTimeMs(12_345)).toBe("00:12.345")
    expect(formatMediaTimeMs(3_723_004)).toBe("01:02:03.004")
  })
})
