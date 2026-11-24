// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"

import { fetchChatSkills, type SkillOption } from "@/lib/skills"
import { SkillPicker } from "./SkillPicker"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (key === "skills.picker.blueprintMeta" && params) {
        return `${params.acts} acts · ${params.slots} slots`
      }
      return (
        {
          "skills.builtin.promo-video.name": "Promotional video",
          "skills.builtin.promo-video.description": "Create a promotional video",
          "skills.builtin.text-animation.name": "Kinetic Text",
          "skills.builtin.text-animation.description": "Beat-led kinetic typography",
          "skills.picker.creationModes": "Creation Modes",
          "skills.picker.templates": "Templates",
          "skills.picker.styles.vox_editorial": "Vox",
          "skills.slotPreview.openAction": "Preview numbered slot promo",
        }[key] ?? key
      )
    },
  }),
}))

vi.mock("@/lib/skills", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/skills")>()
  return { ...actual, fetchChatSkills: vi.fn() }
})

const builtinOption: SkillOption = {
  reference: { kind: "builtin", skill_id: "promo-video", version: "1.0.0" },
  skill_id: "promo-video",
  name: "promo-video",
  description: "Create a promotional video",
  capabilities: [],
}

const textBuiltinOption: SkillOption = {
  reference: { kind: "builtin", skill_id: "text-animation", version: "1.0.0" },
  skill_id: "text-animation",
  name: "text-animation",
  description: "Beat-led kinetic typography",
  capabilities: ["native_motion_graphics", "beat_led_typography", "text_style_presets"],
}

const templateOption: SkillOption = {
  reference: {
    kind: "external",
    skill_version_id: "11111111-2222-3333-4444-555555555555",
  },
  skill_id: "saas-launch-template",
  name: "SaaS Launch Template",
  description: "6-act product launch blueprint",
  capabilities: ["slot_blueprint_v1"],
  version_number: 2,
  blueprint_summary: {
    act_count: 6,
    slot_count: 14,
    duration_s: 32.5,
    style_preset: "vox_editorial",
  },
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

async function renderPicker(
  position: { left: number; top: number; bottom: number },
  items: SkillOption[] = [builtinOption],
  opts: {
    onSelect?: (option: SkillOption) => void
    onPreviewSlotPromo?: (option: SkillOption) => void
  } = {},
) {
  vi.mocked(fetchChatSkills).mockResolvedValue({ items })
  const onSelect = opts.onSelect ?? vi.fn()
  render(
    <SkillPicker
      query=""
      position={position}
      onSelect={onSelect}
      onClose={vi.fn()}
      onPreviewSlotPromo={opts.onPreviewSlotPromo}
    />,
  )
  const name = await screen.findByText("Promotional video")
  const button = name.closest("button") as HTMLButtonElement
  return { button, popup: button.closest(".ui-crdc") as HTMLElement, onSelect }
}

it("opens below the caret when space allows and omits the slash from catalog names", async () => {
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 1000 })
  const { button, popup } = await renderPicker({ left: 120, top: 400, bottom: 424 })

  expect(button.textContent?.startsWith("Promotional video")).toBe(true)
  expect(button.textContent?.startsWith("/")).toBe(false)
  expect(popup.style.left).toBe("120px")
  expect(popup.style.top).toBe("428px")
  expect(popup.style.transform).toBe("")
  expect(screen.getByText("Creation Modes")).toBeTruthy()
  expect(screen.queryByText("Templates")).toBeNull()
})

it("opens upward only when the space below cannot fit the picker", async () => {
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 })
  const { popup } = await renderPicker({ left: 120, top: 700, bottom: 724 })

  expect(popup.style.top).toBe("700px")
  expect(popup.style.transform).toBe("translateY(calc(-100% - 4px))")
})

it("renders two sections with metadata, flat keyboard navigation, and non-bubbling slot preview trigger", async () => {
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 1000 })
  const onSelect = vi.fn()
  const onPreviewSlotPromo = vi.fn()
  await renderPicker(
    { left: 120, top: 300, bottom: 324 },
    [builtinOption, textBuiltinOption, templateOption],
    { onSelect, onPreviewSlotPromo },
  )

  expect(screen.getByText("Creation Modes")).toBeTruthy()
  expect(screen.getByText("Templates")).toBeTruthy()
  expect(screen.getByText("6 acts · 14 slots")).toBeTruthy()
  expect(screen.getByText("Vox")).toBeTruthy()

  // Clicking the Film button triggers slot preview without selecting the skill
  const previewBtn = screen.getByRole("button", { name: "Preview numbered slot promo" })
  fireEvent.click(previewBtn)
  expect(onPreviewSlotPromo).toHaveBeenCalledTimes(1)
  expect(onPreviewSlotPromo).toHaveBeenCalledWith(templateOption)
  expect(onSelect).not.toHaveBeenCalled()

  // ArrowDown twice crosses from Creation Modes (index 0 -> 1) into Templates (index 2)
  fireEvent.keyDown(window, { key: "ArrowDown" })
  fireEvent.keyDown(window, { key: "ArrowDown" })
  fireEvent.keyDown(window, { key: "Enter" })
  expect(onSelect).toHaveBeenCalledTimes(1)
  expect(onSelect).toHaveBeenCalledWith(templateOption)
})
