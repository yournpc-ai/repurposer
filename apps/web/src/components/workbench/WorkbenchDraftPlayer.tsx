"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Player, type PlayerRef } from "@remotion/player"
import { Video } from "@repurposer/video-remotion"
import { videoSpecSchema, type VideoSpec } from "@repurposer/video-spec"

function WorkbenchComposition({ spec }: { spec: VideoSpec }) {
  return <Video key={spec.provenance.content_digest} spec={spec} />
}

export function WorkbenchDraftPlayer({
  rawSpec,
  windowStartSeconds = 0,
  seekRequest,
  onTimeSecondsChange,
}: {
  rawSpec: unknown
  /** Start offset (in composition seconds) of this bounded scrub spec. */
  windowStartSeconds?: number
  /** Increment `nonce` to seek the player to a local frame offset (seconds relative to windowStartSeconds). */
  seekRequest?: { localSeconds: number; nonce: number } | null
  /** Reports live composition time (windowStartSeconds + local player time). */
  onTimeSecondsChange?: (compositionSeconds: number) => void
}) {
  const [mounted, setMounted] = useState(false)
  const playerRef = useRef<PlayerRef>(null)
  useEffect(() => setMounted(true), [])

  const spec = useMemo(() => {
    const parsed = videoSpecSchema.safeParse(rawSpec)
    return parsed.success ? parsed.data : null
  }, [rawSpec])

  const fps = spec ? spec.fps.num / spec.fps.den : 30

  useEffect(() => {
    if (!mounted || !spec || !seekRequest) return
    const player = playerRef.current
    if (!player) return
    const targetFrame = Math.max(
      0,
      Math.min(spec.duration_frames - 1, Math.round(seekRequest.localSeconds * fps)),
    )
    player.seekTo(targetFrame)
  }, [mounted, spec, fps, seekRequest])

  useEffect(() => {
    if (!mounted || !spec || !onTimeSecondsChange) return
    const player = playerRef.current
    if (!player) return
    const handleFrameUpdate = (e: { detail: { frame: number } }) => {
      onTimeSecondsChange(windowStartSeconds + e.detail.frame / fps)
    }
    player.addEventListener("frameupdate", handleFrameUpdate)
    return () => {
      player.removeEventListener("frameupdate", handleFrameUpdate)
    }
  }, [mounted, spec, fps, windowStartSeconds, onTimeSecondsChange])

  if (!spec) return null

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
      className="w-full overflow-hidden rounded-lg border border-subtle bg-black/95"
      style={{ aspectRatio: aspect }}
    >
      <Player
        ref={playerRef}
        key={spec.provenance.content_digest}
        component={WorkbenchComposition}
        inputProps={{ spec }}
        durationInFrames={spec.duration_frames}
        fps={fps}
        initialFrame={Math.min(
          Math.round(fps * 0.5),
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
