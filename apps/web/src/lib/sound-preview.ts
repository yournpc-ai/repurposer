import { synthesizeSound, type SoundTune } from "@repurposer/sound-engine"

let sharedCtx: AudioContext | null = null

/**
 * Deterministic client-side Web Audio audition using the exact same
 * @repurposer/sound-engine math that runs on the render server.
 */
interface PreviewInput {
  recipeId: string
  tune?: SoundTune
  params?: Record<string, number>
  seed?: number
}

export function startSoundPreview(context: AudioContext, input: PreviewInput): AudioBufferSourceNode {
  const { left, right, sampleRate } = synthesizeSound(input)
  const buffer = context.createBuffer(2, left.length, sampleRate)
  buffer.getChannelData(0).set(left)
  buffer.getChannelData(1).set(right)
  const source = context.createBufferSource()
  source.buffer = buffer
  source.connect(context.destination)
  source.start()
  return source
}

export async function playSoundRecipePreview(input: PreviewInput): Promise<void> {
  if (typeof window === "undefined") return
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioCtx) return
  if (!sharedCtx || sharedCtx.state === "closed") {
    sharedCtx = new AudioCtx()
  }
  if (sharedCtx.state === "suspended") {
    await sharedCtx.resume()
  }
  startSoundPreview(sharedCtx, input)
}
