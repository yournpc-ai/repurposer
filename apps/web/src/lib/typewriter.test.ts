import { afterEach, describe, expect, it, vi } from "vitest"

import { createTypewriter } from "./typewriter"

afterEach(() => {
  vi.useRealTimers()
})

describe("typewriter Unicode visibility", () => {
  it("never releases a lone surrogate half", () => {
    vi.useFakeTimers()
    const chunks: string[] = []
    const typewriter = createTypewriter((text) => chunks.push(text))
    typewriter.push("a😀b")
    vi.advanceTimersByTime(24)
    expect(chunks).toEqual(["a😀"])
    vi.advanceTimersByTime(24)
    expect(chunks).toEqual(["a😀", "b"])
    typewriter.discard()
  })
})
