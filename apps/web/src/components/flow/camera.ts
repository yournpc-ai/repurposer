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

/** The bbox center of a frame cluster in world coords — the 「聚焦新生簇」
 * target point (2026-09-29 用户拍板): the same centering math fitView uses
 * for 适应窗口, minus the zoom change (zoom never auto-changes — C5). Null
 * on an empty cluster (the caller spends the request silently). */
export function framesBBoxCenter(
  frames: { x: number; y: number; w: number; h: number }[],
): { cx: number; cy: number } | null {
  if (frames.length === 0) return null
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
  return { cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 }
}
