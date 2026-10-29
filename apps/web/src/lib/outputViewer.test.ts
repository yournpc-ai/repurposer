import { describe, expect, it } from "vitest"

import type { Output } from "@/lib/types"
import { outputViewerItems } from "./outputViewer"

const output = (id: string, version = 1) => ({
  id,
  composition_version_number: version,
}) as Output

describe("B-UI shared Output identity and order", () => {
  it("dedupes repeated references without changing first-delivery order", () => {
    const a = output("a", 3)
    const b = output("b", 3)
    const items = outputViewerItems([
      { output_id: "a", output: a },
      { output_id: "b", output: b },
      { output_id: "a", output: a },
    ], "b", b)
    expect(items.map((item) => item.output_id)).toEqual(["a", "b"])
    expect(items.map((item) => item.output?.composition_version_number)).toEqual([3, 3])
  })

  it("appends only an opened item missing from the refreshing projection", () => {
    const current = output("current")
    const fresh = output("fresh", 2)
    const entries = [{ output_id: "current", output: current }]
    expect(outputViewerItems(entries, "fresh", null).map((item) => item.output_id)).toEqual(["current"])
    expect(outputViewerItems(entries, "fresh", fresh).map((item) => item.output_id)).toEqual(["current", "fresh"])
  })

  it("keeps an unavailable exact historical ref instead of substituting another Output", () => {
    const newer = output("newer", 4)
    const items = outputViewerItems([{ output_id: "old", output: null }], "old", newer)
    expect(items).toHaveLength(1)
    expect(items[0]).toEqual({ output_id: "old", output: null })
  })
})
