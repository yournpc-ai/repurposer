import { describe, expect, it } from "vitest"

import { cn } from "./utils"

describe("cn", () => {
  it("merges conditional classes", () => {
    expect(cn("foo", false && "bar", "baz")).toBe("foo baz")
  })

  it("resolves tailwind conflicts", () => {
    expect(cn("px-2 px-4")).toBe("px-4")
  })
})
