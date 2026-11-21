// @vitest-environment jsdom
import { act } from "react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { expect, it, vi } from "vitest"
import { MentionEditor } from "./MentionEditor"

it("adopts a draft typed into server HTML before hydration", async () => {
  const onChange = vi.fn()
  const onRecoverableError = vi.fn()
  const component = <MentionEditor onChange={onChange} onSubmit={() => {}} />
  const host = document.createElement("div")
  host.innerHTML = renderToString(component)
  document.body.appendChild(host)
  let root: Root | undefined
  try {
    const editable = host.querySelector('[role="textbox"]')!
    expect(editable.getAttribute("contenteditable")).toBe("plaintext-only")
    editable.append("First line", document.createElement("br"), "Second line")
    await act(async () => { root = hydrateRoot(host, component, { onRecoverableError }) })
    expect(host.querySelector('[role="textbox"]')).toBe(editable)
    expect(editable.textContent).toBe("First lineSecond line")
    expect(onChange).toHaveBeenCalledWith("First line\nSecond line", [])
    expect(onRecoverableError).not.toHaveBeenCalled()
  } finally {
    await act(async () => root?.unmount())
    host.remove()
  }
})
