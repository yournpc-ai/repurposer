// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { apiFetch } from "@/lib/api"
import type { VideoStoryboardBlock } from "../timeline/types"
import { StoryboardCard } from "./StoryboardCard"

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn() }))
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }))

const block: VideoStoryboardBlock = {
  kind: "video_storyboard",
  composition_id: "composition",
  composition_version_id: "pinned",
  version: 1,
  content_digest: "saved-content",
  presented_message_id: "original-message",
}
const dto = {
  composition_id: block.composition_id,
  composition_version_id: block.composition_version_id,
  content_digest: block.content_digest,
  presentation_digest: "presented-content",
}
const scrub = { kind: "object", object_id: "title" } as const

afterEach(() => {
  cleanup()
  vi.mocked(apiFetch).mockReset()
})

async function paint() {
  await act(() => new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  ))
}

it.each([
  [{ status: "pending_media" }, "chat.videoStoryboard.pendingMedia"],
  [{ status: "unavailable" }, "chat.videoStoryboard.previewError"],
  [undefined, "chat.videoStoryboard.unavailable"],
] as const)("withholds the presentation receipt when a requested preview cannot play (%j)", async (video_preview, label) => {
  vi.mocked(apiFetch).mockResolvedValueOnce(Response.json({ ...dto, scrub, video_preview }))
  render(<StoryboardCard block={{ ...block, scrub }} messageId="host" prosePresented allowPresentationAck />)
  await screen.findByText(label)
  await paint()
  expect(apiFetch).toHaveBeenCalledTimes(1)
  expect(apiFetch).toHaveBeenCalledWith(
    `/api/v1/chat/video/versions/pinned/storyboard?scrub=${encodeURIComponent(JSON.stringify(scrub))}`,
    { toast: false },
  )
})

it("acknowledges an overview without a requested preview after the prose is visible", async () => {
  vi.mocked(apiFetch).mockResolvedValueOnce(Response.json(dto))
    .mockResolvedValueOnce(Response.json({ accepted: true }))
  const onReady = vi.fn()
  const props = { block, messageId: "host", allowPresentationAck: true, onReady }
  const view = render(<StoryboardCard {...props} prosePresented={false} />)
  await vi.waitFor(() => expect(onReady).toHaveBeenLastCalledWith(true))
  await paint()
  expect(apiFetch).toHaveBeenCalledTimes(1)
  view.rerender(<StoryboardCard {...props} prosePresented />)
  await paint()
  expect(apiFetch).toHaveBeenCalledTimes(2)
  expect(apiFetch).toHaveBeenLastCalledWith("/api/v1/chat/messages/original-message/video-presentation", {
    method: "POST",
    toast: false,
    body: { composition_version_id: "pinned", presentation_digest: dto.presentation_digest },
  })
})
