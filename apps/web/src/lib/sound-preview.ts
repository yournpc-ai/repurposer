import { synthesizeSound } from "@repurposer/sound-engine"

let sharedCtx: AudioContext | null = null

/**
 * Deterministic client-side Web Audio audition using the exact same
 * @repurposer/sound-engine math that runs on the render server.
 */
export async function playSoundRecipePreview(input: {
  recipeId: string
  params?: Record<string, number>
  seed?: number
}): Promise<void> {
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
  const { left, right, sampleRate } = synthesizeSound(input)
  const buffer = sharedCtx.createBuffer(2, left.length, sampleRate)
  buffer.copyToChannel(new Float32Array(left), 0)
  buffer.copyToChannel(new Float32Array(right), 1)
  const source = sharedCtx.createBufferSource()
  source.buffer = buffer
  source.connect(sharedCtx.destination)
  source.start()
}
