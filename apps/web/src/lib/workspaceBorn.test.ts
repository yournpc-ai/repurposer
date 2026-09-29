/** workspaceBorn contract suite (Workspace 合同 v4.2 C3) — pins the flip
 * condition's per-face law so a state-vocabulary change on the server can
 * never silently re-open the send-beat birth (the transcript card's birth
 * state moved queued → running once already; the coarse predicate fired at
 * the send beat until it read the terminal face instead). */

import { describe, expect, it } from "vitest"

import { workspaceBornOf } from "./workspaceBorn"

type Node = Parameters<typeof workspaceBornOf>[0] extends (infer T)[] | null | undefined
  ? T
  : never

function node(
  state: string,
  opts: { role?: string; asset?: boolean } = {},
): Node {
  return {
    state,
    spec: opts.role ? { role: opts.role } : {},
    asset: opts.asset ? { id: "a1", type: "VIDEO", title: null, file_url: null } : null,
  } as Node
}

describe("workspaceBornOf", () => {
  it("empty / missing frames are not born", () => {
    expect(workspaceBornOf(null)).toBe(false)
    expect(workspaceBornOf(undefined)).toBe(false)
    expect(workspaceBornOf([])).toBe(false)
  })

  it("Source (asset-dossier) nodes never birth the canvas", () => {
    expect(workspaceBornOf([node("done", { asset: true })])).toBe(false)
  })

  it("a docked draft chain births the canvas (图先展示后运行)", () => {
    expect(workspaceBornOf([node("done", { asset: true }), node("draft")])).toBe(true)
  })

  it("the upload-born transcript card sits running with no content — NO birth at the send beat", () => {
    expect(
      workspaceBornOf([node("done", { asset: true }), node("running", { role: "transcript" })]),
    ).toBe(false)
  })

  it("the transcript card births the canvas on its terminal face (done / failed)", () => {
    expect(workspaceBornOf([node("done", { role: "transcript" })])).toBe(true)
    expect(workspaceBornOf([node("failed", { role: "transcript" })])).toBe(true)
  })

  it("a transcript card still queued stays unborn", () => {
    expect(workspaceBornOf([node("queued", { role: "transcript" })])).toBe(false)
  })

  it("run-time nodes past queued birth the canvas", () => {
    expect(workspaceBornOf([node("queued")])).toBe(false)
    expect(workspaceBornOf([node("running")])).toBe(true)
    expect(workspaceBornOf([node("done")])).toBe(true)
  })
})
