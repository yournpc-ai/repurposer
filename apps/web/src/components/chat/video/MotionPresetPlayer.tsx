import { useEffect, useRef, useState } from "react"
import { Player, type PlayerRef } from "@remotion/player"
import { Video } from "@repurposer/video-remotion"
import type { VideoSpec } from "@repurposer/video-spec"
import { Pause, Play } from "@/components/ui/icons"
import { useTranslation } from "react-i18next"

export default function MotionPresetPlayer({ spec, title }: { spec: VideoSpec; title: string }) {
  const ref = useRef<PlayerRef>(null)
  const [playing, setPlaying] = useState(false)
  const { t } = useTranslation()
  useEffect(() => {
    const player = ref.current
    if (!player) return
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    player.addEventListener("play", onPlay)
    player.addEventListener("pause", onPause)
    return () => {
      player.removeEventListener("play", onPlay)
      player.removeEventListener("pause", onPause)
    }
  }, [])
  return <>
    <Player ref={ref} component={Video} inputProps={{ spec }} durationInFrames={spec.duration_frames}
      fps={spec.fps.num / spec.fps.den} compositionWidth={spec.width} compositionHeight={spec.height}
      className={spec.style ? undefined : "grayscale"} style={{ width: "100%" }} loop initiallyMuted acknowledgeRemotionLicense numberOfSharedAudioTags={0}
      errorFallback={() => <span>{t("chat.candidates.presetUnavailable")}</span>} />
    <button type="button" aria-label={t(playing ? "chat.candidates.pausePreset" : "chat.candidates.playPreset", { title })}
      onClick={() => {
        const player = ref.current
        if (!player) return
        if (player.isPlaying()) player.pause()
        else player.play()
      }}
      className="absolute inset-0 flex items-end justify-end p-2 focus-visible:outline-2 focus-visible:outline-offset-[-2px]">
      <span className="grid size-8 place-items-center rounded-full border border-subtle bg-card text-foreground">
        {playing ? <Pause size={14} /> : <Play size={14} />}
      </span>
    </button>
  </>
}
