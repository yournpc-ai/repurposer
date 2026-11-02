import { describe, expect, it } from "vitest"

import { MENTION_REGISTRY } from "./mentions"

describe("Chat @output candidates", () => {
  it("offers only video Outputs", async () => {
    const source = MENTION_REGISTRY.find((entry) => entry.type === "output")?.source
    expect(source).toBeDefined()
    const candidates = await source!({
      outputs: [
        { id: "video", label: "Video", kind: "film" },
        { id: "post", label: "Post", kind: "post" },
        { id: "quotes", label: "Quotes", kind: "quotes" },
        { id: "clip", label: "Clip", kind: "clip" },
      ],
    })
    expect(candidates.map((candidate) => candidate.id)).toEqual(["video", "clip"])
  })
})
