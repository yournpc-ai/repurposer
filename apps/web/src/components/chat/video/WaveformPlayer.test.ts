import { describe, expect, it } from "vitest"

import { deterministicWaveform } from "./WaveformPlayer"

describe("WaveformPlayer deterministic voice bars", () => {
  it("keeps one candidate silhouette stable across live, history and remounts", () => {
    const identity = "candidate-set-1:833628:1"
    const live = deterministicWaveform(identity)
    deterministicWaveform("another-candidate:528561:0")
    const replayed = deterministicWaveform(identity)
    const remounted = deterministicWaveform(identity)

    expect(live).toHaveLength(48)
    expect(replayed).toEqual(live)
    expect(remounted).toEqual(live)
    expect(live.every((peak) => peak >= 0.18 && peak <= 1)).toBe(true)
  })

  it("uses candidate identity rather than a random or playback-time seed", () => {
    const first = deterministicWaveform("candidate-a")
    const second = deterministicWaveform("candidate-b")
    expect(second).not.toEqual(first)
    expect(deterministicWaveform("candidate-a", 12)).toHaveLength(12)
    expect(deterministicWaveform("candidate-a", 0)).toEqual([])
  })
})
