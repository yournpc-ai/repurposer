import { describe, expect, it } from "vitest"

import { WaveformDecodeCoordinator } from "./waveformDecode"

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

async function flushTasks() {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

describe("lazy WaveformPlayer decode coordination", () => {
  it("does no download/decode work until the user requests peaks", async () => {
    let calls = 0
    const coordinator = new WaveformDecodeCoordinator(async () => {
      calls += 1
      return [0.5]
    })
    expect(calls).toBe(0)

    const peaks: number[][] = []
    coordinator.request("candidate.mp3", (value) => peaks.push(value))
    await flushTasks()
    expect(calls).toBe(1)
    expect(peaks).toEqual([[0.5]])
  })

  it("keeps one decode lane, aborts stale work, and never writes old results", async () => {
    const first = deferred<number[]>()
    const second = deferred<number[]>()
    const calls: string[] = []
    let firstSignal: AbortSignal | undefined
    const coordinator = new WaveformDecodeCoordinator((src, signal) => {
      calls.push(src)
      if (src === "first.mp3") {
        firstSignal = signal
        return first.promise
      }
      return second.promise
    })
    const received: Array<[string, number[]]> = []
    let firstSettled = 0

    coordinator.request(
      "first.mp3",
      (peaks) => received.push(["first", peaks]),
      () => { firstSettled += 1 },
    )
    coordinator.request("second.mp3", (peaks) => received.push(["second", peaks]))
    expect(firstSignal?.aborted).toBe(true)
    expect(calls).toEqual(["first.mp3"])

    first.resolve([1])
    await flushTasks()
    expect(calls).toEqual(["first.mp3", "second.mp3"])
    expect(received).toEqual([])
    expect(firstSettled).toBe(1)

    second.resolve([0.25, 0.75])
    await flushTasks()
    expect(received).toEqual([["second", [0.25, 0.75]]])
  })

  it("cancels an unmounted attempt and lets its successor start after cleanup", async () => {
    const old = deferred<number[]>()
    const next = deferred<number[]>()
    const calls: string[] = []
    const coordinator = new WaveformDecodeCoordinator((src) => {
      calls.push(src)
      return src === "old.mp3" ? old.promise : next.promise
    })
    const received: number[][] = []

    const cancelOld = coordinator.request("old.mp3", (peaks) => received.push(peaks))
    cancelOld()
    coordinator.request("next.mp3", (peaks) => received.push(peaks))
    old.resolve([1])
    await flushTasks()
    expect(calls).toEqual(["old.mp3", "next.mp3"])
    expect(received).toEqual([])

    next.resolve([0.5])
    await flushTasks()
    expect(received).toEqual([[0.5]])
  })
})
