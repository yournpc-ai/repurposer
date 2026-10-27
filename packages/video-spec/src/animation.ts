/**
 * Keyframe evaluation for video-spec animations (VIDEO_PROJECT §5.1).
 * Pure, zero renderer concepts — the render adapter and the future preview
 * adapter both evaluate through THIS seat, so preview and export cannot
 * drift apart.
 *
 * Frozen evaluation law (§6.5):
 * - keyframes are sorted by `at` (clip-local frames);
 * - before the first keyframe: the first value; after the last: the last
 *   value (constant extrapolation, both ends);
 * - the easing on a keyframe owns the segment FROM it TO the next;
 * - "hold" keeps the segment's FROM value until the next keyframe's frame,
 *   where the value jumps;
 * - cubic_bezier solves x(t) = progress by bisection, then reads y(t).
 */

import type { VideoKeyframe } from "./schema";

type Vec2 = [number, number];
export type AnimValue = number | Vec2;

function isVec2(v: AnimValue): v is Vec2 {
  return Array.isArray(v);
}

function cubicBezierY(x: number, [x1, y1, x2, y2]: [number, number, number, number]): number {
  // Solve x(t) = x by bisection (x(t) is monotone for legal params), then
  // evaluate y(t). 24 iterations pin t well below frame precision.
  let lo = 0;
  let hi = 1;
  let t = x;
  for (let i = 0; i < 24; i++) {
    const cx = 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3;
    if (cx < x) lo = t;
    else hi = t;
    t = (lo + hi) / 2;
  }
  return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3;
}

function interpolate(from: AnimValue, to: AnimValue, p: number): AnimValue {
  if (isVec2(from) && isVec2(to)) {
    return [from[0] + (to[0] - from[0]) * p, from[1] + (to[1] - from[1]) * p];
  }
  if (!isVec2(from) && !isVec2(to)) {
    return from + (to - from) * p;
  }
  throw new Error("keyframe value shapes differ within one animation");
}

/** Evaluate one animation's value at a clip-local frame. */
export function evaluateKeyframes(keyframes: VideoKeyframe[], frame: number): AnimValue {
  if (keyframes.length === 0) throw new Error("an animation needs at least one keyframe");
  const sorted = [...keyframes].sort((a, b) => a.at - b.at);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (frame <= first.at) return first.value;
  if (frame >= last.at) return last.value;
  const idx = sorted.findIndex((k, i) => k.at <= frame && frame < sorted[i + 1].at);
  const from = sorted[idx];
  const to = sorted[idx + 1];
  if (from.easing.kind === "hold") return from.value;
  const span = to.at - from.at;
  const progress = (frame - from.at) / span;
  const eased =
    from.easing.kind === "cubic_bezier"
      ? cubicBezierY(progress, from.easing.params!)
      : progress;
  return interpolate(from.value, to.value, eased);
}

/** Evaluate one (object, property) of a clip's animation list; undefined =
 * no animation governs the property at all (the object's static value). */
export function evaluateProperty(
  animations: {
    target_object_id: string;
    target_text_part_id?: string | null;
    property: string;
    keyframes: VideoKeyframe[];
  }[],
  objectId: string,
  property: string,
  frame: number,
  textPartId: string | null = null,
): AnimValue | undefined {
  const anim = animations.find(
    (a) =>
      a.target_object_id === objectId &&
      (a.target_text_part_id ?? null) === textPartId &&
      a.property === property,
  );
  return anim ? evaluateKeyframes(anim.keyframes, frame) : undefined;
}
