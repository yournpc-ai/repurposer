import type { Output } from "@/lib/types"

/** The Output's declared display ratio. Unknown frames keep the existing
 * media-family fallback; consumers never probe the file just to lay it out. */
export function outputAspect(output: Output): number {
  const spec = output.render_spec as { aspect?: string; width?: number; height?: number } | null
  const declared = output.aspect ?? spec?.aspect
  const match = declared?.match(/^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/)
  if (match) {
    const width = Number(match[1])
    const height = Number(match[2])
    if (width > 0 && height > 0) return width / height
  }
  if (spec?.width && spec.height && spec.width > 0 && spec.height > 0) {
    return spec.width / spec.height
  }
  return output.type === "clip" || output.type === "film" || output.type === "video" ? 16 / 9 : 4 / 3
}
