import type { CSSProperties } from "react";
import type { VideoSpec } from "@repurposer/video-spec";
import { easeInOutCubic, lerp } from "./math";

type Transition = NonNullable<VideoSpec["transitions"]>[number];

export function evaluateTransition(kind: Transition["kind"], incoming: boolean, progress: number): CSSProperties {
  const t = easeInOutCubic(progress);
  switch (kind) {
    case "crossfade":
      return incoming ? { opacity: progress } : {};
    case "whip_pan": {
      // Overscan both sides of the moving seam and top/bottom by the blur kernel.
      const velocity = 4 * t * (1 - t);
      return {
        transform: `translateX(${(incoming ? 1 - t : -t) * 100}%) scale(${1 + velocity * 0.08})`,
        filter: `blur(${velocity * 3}px)`,
      };
    }
    case "wipe_reveal":
      return incoming ? { clipPath: `inset(0 ${(1 - t) * 100}% 0 0)` } : {};
    case "zoom_through":
      return incoming
        ? { transform: `scale(${lerp(0.94, 1, t)})`, opacity: t }
        : { transform: `scale(${lerp(1, 1.12, t)})` };
    case "iris_focus": {
      if (!incoming || t === 1) return {};
      if (t === 0) return { opacity: 0 };
      const radius = lerp(-6, 106, t);
      return { maskImage: `radial-gradient(ellipse farthest-corner, black ${radius - 6}%, transparent ${radius + 6}%)` };
    }
  }
}
