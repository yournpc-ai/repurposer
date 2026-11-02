export type WaveformPeakDecoder = (
  src: string,
  signal: AbortSignal,
) => Promise<number[]>

type DecodeTask = {
  cancelled: boolean
  controller: AbortController
  done: Promise<void>
}

/** One process-wide lazy decode lane. A new candidate invalidates the old
 * task immediately, but waits for its non-cancellable decoder to settle so
 * two MP3 decodes never consume CPU/memory together. */
export class WaveformDecodeCoordinator {
  private current: DecodeTask | null = null

  constructor(private readonly decode: WaveformPeakDecoder) {}

  request(
    src: string,
    onPeaks: (peaks: number[]) => void,
    onSettled?: () => void,
  ): () => void {
    const previous = this.current
    if (previous) {
      previous.cancelled = true
      previous.controller.abort()
    }
    const task: DecodeTask = {
      cancelled: false,
      controller: new AbortController(),
      done: Promise.resolve(),
    }
    this.current = task
    task.done = (async () => {
      try {
        if (previous) await previous.done
        if (task.cancelled) return
        const peaks = await this.decode(src, task.controller.signal)
        if (!task.cancelled && this.current === task) onPeaks(peaks)
      } catch {
        // CORS, abort and decode failures leave the honest progress track.
      } finally {
        if (this.current === task) this.current = null
        onSettled?.()
      }
    })()
    return () => {
      task.cancelled = true
      task.controller.abort()
    }
  }
}
