/** C-1 acceptance suite (合同 §7 C-1; I-PFA-02/03) — the settled canvas's
 * Product Graph rank projection. Pure: no DOM, no server — fixtures feed
 * `projectSettledFrames` the rank the server would stamp.
 *
 * 不可妥协验收句的测试形态：settled 路径的 x 永远 = rank × PITCH（464 =
 * product_graph.PITCH ↔ graph_store._PITCH ↔ layout.ts PITCH 的三镜像值），
 * stored frame.x 永不被读；frame 与拓扑脱节（L1 的 late-born 中间节点）时
 * 投影照样严格 L→R。 */

import { describe, expect, it } from "vitest"

import { projectSettledFrames } from "./layout"
import type { FlowEdge, FlowNode } from "./types"

// The three-mirror pitch value (product_graph.PITCH ↔ graph_store._PITCH ↔
// layout.ts PITCH) — hardcoded here so a silent constant drift turns red.
const PITCH = 464
// A video-kind draft card's deterministic render height (PRODUCT_LABEL_PX 26
// + DRAFT_BODY_PX 120 + PROGRAM_REGION_PX 88 + PRODUCT_TOOLBAR_PX 44).
const DRAFT_H = 278
const GAP_CROSS = 16

function node(
  id: string,
  rank: number | null,
  frame: { x: number; y: number; w?: number; h?: number },
  order = 0,
): FlowNode {
  return {
    id,
    kind: "video",
    label: id,
    rank,
    frame: { w: 400, h: 560, ...frame },
    order,
  }
}

function edge(from: string, to: string, edgeType?: FlowEdge["edgeType"]): FlowEdge {
  return { from, to, edgeType }
}

describe("projectSettledFrames — C-1 rank projection", () => {
  it("x = rank × PITCH; the column key is rank, never the stored frame.x", () => {
    // All three nodes carry the SAME wrong stored x (0) — under the old law
    // they'd collapse into one column; under C-1 rank separates them.
    const nodes = [
      node("a", 0, { x: 0, y: 0 }),
      node("b", 1, { x: 0, y: 0 }),
      node("c", 2, { x: 0, y: 0 }),
    ]
    const { positions, violations } = projectSettledFrames(nodes, [])
    expect(positions.get("a")!.x).toBe(0)
    expect(positions.get("b")!.x).toBe(PITCH)
    expect(positions.get("c")!.x).toBe(2 * PITCH)
    expect(violations).toEqual([])
  })

  it("L1 regression (旗舰用例): a late-born intermediate node whose stored frames completely contradict the topology still projects strictly L→R", () => {
    // The historical bug shape: frames stamped at birth (928 / 464 / 100 —
    // pitch drift + late birth) while the true ranks are 0 / 1 / 2.
    const nodes = [
      node("a", 0, { x: 928, y: 0 }),
      node("b", 1, { x: 464, y: 0 }),
      node("c", 2, { x: 100, y: 0 }),
    ]
    const edges = [edge("a", "b", "video"), edge("b", "c", "text")]
    const { positions, violations } = projectSettledFrames(nodes, edges)
    expect(positions.get("a")!.x).toBeLessThan(positions.get("b")!.x)
    expect(positions.get("b")!.x).toBeLessThan(positions.get("c")!.x)
    expect(positions.get("c")!.x).toBe(2 * PITCH) // not 100 — frame.x lost authority
    expect(violations).toEqual([])
  })

  it("direction invariant: a rank-reversed edge is a named violation (防假绿负例)", () => {
    const nodes = [node("a", 1, { x: 0, y: 0 }), node("b", 0, { x: 0, y: 0 })]
    const { violations } = projectSettledFrames(nodes, [edge("a", "b", "video")])
    expect(violations).toHaveLength(1)
    expect(violations[0]).toContain("rank violation")
    expect(violations[0]).toContain("a")
    expect(violations[0]).toContain("b")
  })

  it("ctx edges are not product edges: they never enter the invariant", () => {
    const nodes = [node("a", 0, { x: 0, y: 0 }), node("b", 0, { x: 0, y: 100 })]
    const { violations } = projectSettledFrames(nodes, [edge("a", "b", "ctx")])
    expect(violations).toEqual([])
  })

  it("rank-null = compatibility display, never legal topology (约束❷)", () => {
    // The B4-gate-survivor orphan: drawn at its stored frame.x, but its
    // product edge is a named violation — the fallback never acquits it.
    const nodes = [node("a", 0, { x: 0, y: 0 }), node("orphan", null, { x: 2000, y: 0 })]
    const { positions, violations } = projectSettledFrames(nodes, [edge("a", "orphan", "video")])
    expect(positions.get("orphan")!.x).toBe(2000) // compatibility seat
    expect(violations).toHaveLength(1)
    expect(violations[0]).toContain("rank-null endpoint")
    expect(violations[0]).toContain("orphan")
  })

  it("y compression is preserved (ADR-082): followers pull up to the predecessor's render bottom, never past the server seat", () => {
    // Pull-up: the follower reserved far below (draft 560 reservation air)
    // compacts to the predecessor's current render bottom + gap.
    const pullUp = projectSettledFrames(
      [node("top", 2, { x: 0, y: 0 }), node("follower", 2, { x: 0, y: 1000 })],
      [],
    )
    expect(pullUp.positions.get("top")!.y).toBe(0)
    expect(pullUp.positions.get("follower")!.y).toBe(DRAFT_H + GAP_CROSS)
    // min() safety: a server seat ABOVE the compressed bottom is kept —
    // compaction never pushes a node past its seat downward-pull-free.
    const seated = projectSettledFrames(
      [node("top", 2, { x: 0, y: 0 }), node("floor", 2, { x: 0, y: 100 })],
      [],
    )
    expect(seated.positions.get("floor")!.y).toBe(100)
  })

  it("错帧双杀 (shared malicious fixture, 用户点名): the same corrupted frames feed BOTH consumers — Canvas projects L→R while (mirror suite API-side) execution orders A→B→C", () => {
    // Mirror of apps/api/tests/test_graph_wiring_pure.py::
    // test_run_op_double_kill_shared_fixture — SAME frames, SAME ranks, two
    // runtimes. If this pair ever diverges, one of the two consumers
    // re-derived topology on its own.
    const nodes = [
      node("a", 0, { x: 928, y: 0 }),
      node("b", 1, { x: 100, y: 0 }),
      node("c", 2, { x: 464, y: 0 }),
    ]
    const edges = [edge("a", "b", "video"), edge("b", "c", "video")]
    const { positions, violations } = projectSettledFrames(nodes, edges)
    expect(positions.get("a")!.x).toBe(0)
    expect(positions.get("b")!.x).toBe(PITCH)
    expect(positions.get("c")!.x).toBe(2 * PITCH)
    expect(violations).toEqual([])
  })

  it("revealOrder = rank-major then frame y; insertion order never matters", () => {
    const nodes = [
      node("c", 2, { x: 0, y: 0 }),
      node("a", 0, { x: 0, y: 50 }),
      node("b1", 1, { x: 0, y: 200 }),
      node("b0", 1, { x: 0, y: 100 }),
    ]
    const expected = ["a", "b0", "b1", "c"]
    const shuffled = [nodes[2], nodes[0], nodes[3], nodes[1]]
    for (const input of [nodes, shuffled]) {
      const { revealOrder } = projectSettledFrames(input, [])
      const order = [...revealOrder.entries()].sort(([, i], [, j]) => i - j).map(([id]) => id)
      expect(order).toEqual(expected)
    }
  })
})
