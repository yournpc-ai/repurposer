"use client"

import { useEffect, useMemo, useState } from "react"
import { Player } from "@remotion/player"
import { Video } from "@repurposer/video-remotion"
import { videoSpecSchema, type VideoSpec } from "@repurposer/video-spec"

function WorkbenchComposition({ spec }: { spec: VideoSpec }) {
  return <Video key={spec.provenance.content_digest} spec={spec} />
}

export function WorkbenchDraftPlayer({
  rawSpec,
}: {
  rawSpec: unknown
}) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const spec = useMemo(() => {
    const parsed = videoSpecSchema.safeParse(rawSpec)
    return parsed.success ? parsed.data : null
  }, [rawSpec])

  if (!spec) return null

  const fps = spec.fps.num / spec.fps.den
  const aspect = `${spec.width} / ${spec.height}`

  if (!mounted) {
    return (
      <div
        className="w-full rounded-lg bg-muted"
        style={{ aspectRatio: aspect }}
      />
    )
  }

  return (
    <div
      className="w-full overflow-hidden rounded-lg border border-border bg-black/90"
      style={{ aspectRatio: aspect }}
    >
      <Player
        key={spec.provenance.content_digest}
        component={WorkbenchComposition}
        inputProps={{ spec }}
        durationInFrames={spec.duration_frames}
        fps={fps}
        initialFrame={Math.min(
          Math.round(fps * 1.5),
          Math.max(0, spec.duration_frames - 1),
        )}
        compositionWidth={spec.width}
        compositionHeight={spec.height}
        style={{ width: "100%", height: "100%" }}
        className="h-full w-full"
        controls
        loop
        numberOfSharedAudioTags={0}
      />
    </div>
  )
}
