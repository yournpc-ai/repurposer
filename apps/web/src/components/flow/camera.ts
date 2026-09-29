/** Camera math (Workspace 合同 v4.2 C5 — ensure-in-view) — pure, zero DOM,
 * zero xyflow. The one law this module pins: the delta is a WINDOW shift in
 * world units — positive dx moves the visible window RIGHT (the world
 * appears to slide left), negative LEFT; positive dy DOWN, negative UP.
 * The window's center after the pan is (oldCenter + d), so a target beyond
 * the RIGHT edge needs a POSITIVE dx. Applying the shortfall with the
 * inverted sign pans the camera AWAY from the newborn into empty space —
 * the regression this module's tests exist to catch. */

export interface Bbox {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export interface SafeRect {
  left: number
  top: number
  right: number
  bottom: number
}

/** The minimal pan bringing the target bbox inside the safe region, zoom
 * locked (zoom never auto-changes — C5). {0, 0} = already inside, the beat
 * spends with zero movement. A cluster wider/taller than the safe region
 * can never fully fit at a locked zoom — align its near edge (left / top,
 * the honest best at this zoom). */
export function cameraPanDelta(bbox: Bbox, safe: SafeRect): { dx: number; dy: number } {
  let dx = 0
  if (bbox.minX < safe.left) {
    // Beyond the LEFT edge: shift the window left (negative).
    dx = bbox.minX - safe.left
  } else if (bbox.maxX > safe.right) {
    // Beyond the RIGHT edge: shift the window right (positive). The min()
    // picks the near-edge alignment when the cluster is wider than the
    // safe region (the minimal right-edge shift would push the left edge
    // out).
    dx = Math.min(bbox.maxX - safe.right, bbox.minX - safe.left)
  }
  let dy = 0
  if (bbox.minY < safe.top) {
    dy = bbox.minY - safe.top
  } else if (bbox.maxY > safe.bottom) {
    dy = Math.min(bbox.maxY - safe.bottom, bbox.minY - safe.top)
  }
  return { dx, dy }
}

/** The dock-path cluster gesture (2026-09-30 用户拍板 — 簇可见性 > zoom
 * 守恒, 仅此一扇门): a SINGLE newborn card centers zoom-locked (the 聚焦
 * 新生簇 shape); a MULTI-card cluster gets ONE fit — a dispersed station
 * chain's bbox center at a locked zoom is empty canvas (the island cell +
 * fresh-column rise spread a chain beyond the viewport — 2–4 nodes per
 * plan is the NORM, so the bbox convergence was reliably wrong), and the
 * dock moment's job is reviewing the whole newborn plan. This fit is the
 * ONLY automatic zoom change besides the settle/mount framing — scoped to
 * user-initiated dock arrivals; background beats stay ensure-in-view. Null
 * on an empty cluster (the caller spends the request silently). */
export type ClusterGesture =
  | { kind: "center"; cx: number; cy: number }
  | { kind: "fit"; bounds: Bbox }

export function clusterGesture(
  frames: { x: number; y: number; w: number; h: number }[],
): ClusterGesture | null {
  if (frames.length === 0) return null
  if (frames.length === 1) {
    const f = frames[0]
    return { kind: "center", cx: f.x + f.w / 2, cy: f.y + f.h / 2 }
  }
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const f of frames) {
    minX = Math.min(minX, f.x)
    minY = Math.min(minY, f.y)
    maxX = Math.max(maxX, f.x + f.w)
    maxY = Math.max(maxY, f.y + f.h)
  }
  return { kind: "fit", bounds: { minX, minY, maxX, maxY } }
}
