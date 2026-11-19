// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { apiGet } from "@/lib/api"
import type { AudioPlaybackBlock } from "../timeline/types"
import { AudioPlaybackSurface } from "./AudioPlaybackSurface"

vi.mock("@/lib/api", () => ({ apiGet: vi.fn() }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

class TestAudio extends EventTarget {
  static instances: TestAudio[] = []
  src = ""
  currentTime = 0
  duration = 3
  constructor() { super(); TestAudio.instances.push(this) }
  async play() { this.dispatchEvent(new Event("play")) }
  pause() { this.dispatchEvent(new Event("pause")) }
}
const item = {
  role: "narration" as const, snapshot_id: "same-audio", digest: "same-digest",
  scene_id: "opening", scene_label: "Opening", title: "A line", duration_seconds: 3,
  peaks: [0.25, 0.75], analysis_digest: "analysis",
}
const block: AudioPlaybackBlock = {
  kind: "audio_playback", project_id: "project",
  items: [item, { ...item, scene_id: "ending", scene_label: "Ending" }],
}
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.mocked(apiGet).mockReset()
  TestAudio.instances = []
})
function sign(url: string, digest = item.digest) {
  vi.mocked(apiGet).mockResolvedValueOnce(Response.json({ url, digest, snapshot_id: item.snapshot_id, expires_in: 300 }))
}
async function click(name: string) {
  await act(async () => { fireEvent.click(screen.getAllByRole("button", { name })[0]) })
}

it("shows both uses of one fixed audio and renews an expired link on the next play", async () => {
  vi.stubGlobal("Audio", TestAudio)
  const clock = vi.spyOn(Date, "now").mockReturnValue(1000)
  sign("https://example.test/audio?first")
  sign("https://example.test/audio?next")
  const view = render(<AudioPlaybackSurface block={block} />)
  expect(screen.getByText("Opening")).toBeDefined()
  expect(screen.getByText("Ending")).toBeDefined()
  expect(view.container.querySelector('span[style="height: 21px;"]')).toBeTruthy()
  expect(apiGet).not.toHaveBeenCalled()

  await click("chat.audio.play")
  expect(apiGet).toHaveBeenCalledWith("/api/v1/projects/project/audio/same-audio/playback", { toast: false })
  const audio = TestAudio.instances[0]
  expect(audio.src).toBe("https://example.test/audio?first")
  audio.currentTime = 1.5
  await click("chat.audio.pause")
  clock.mockReturnValue(311000)
  await click("chat.audio.play")
  expect(audio.src).toBe("https://example.test/audio?next")
  expect(audio.currentTime).toBe(1.5)
  expect(apiGet).toHaveBeenCalledTimes(2)
})

it("rejects mismatched bytes, retries on demand, and recovers transport failure", async () => {
  vi.stubGlobal("Audio", TestAudio)
  sign("https://example.test/wrong", "wrong-digest")
  sign("https://example.test/fixed")
  sign("https://example.test/refreshed")
  render(<AudioPlaybackSurface block={{ ...block, items: [item] }} />)
  await click("chat.audio.play")
  const audio = TestAudio.instances[0]
  expect(audio.src).toBe("")
  expect(screen.getByText("chat.audio.unavailable")).toBeDefined()
  await click("chat.audio.retry")
  expect(audio.src).toBe("https://example.test/fixed")
  act(() => { audio.dispatchEvent(new Event("error")) })
  await click("chat.audio.retry")
  expect(audio.src).toBe("https://example.test/refreshed")
  expect(screen.getByRole("button", { name: "chat.audio.pause" })).toBeDefined()
})

it("reports a legacy playback receipt with missing measurements", () => {
  render(<AudioPlaybackSurface block={{ ...block, items: [{ ...item, peaks: [] }] }} />)
  expect(screen.queryByRole("button", { name: "chat.audio.play" })).toBeNull()
  expect(screen.getByText("chat.audio.unavailable")).toBeDefined()
  expect(apiGet).not.toHaveBeenCalled()
})
