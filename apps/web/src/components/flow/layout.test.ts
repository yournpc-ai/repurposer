import { describe, expect, it } from "vitest"

import { declaredHandles, layoutFlow } from "./layout"
import type { FlowEdge, FlowNode } from "./types"

function node(id: string, overrides: Partial<FlowNode> = {}): FlowNode {
  return {
    id,
    kind: "text",
    label: id,
    frame: { x: 0, y: 0, w: 340, h: 280 },
    order: 0,
    ...overrides,
  }
}

function edge(from: string, to: string, edgeType: FlowEdge["edgeType"] = "text"): FlowEdge {
  return { from, to, edgeType }
}

describe("asset and manual Graph layout", () => {
  it("layers nodes from their real connections, not legacy product ranks", () => {
    const a = node("a", { frame: { x: 900, y: 0, w: 340, h: 280 } })
    const b = node("b", { frame: { x: 100, y: 0, w: 340, h: 280 } })
    const c = node("c", { frame: { x: 0, y: 0, w: 340, h: 280 } })
    const layout = layoutFlow([c, b, a], [edge("a", "b"), edge("b", "c")])
    expect(layout.positions.get("a")!.x).toBeLessThan(layout.positions.get("b")!.x)
    expect(layout.positions.get("b")!.x).toBeLessThan(layout.positions.get("c")!.x)
  })

  it("keeps independent nodes and joins in stable order", () => {
    const layout = layoutFlow(
      [node("joined", { order: 2 }), node("second", { order: 1 }), node("first", { order: 0 })],
      [edge("first", "joined"), edge("second", "joined")],
    )
    expect(layout.positions.get("first")!.x).toBe(layout.positions.get("second")!.x)
    expect(layout.positions.get("first")!.y).toBeLessThan(layout.positions.get("second")!.y)
    expect(layout.positions.get("joined")!.x).toBeGreaterThan(layout.positions.get("first")!.x)
  })

  it("declares manual input ports without product pager or Clip lanes", () => {
    const handles = declaredHandles(node("manual"), { width: 340, height: 280 }, {
      in: ["video", "text"], out: ["text"],
    })!
    expect(handles.find((h) => h.id === "in:video")!.y).toBe(236)
    expect(handles.find((h) => h.id === "in:text")!.y).toBe(202)
    expect(handles.find((h) => h.id === "out:text")!.y).toBe(40)
  })
})

describe("asset transcript port", () => {
  const mediaAsset = (type: string): FlowNode => node("asset", {
    asset: { id: "a1", type, title: null, file_url: null },
  })
  const size = { width: 400, height: 700 }

  it("places text at the transcript and preserves the media top port", () => {
    const handles = declaredHandles(mediaAsset("video"), size, { in: [], out: ["text", "video"] })!
    expect(handles.find((h) => h.id === "out:video")!.y).toBe(40)
    expect(handles.find((h) => h.id === "out:text")!.y).toBe(700 - 207 - 28)
  })

  it("uses the ordinary top stack for an image asset", () => {
    const handles = declaredHandles(mediaAsset("image"), size, { in: [], out: ["video", "text"] })!
    expect(handles.find((h) => h.id === "out:video")!.y).toBe(40)
    expect(handles.find((h) => h.id === "out:text")!.y).toBe(74)
  })
})
