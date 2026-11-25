// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { createRef } from "react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { localBuiltinSkillOptions, skillOptionForReference } from "@/lib/skills"
import { MentionEditor, type MentionEditorHandle } from "./MentionEditor"

const brief = "Title: [Your title]\nAudience: [Your audience]\nLength: [optional:Duration]"
const selection = () => window.getSelection()!

function setup(withSkill = false) {
  const ref = createRef<MentionEditorHandle>()
  const onChange = vi.fn()
  const onSubmit = vi.fn()
  const onSkillChange = vi.fn()
  const skill = skillOptionForReference({ kind: "builtin", skill_id: "text-animation", version: "1.0.0" })
  render(<MentionEditor ref={ref} onChange={onChange} onSubmit={onSubmit}
    selectedSkill={withSkill ? skill : null} onSkillChange={onSkillChange}
    mentionContext={{ files: [{ name: "clip.mp4", kind: "video" }] }} />)
  act(() => { ref.current!.insertBrief(brief) })
  return { editor: screen.getByRole("textbox"), handle: ref.current!, onChange, onSubmit, onSkillChange }
}

// jsdom exposes Selection/Range but leaves the browser's contenteditable default action to the caller.
function applyInput(editor: HTMLElement, text: string, inputType = "insertText") {
  const range = selection().getRangeAt(0)
  range.deleteContents()
  if (text) {
    const node = document.createTextNode(text)
    range.insertNode(node)
    range.setStart(node, text.length)
    range.collapse(true)
  }
  fireEvent.input(editor, { data: text, inputType, isComposing: inputType === "insertCompositionText" })
}

beforeEach(() => {
  Object.defineProperty(Range.prototype, "getBoundingClientRect", { configurable: true, value: () => new DOMRect() })
})

afterEach(() => {
  cleanup()
  Reflect.deleteProperty(Range.prototype, "getBoundingClientRect")
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it("selects whole slots on prefill, click and forward Tab, returning to normal focus order at the end", () => {
  const { editor, handle } = setup()
  expect(document.activeElement).toBe(editor)
  expect(selection().toString()).toBe("[Your title]")
  fireEvent.click(screen.getByText("[Your audience]"))
  expect(selection().toString()).toBe("[Your audience]")
  expect(fireEvent.keyDown(editor, { key: "Tab" })).toBe(false)
  expect(selection().toString()).toBe("[Duration]")
  expect(fireEvent.keyDown(editor, { key: "Tab" })).toBe(true)
  expect(handle.selectFirstRequired()).toBe(true)
  applyInput(editor, "Launch [v2]")
  expect(handle.selectFirstRequired()).toBe(true)
  expect(selection().toString()).toBe("[Your audience]")
  applyInput(editor, "Designers")
  expect(handle.selectFirstRequired()).toBe(false)
  expect(handle.getSubmitText()).toBe("Title: Launch [v2]\nAudience: Designers\nLength: ")
  expect(editor.querySelectorAll("[data-brief-slot]")).toHaveLength(1)
})

it("replaces the selection with plain clipboard text and treats pasted brackets as ordinary text", () => {
  const { editor, handle } = setup()
  const execCommand = vi.fn((_command: string, _ui: boolean, text: string) => {
    applyInput(editor, text, "insertFromPaste")
    return true
  })
  Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand })
  try {
    const getData = vi.fn((type) => type === "text/plain" ? "[Launch]\n<notes>" : "<b>Launch</b>")
    expect(fireEvent.paste(editor, { clipboardData: { getData } })).toBe(false)
    expect(getData).toHaveBeenCalledExactlyOnceWith("text/plain")
    expect(execCommand).toHaveBeenCalledWith("insertText", false, "[Launch]\n<notes>")
    expect(handle.getSubmitText()).toContain("Title: [Launch]\n<notes>\n")
    expect(editor.querySelector("b, notes")).toBeNull()
  } finally {
    Reflect.deleteProperty(document, "execCommand")
  }
})

it.each([["Backspace", "deleteContentBackward"], ["Delete", "deleteContentForward"]])(
  "%s removes a selected capsule without touching its neighbors", (key, inputType) => {
    const { editor, handle } = setup()
    expect(fireEvent.keyDown(editor, { key })).toBe(true)
    applyInput(editor, "", inputType)
    expect(editor.querySelectorAll("[data-brief-slot]")).toHaveLength(2)
    expect(handle.selectFirstRequired()).toBe(true)
    expect(selection().toString()).toBe("[Your audience]")
  },
)

it("lets IME own the selection, Tab and Enter until its text is committed", () => {
  const { editor, onSubmit, handle } = setup()
  const slot = editor.querySelector('[data-brief-slot="required"]')!
  const range = selection().getRangeAt(0)
  expect(slot.contains(range.commonAncestorContainer)).toBe(true)
  expect(slot.closest('[contenteditable="false"]')).toBeNull()
  fireEvent.compositionStart(editor)
  expect(fireEvent.keyDown(editor, { key: "Tab", isComposing: true })).toBe(true)
  expect(selection().toString()).toBe("[Your title]")
  fireEvent.keyDown(editor, { key: "Enter", isComposing: true })
  fireEvent.keyDown(editor, { key: "Enter", keyCode: 229 })
  expect(onSubmit).not.toHaveBeenCalled()
  applyInput(editor, "月相", "insertCompositionText")
  fireEvent.compositionEnd(editor, { data: "月相" })
  expect(handle.getSubmitText()).toContain("Title: 月相")
  fireEvent.keyDown(editor, { key: "Enter" })
  expect(onSubmit).toHaveBeenCalledOnce()
})

it("keeps the mention picker in control and serializes mentions separately from skill bindings", async () => {
  const { editor, handle, onChange, onSkillChange } = setup(true)
  applyInput(editor, "@clip")
  const option = await screen.findByRole("button", { name: /clip.mp4/ })
  expect(fireEvent.keyDown(editor, { key: "Tab" })).toBe(true)
  fireEvent.click(option)
  expect(handle.getSubmitText()).toContain("@clip.mp4")
  expect(handle.getSubmitText()).not.toContain("text-animation")
  expect(onChange.mock.lastCall?.[1]).toMatchObject([{ type: "asset", label: "clip.mp4" }])
  act(() => handle.clear({ preserveSkill: true }))
  expect(editor.querySelector("[data-skill-chip]")).toBeTruthy()
  expect(editor.querySelector("[data-brief-slot],[data-mention-type]")).toBeNull()
  act(() => handle.clear())
  expect(editor.childNodes).toHaveLength(0)
  expect(onChange).toHaveBeenLastCalledWith("", [])
  expect(onSkillChange).toHaveBeenCalledWith(null)
})

it("lets the slash picker bind its skill without moving Tab to a brief slot or submitting", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ items: localBuiltinSkillOptions() })))
  const { editor, handle, onSkillChange, onSubmit } = setup()
  applyInput(editor, "/text-animation")
  await screen.findByRole("button")
  expect(fireEvent.keyDown(editor, { key: "Tab" })).toBe(true)
  fireEvent.keyDown(editor, { key: "Enter" })
  expect(onSubmit).not.toHaveBeenCalled()
  expect(onSkillChange).toHaveBeenCalledWith(expect.objectContaining({ skill_id: "text-animation" }))
  expect(handle.getSubmitText()).not.toContain("/text-animation")
  expect(editor.querySelectorAll("[data-brief-slot]")).toHaveLength(2)
})
