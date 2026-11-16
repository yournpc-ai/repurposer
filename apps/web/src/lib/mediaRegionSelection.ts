export interface PixelSize {
  width: number
  height: number
}

export interface PixelRect extends PixelSize {
  x: number
  y: number
}

/** A frame-accurate spatial reference captured in the Output viewer.
 *
 * `sourceRect` addresses the video's intrinsic pixels; `normalizedRect` is
 * resolution-independent; `viewportRect` records the CSS-pixel drag geometry
 * at capture time. `mediaTimeMs` identifies the paused source frame.
 */
export interface MediaRegionSelection {
  coordinateSpace: "source_pixels"
  mediaTimeMs: number
  sourceSize: PixelSize
  sourceRect: PixelRect
  normalizedRect: PixelRect
  viewportRect: PixelRect
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value))

/** The actual object-contain content box inside a media element. */
export function videoContentRect(container: PixelSize, source: PixelSize): PixelRect {
  if (container.width <= 0 || container.height <= 0 || source.width <= 0 || source.height <= 0) {
    return { x: 0, y: 0, width: 0, height: 0 }
  }
  const scale = Math.min(container.width / source.width, container.height / source.height)
  const width = Math.min(container.width, source.width * scale)
  const height = Math.min(container.height, source.height * scale)
  return {
    x: clamp((container.width - width) / 2, 0, container.width - width),
    y: clamp((container.height - height) / 2, 0, container.height - height),
    width,
    height,
  }
}

/** Convert one displayed drag rectangle into intrinsic and normalized pixels. */
export function makeMediaRegionSelection({
  viewportRect,
  viewportSize,
  sourceSize,
  mediaTimeSeconds,
}: {
  viewportRect: PixelRect
  viewportSize: PixelSize
  sourceSize: PixelSize
  mediaTimeSeconds: number
}): MediaRegionSelection {
  const left = clamp(viewportRect.x, 0, viewportSize.width)
  const top = clamp(viewportRect.y, 0, viewportSize.height)
  const right = clamp(viewportRect.x + viewportRect.width, left, viewportSize.width)
  const bottom = clamp(viewportRect.y + viewportRect.height, top, viewportSize.height)
  const boundedViewport = { x: left, y: top, width: right - left, height: bottom - top }
  const normalizedRect = {
    x: viewportSize.width > 0 ? left / viewportSize.width : 0,
    y: viewportSize.height > 0 ? top / viewportSize.height : 0,
    width: viewportSize.width > 0 ? boundedViewport.width / viewportSize.width : 0,
    height: viewportSize.height > 0 ? boundedViewport.height / viewportSize.height : 0,
  }
  const sourceLeft = clamp(Math.floor(normalizedRect.x * sourceSize.width), 0, sourceSize.width)
  const sourceTop = clamp(Math.floor(normalizedRect.y * sourceSize.height), 0, sourceSize.height)
  const sourceRight = clamp(
    Math.ceil((normalizedRect.x + normalizedRect.width) * sourceSize.width),
    sourceLeft,
    sourceSize.width,
  )
  const sourceBottom = clamp(
    Math.ceil((normalizedRect.y + normalizedRect.height) * sourceSize.height),
    sourceTop,
    sourceSize.height,
  )
  return {
    coordinateSpace: "source_pixels",
    mediaTimeMs: Math.max(0, Math.round(mediaTimeSeconds * 1000)),
    sourceSize: { ...sourceSize },
    sourceRect: {
      x: sourceLeft,
      y: sourceTop,
      width: sourceRight - sourceLeft,
      height: sourceBottom - sourceTop,
    },
    normalizedRect,
    viewportRect: boundedViewport,
  }
}

export function formatMediaTimeMs(value: number): string {
  const total = Math.max(0, Math.round(value))
  const hours = Math.floor(total / 3_600_000)
  const minutes = Math.floor(total / 60_000) % 60
  const seconds = Math.floor(total / 1000) % 60
  const milliseconds = total % 1000
  const prefix = hours > 0 ? `${String(hours).padStart(2, "0")}:` : ""
  return `${prefix}${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`
}
