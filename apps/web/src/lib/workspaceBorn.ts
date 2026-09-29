/** workspaceBorn predicate (Workspace 合同 v4.2 C3) — the desktop world's
 * flip condition is an INDEPENDENT presentation predicate: the first
 * non-Source workspace entity exists in the graph PAST its placeholder
 * face. 内容到达才出生 — the canvas arrives WITH the content.
 *
 * Reads the graph frame's node states; three facts stay separated: graph
 * entity existence (data truth since upload), this predicate
 * (presentation), and PLAN_READY (lifecycle projection, lifecycleStamp.ts).
 *
 * Per-face law:
 * - Source (asset) nodes NEVER count — read off the joined asset dossier
 *   (the server joins it only onto ORM type="asset" rows).
 * - Draft plan chains (K5) count — "draft" is the docked plan's face, the
 *   canvas is born with the whole chain visible.
 * - Run-time nodes count once past queued — they only exist once the world
 *   is alive (a run requires a docked plan, which already flipped birth).
 * - The upload-born transcript card is the ONE exception to the coarse
 *   state read: it is born `running` (its queued birth face is retired —
 *   the shared wipe + edge packet ride `running`) with no content yet, and
 *   it must NOT birth the canvas at the send beat. Its "past the
 *   placeholder" moment is the TERMINAL face — done / failed, the truth in
 *   hand (a failed card's red face is also the truth). Reading its coarse
 *   state instead fires the birth at the send beat — the drift this
 *   predicate pins. */

import type { GraphNode } from "./types"

export function workspaceBornOf(
  nodes: Pick<GraphNode, "asset" | "state" | "spec">[] | null | undefined,
): boolean {
  return (
    nodes?.some((n) => {
      if (n.asset != null) return false
      if (n.spec?.role === "transcript") {
        return n.state === "done" || n.state === "failed"
      }
      return n.state !== "queued"
    }) ?? false
  )
}
