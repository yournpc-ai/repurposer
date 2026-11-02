// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { WaveformPlayer } from "./WaveformPlayer"

const { animateMock } = vi.hoisted(() => ({
  animateMock: vi.fn(() => ({ stop: vi.fn() })),
}))

vi.mock("motion/react", async (importOriginal) => ({
  ...await importOriginal<typeof import("motion/react")>(),
  animate: animateMock,
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

class MetadataAudio {
  static instances: MetadataAudio[] = []
  preload = ""
  src = ""
  currentTime = 0
  duration = 3.2
  private listeners = new Map<string, Set<() => void>>()

  constructor() {
    MetadataAudio.instances.push(this)
  }

  addEventListener(name: string, listener: () => void) {
    this.listeners.set(name, (this.listeners.get(name) ?? new Set()).add(listener))
  }

  removeEventListener(name: string, listener: () => void) {
    this.listeners.get(name)?.delete(listener)
  }

  emit(name: string) {
    for (const listener of this.listeners.get(name) ?? []) listener()
  }

  play = vi.fn(async () => {
    this.emit("play")
  })

  pause = vi.fn(() => {
    this.emit("pause")
  })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  animateMock.mockClear()
  MetadataAudio.instances = []
})

function player(src = "https://cdn.freesound.org/previews/candidate.mp3") {
  return render(<WaveformPlayer src={src} durationSeconds={3.2} waveformKey={src} />)
}

describe("WaveformPlayer real-audio transport", () => {
  it("loads only metadata and never downloads or decodes PCM for its bars", () => {
    const fetchMock = vi.fn()
    const decodeMock = vi.fn()
    vi.stubGlobal("Audio", MetadataAudio)
    vi.stubGlobal("fetch", fetchMock)
    vi.stubGlobal("AudioContext", vi.fn(() => ({
      decodeAudioData: decodeMock,
      close: vi.fn(async () => {}),
    })))

    const { unmount } = player()
    expect(MetadataAudio.instances).toHaveLength(1)
    expect(MetadataAudio.instances[0].preload).toBe("metadata")
    expect(fetchMock).not.toHaveBeenCalled()
    expect(decodeMock).not.toHaveBeenCalled()

    unmount()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(decodeMock).not.toHaveBeenCalled()
  })

  it("drives play, pause, seek, ended and replay from the real audio element", () => {
    vi.stubGlobal("Audio", MetadataAudio)
    player()
    const audio = MetadataAudio.instances[0]

    fireEvent.click(screen.getByRole("button", { name: "chat.sfx.play" }))
    expect(audio.play).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole("button", { name: "chat.sfx.pause" }))
    expect(audio.pause).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole("button", { name: "chat.sfx.play" }))
    fireEvent.change(screen.getByRole("slider", { name: "chat.sfx.seek" }), {
      target: { value: "1.25" },
    })
    expect(audio.currentTime).toBe(1.25)
    expect(screen.getByText("0:01")).toBeTruthy()

    act(() => {
      audio.currentTime = audio.duration
      audio.emit("ended")
    })
    expect(audio.currentTime).toBe(3.2)
    expect(screen.getByRole("button", { name: "chat.sfx.play" })).toBeTruthy()
    expect(screen.getByText("0:03")).toBeTruthy()

    fireEvent.click(screen.getByRole("button", { name: "chat.sfx.play" }))
    expect(audio.currentTime).toBe(0)
    expect(audio.play).toHaveBeenCalledTimes(3)
  })

  it("pauses the previously playing candidate", () => {
    vi.stubGlobal("Audio", MetadataAudio)
    render(
      <>
        <WaveformPlayer src="first.mp3" durationSeconds={3.2} waveformKey="first" />
        <WaveformPlayer src="second.mp3" durationSeconds={2} waveformKey="second" />
      </>,
    )
    const [first, second] = MetadataAudio.instances
    const playButtons = screen.getAllByRole("button", { name: "chat.sfx.play" })
    fireEvent.click(playButtons[0])
    fireEvent.click(playButtons[1])

    expect(first.pause).toHaveBeenCalledTimes(1)
    expect(second.play).toHaveBeenCalledTimes(1)
    expect(screen.getAllByRole("button", { name: "chat.sfx.pause" })).toHaveLength(1)
  })

  it("keeps error state unavailable and disables transport", () => {
    vi.stubGlobal("Audio", MetadataAudio)
    player()
    const audio = MetadataAudio.instances[0]
    act(() => audio.emit("error"))

    expect((screen.getByRole("button", { name: "chat.sfx.play" }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole("slider", { name: "chat.sfx.seek" }) as HTMLInputElement).disabled).toBe(true)
    expect(screen.getByText("chat.sfx.previewUnavailable")).toBeTruthy()
  })

  it("uses zero-duration visual transitions under reduced motion", () => {
    vi.stubGlobal("Audio", MetadataAudio)
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })))
    animateMock.mockClear()
    player()

    expect(animateMock).toHaveBeenCalledWith(
      expect.anything(),
      0,
      expect.objectContaining({ duration: 0 }),
    )
  })
})
