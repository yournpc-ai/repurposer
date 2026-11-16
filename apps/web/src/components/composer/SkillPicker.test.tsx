// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"

import { fetchChatSkills, type SkillOption } from "@/lib/skills"
import { SkillPicker } from "./SkillPicker"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "skills.builtin.promo-video.name": "Promotional video",
        "skills.builtin.promo-video.description": "Create a promotional video",
      })[key] ?? key,
  }),
}))

vi.mock("@/lib/skills", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/skills")>()
  return { ...actual, fetchChatSkills: vi.fn() }
})

const option: SkillOption = {
  reference: { kind: "builtin", skill_id: "promo-video", version: "1.0.0" },
  skill_id: "promo-video",
  name: "promo-video",
  description: "Create a promotional video",
  capabilities: [],
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

async function renderPicker(position: { left: number; top: number; bottom: number }) {
  vi.mocked(fetchChatSkills).mockResolvedValue({ items: [option] })
  render(
    <SkillPicker
      query=""
      position={position}
      onSelect={vi.fn()}
      onClose={vi.fn()}
    />,
  )
  const name = await screen.findByText("Promotional video")
  const button = name.closest("button") as HTMLButtonElement
  return { button, popup: button.closest(".overlay-surface") as HTMLElement }
}

it("opens below the caret when space allows and omits the slash from catalog names", async () => {
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 1000 })
  const { button, popup } = await renderPicker({ left: 120, top: 400, bottom: 424 })

  expect(button.textContent?.startsWith("Promotional video")).toBe(true)
  expect(button.textContent?.startsWith("/")).toBe(false)
  expect(popup.style.left).toBe("120px")
  expect(popup.style.top).toBe("428px")
  expect(popup.style.transform).toBe("")
})

it("opens upward only when the space below cannot fit the picker", async () => {
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 })
  const { popup } = await renderPicker({ left: 120, top: 700, bottom: 724 })

  expect(popup.style.top).toBe("700px")
  expect(popup.style.transform).toBe("translateY(calc(-100% - 4px))")
})
