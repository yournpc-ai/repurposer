/** C-1 acceptance suite (合同 §7 C-1; I-PFA-02/03) — the settled canvas's
 * Product Graph rank projection. Pure: no DOM, no server — fixtures feed
 * `projectSettledFrames` the rank the server would stamp.
 *
 * 不可妥协验收句的测试形态：settled 路径的 x 永远 = rank × PITCH（524 =
 * product_graph.PITCH ↔ graph_store._PITCH ↔ layout.ts PITCH 的三镜像值），
 * stored frame.x 永不被读；frame 与拓扑脱节（L1 的 late-born 中间节点）时
 * 投影照样严格 L→R。 */

import { describe, expect, it } from "vitest"

import { flowNodeSize, projectSettledFrames } from "./layout"
import type { FlowEdge, FlowNode } from "./types"

// The three-mirror pitch value (product_graph.PITCH ↔ graph_store._PITCH ↔
// layout.ts PITCH) — hardcoded here so a silent constant drift turns red.
const PITCH = 524
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

describe("projectSettledFrames — ADR-098 B3 读时归一 (double-mirror fixtures)", () => {
  /** 事故同构 fixture（mirror of apps/api/tests/test_product_graph_pure.py::
   * test_accident_isomorph_mixed_island_both_cohorts_dead — SAME ranks, SAME
   * stamp shape, two runtimes; 项目 62594b0b 取证原型）: the pre-B1 island
   * {transcript, quotes} cols=2 split into two rank cohorts at read time;
   * both corridors fully died server-side, so NEITHER node carries a
   * spec.island stamp — the client mechanism is untouched (rank × PITCH +
   * spec.island two entries), the dead cohort simply never arrives. */
  it("dead corridor: no stamp → plain column law, zero reserved_bottom ghost", () => {
    const nodes = [
      node("asset", 0, { x: 0, y: 0 }),
      // Stored frame y stays (append-only, zero migration) — the former
      // island cell seats ride as plain serverY seats.
      node("transcript", 1, { x: 524, y: -88 }),
      node("quotes", 2, { x: 524, y: 488 }),
      // A later band-1 mate: without the dead corridor's floor it compresses
      // to the transcript's render bottom — NOT to the ghost reserved bottom
      // (the accident island's reservation would have floored it at 2216).
      node("follower", 1, { x: 524, y: 3000 }),
    ]
    const edges = [
      edge("asset", "transcript", "text"),
      edge("transcript", "quotes", "text"), // the A3-lite synthesized leg
      edge("asset", "quotes", "text"),
    ]
    const { positions, revealOrder, violations } = projectSettledFrames(nodes, edges)
    // 双镜像同数 (G): ranks 0/1/2 → x = 0/524/1048 — the server's numbers.
    expect(positions.get("asset")!.x).toBe(0)
    expect(positions.get("transcript")!.x).toBe(PITCH)
    expect(positions.get("quotes")!.x).toBe(2 * PITCH)
    expect(positions.get("transcript")!.y).toBe(-88) // plain law, first in column
    expect(positions.get("quotes")!.y).toBe(488) // stored seat rides, never moved
    // reserved_bottom 幽灵死: the follower pulls up to the transcript's real
    // bottom (DRAFT_H 278 + gap), never to a corridor floor.
    expect(positions.get("follower")!.y).toBe(-88 + DRAFT_H + GAP_CROSS)
    // B→C 方向不变量成立 (E); revealOrder 恒 from 先于 to (F).
    expect(violations).toEqual([])
    const order = [...revealOrder.entries()].sort(([, i], [, j]) => i - j).map(([id]) => id)
    expect(order).toEqual(["asset", "transcript", "follower", "quotes"])
  })

  /** 活廊道对照组（mirror of the server writers fixture
   * test_display_ranks_writers_share_one_island_band /
   * test_legacy_mixed_island_writers_cohort_keeps_corridor）: a ≥2 cohort's
   * corridor LIVES — members render at frozen cell y verbatim and the
   * reserved bottom floors the column's compression. Server numbers: island
   * born at band 2, origin_y -176, row_h 576, cap 4 → cells -176/400/976,
   * reserved_bottom 2112. */
  it("alive corridor: frozen cells verbatim + reserved_bottom floors a plain band-mate", () => {
    const stamp = { island: { reserved_bottom: 2112 } }
    const nodes = [
      node("asset", 0, { x: 0, y: 0 }),
      node("transcript", 1, { x: 524, y: -88 }),
      { ...node("w1", 2, { x: 1048, y: -176 }), spec: stamp },
      { ...node("w2", 2, { x: 1048, y: 400 }), spec: stamp },
      { ...node("w3", 2, { x: 1048, y: 976 }), spec: stamp },
      node("plain", 2, { x: 1048, y: 3000 }),
    ]
    const { positions, violations } = projectSettledFrames(nodes, [])
    expect(positions.get("w1")!.y).toBe(-176)
    expect(positions.get("w2")!.y).toBe(400)
    expect(positions.get("w3")!.y).toBe(976)
    for (const w of ["w1", "w2", "w3"]) expect(positions.get(w)!.x).toBe(2 * PITCH)
    // The corridor's empty rows are never invaded: the plain band-mate's
    // compression floors at reserved_bottom + gap (2112 + 16), never higher.
    expect(positions.get("plain")!.y).toBe(2112 + GAP_CROSS)
    expect(violations).toEqual([])
  })
})
