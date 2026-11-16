import { useCallback, useEffect, useRef, useState } from "react"
import { Player, type PlayerRef } from "@remotion/player"
import { Video } from "@repurposer/video-remotion"
import type { VideoSpec } from "@repurposer/video-spec"

function FirstFrameSignal({
  playerRef,
  fontsReady,
  onReady,
  onError,
}: {
  playerRef: React.RefObject<PlayerRef | null>
  fontsReady: boolean
  onReady: () => void
  onError: () => void
}) {
  useEffect(() => {
    if (!fontsReady) return
    let frame: number | undefined
    const waitForFirstFrame = () => {
      const container = playerRef.current?.getContainerNode()
      if (!container) {
        frame = requestAnimationFrame(waitForFirstFrame)
        return
      }
      const elements = Array.from(container.querySelectorAll("img,video,audio"))
      const failed = elements.some((element) =>
        element instanceof HTMLImageElement
          ? element.hasAttribute("src") && element.complete && element.naturalWidth === 0
          : element instanceof HTMLMediaElement && element.error !== null,
      )
      if (failed) {
        onError()
        return
      }
      const pending = elements.some((element) => {
        if (element instanceof HTMLImageElement) {
          return element.hasAttribute("src") && (!element.complete || element.naturalWidth === 0)
        }
        if (element instanceof HTMLMediaElement) {
          const source = element.currentSrc || element.getAttribute("src")
          return Boolean(source) && element.readyState < HTMLMediaElement.HAVE_METADATA
        }
        return false
      })
      if (pending) {
        frame = requestAnimationFrame(waitForFirstFrame)
        return
      }
      // The current Player's fonts and first-frame media are ready; allow one
      // browser paint before the outer presentation ACK gate.
      frame = requestAnimationFrame(onReady)
    }
    frame = requestAnimationFrame(waitForFirstFrame)
    return () => {
      if (frame !== undefined) cancelAnimationFrame(frame)
    }
  }, [fontsReady, onError, onReady, playerRef])
  return null
}

function PreviewComposition({
  spec,
  playerRef,
  onReady,
  onError,
}: {
  spec: VideoSpec
  playerRef: React.RefObject<PlayerRef | null>
  onReady: () => void
  onError: () => void
}) {
  const digest = spec.provenance.content_digest
  const [fontsReadyDigest, setFontsReadyDigest] = useState<string | null>(null)
  const onFontsReady = useCallback(() => setFontsReadyDigest(digest), [digest])
  return (
    <>
      <Video
        key={digest}
        spec={spec}
        onFontsReady={onFontsReady}
        onFontsError={onError}
      />
      <FirstFrameSignal
        playerRef={playerRef}
        fontsReady={fontsReadyDigest === digest}
        onReady={onReady}
        onError={onError}
      />
    </>
  )
}

function PlayerFailure({ onError }: { onError: () => void }) {
  useEffect(() => onError(), [onError])
  return null
}

/** The only Chat-side Remotion Player seat. The pure video-spec package stays
 * renderer-neutral; this adapter consumes the shared Remotion composition. */
export function RemotionPreviewAdapter({
  spec,
  onReady,
  onError,
}: {
  spec: VideoSpec
  onReady: () => void
  onError: () => void
}) {
  const playerRef = useRef<PlayerRef>(null)
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  useEffect(() => {
    if (!mounted) return
    const player = playerRef.current
    if (!player) return
    const handleError = () => onError()
    player.addEventListener("error", handleError)
    return () => player.removeEventListener("error", handleError)
  }, [mounted, onError])

  if (!mounted) return (
    <div
      className="w-full rounded-md bg-muted"
      style={{ aspectRatio: `${spec.width} / ${spec.height}` }}
    />
  )
  return (
    <Player
      ref={playerRef}
      component={PreviewComposition}
      inputProps={{ spec, playerRef, onReady, onError }}
      durationInFrames={spec.duration_frames}
      fps={spec.fps.num / spec.fps.den}
      compositionWidth={spec.width}
      compositionHeight={spec.height}
      style={{ width: "100%" }}
      className="w-full overflow-hidden rounded-md bg-muted"
      controls
      loop
      numberOfSharedAudioTags={0}
      errorFallback={({ error }: { error: Error }) => {
        void error
        return <PlayerFailure onError={onError} />
      }}
    />
  )
}
