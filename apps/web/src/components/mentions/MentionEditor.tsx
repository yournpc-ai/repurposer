"use client"

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type Ref,
} from "react"

import {
  mentionTypeDef,
  type ChatMention,
  type MentionContext,
} from "@/lib/mentions"
import i18n from "@/lib/i18n"
import { MentionPicker } from "@/components/mentions/MentionPicker"

/**
 * 提及编辑器 (MentionEditor) — the full-form mention input (docs/tasks/
 * recipe-mention.md §2.5, pulled forward 2026-08-02): a contentEditable box
 * where a picked mention becomes an INLINE chip (contenteditable=false) at
 * the @ position — the sentence never loses what was @'d.
 *
 * Architecture: the DOM owns the text; React never renders children inside
 * the editable area (it would fight the browser's own mutations). Every edit
 * path — typing, chip pick, chip ×, backspace, paste, imperative insert —
 * funnels into `syncNow`, which derives `{text, mentions}` from the DOM and
 * reports them up. Mentions serialize into the text as `@label` (the LLM
 * reads a natural sentence; the structured pin rides the mentions array).
 */

/** An "@" at line start or after whitespace opens the picker; the capture
 * group is the filter query. The whitespace guard keeps email-style text
 * ("name@host") from false-triggering; Unicode letters match CJK titles. */
export const MENTION_TRIGGER = /(?:^|\s)@([\p{L}\p{N}_-]*)$/u

export interface MentionEditorHandle {
  /** Insert a mention chip at the active "@query" (replacing it), else at
   * the end of the text. Registry rules apply: same type+id dedupes, an
   * exclusive type replaces its previous chip. */
  insertMention: (mention: ChatMention) => void
  /** Insert plain text at the end ("\n" becomes a line break). */
  insertText: (text: string) => void
  clear: () => void
  focus: () => void
}

interface MentionEditorProps {
  placeholder?: string
  disabled?: boolean
  onChange: (text: string, mentions: ChatMention[]) => void
  /** Enter without shift (picker closed, not mid-IME). */
  onSubmit: () => void
  /** Live surface data for registry candidate feeds (keep referentially
   * stable — e.g. useMemo — or the picker reloads every render). */
  mentionContext?: MentionContext
  className?: string
  "data-tour"?: string
  ref?: Ref<MentionEditorHandle>
}

const MENTION_ATTR = "data-mention-type"

/** An "empty" editable usually isn't: focusing inserts a browser placeholder
 * <br>, and anything appended lands AFTER it (the ghost first line). Treat
 * placeholder-only content as truly empty before programmatic inserts. */
function normalizeEmpty(el: HTMLElement) {
  if (!el.textContent?.trim() && !el.querySelector(`[${MENTION_ATTR}]`)) {
    el.innerHTML = ""
  }
}

/** Serialize the editable DOM into prompt text: text nodes verbatim, chips
 * as `@label`, block boundaries as newlines. */
function serializeNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? ""
  if (!(node instanceof HTMLElement)) return ""
  if (node.dataset.mentionType) return `@${node.dataset.mentionLabel ?? ""}`
  if (node.tagName === "BR") return "\n"
  const inner = Array.from(node.childNodes).map(serializeNode).join("")
  // Block elements (Enter/shift-Enter lines) are newline-separated.
  return node.tagName === "DIV" ? `\n${inner}` : inner
}

export function MentionEditor({
  placeholder,
  disabled,
  onChange,
  onSubmit,
  mentionContext,
  className,
  "data-tour": dataTour,
  ref,
}: MentionEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null)
  const [picker, setPicker] = useState<{ query: string; rect: DOMRect } | null>(
    null,
  )

  /** DOM → state: the single sync funnel every edit path calls. */
  const syncNow = useCallback(() => {
    const el = editorRef.current
    if (!el) return
    const text = Array.from(el.childNodes)
      .map(serializeNode)
      .join("")
      .replace(/^\n/, "") // leading block boundary is not a real newline
    const mentions: ChatMention[] = Array.from(
      el.querySelectorAll<HTMLElement>(`[${MENTION_ATTR}]`),
    ).map((node) => ({
      type: node.dataset.mentionType as ChatMention["type"],
      id: node.dataset.mentionId ?? "",
      label: node.dataset.mentionLabel ?? "",
    }))
    onChange(text, mentions)
  }, [onChange])

  /** The inline chip node: `@label` + × in one contenteditable=false span.
   * Text-only (no icon) — the @ prefix makes it self-describing in the
   * sentence; the registry icon stays on the static chip (message bubbles). */
  const buildChip = useCallback(
    (mention: ChatMention): HTMLSpanElement => {
      const chip = document.createElement("span")
      chip.contentEditable = "false"
      chip.dataset.mentionType = mention.type
      chip.dataset.mentionId = mention.id
      chip.dataset.mentionLabel = mention.label
      chip.className =
        "mx-0.5 inline-flex items-baseline gap-0.5 rounded-md bg-muted px-1 text-foreground"

      const label = document.createElement("span")
      label.textContent = `@${mention.label}`
      chip.appendChild(label)

      const remove = document.createElement("button")
      remove.type = "button"
      remove.textContent = "×"
      remove.setAttribute("aria-label", i18n.t("mentions.remove"))
      remove.className = "text-muted-foreground hover:text-foreground"
      remove.addEventListener("mousedown", (e) => e.preventDefault())
      remove.addEventListener("click", () => {
        chip.remove()
        syncNow()
        editorRef.current?.focus()
      })
      chip.appendChild(remove)
      return chip
    },
    [syncNow],
  )

  /** Track the "@" trigger against the live selection: query = text between
   * the "@" and the caret; the picker anchors to the caret rect. */
  const updatePicker = useCallback(() => {
    const el = editorRef.current
    const sel = window.getSelection()
    if (
      !el ||
      !sel ||
      sel.rangeCount === 0 ||
      !el.contains(sel.anchorNode) ||
      !sel.anchorNode ||
      sel.anchorNode.nodeType !== Node.TEXT_NODE
    ) {
      setPicker(null)
      return
    }
    const match = (sel.anchorNode.textContent ?? "")
      .slice(0, sel.anchorOffset)
      .match(MENTION_TRIGGER)
    if (!match) {
      setPicker(null)
      return
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect()
    setPicker({ query: match[1], rect })
  }, [])

  /** Insert a chip node at `range` (replacing its contents) and park the
   * caret after a trailing space so typing continues separated from the chip. */
  const insertChipAt = useCallback(
    (range: Range, mention: ChatMention) => {
      const def = mentionTypeDef(mention.type)
      const el = editorRef.current
      if (el) {
        // Registry rules, DOM edition: dedupe same type+id; an exclusive
        // type replaces its previous chip (v1: one recipe per message).
        const selector = def?.exclusive
          ? `[${MENTION_ATTR}="${mention.type}"]`
          : `[${MENTION_ATTR}="${mention.type}"][data-mention-id="${mention.id}"]`
        el.querySelectorAll(selector).forEach((node) => node.remove())
      }
      range.deleteContents()
      const chip = buildChip(mention)
      range.insertNode(chip)
      const spacer = document.createTextNode(" ")
      chip.after(spacer)
      const sel = window.getSelection()
      if (sel) {
        const after = document.createRange()
        after.setStartAfter(spacer)
        after.collapse(true)
        sel.removeAllRanges()
        sel.addRange(after)
      }
      syncNow()
    },
    [buildChip, syncNow],
  )

  const insertMention = useCallback(
    (mention: ChatMention) => {
      const el = editorRef.current
      if (!el) return
      el.focus()
      normalizeEmpty(el)
      const sel = window.getSelection()
      // Active "@query" at the caret → replace exactly that text.
      if (
        sel &&
        sel.rangeCount > 0 &&
        el.contains(sel.anchorNode) &&
        sel.anchorNode?.nodeType === Node.TEXT_NODE
      ) {
        const node = sel.anchorNode as Text
        const match = (node.textContent ?? "")
          .slice(0, sel.anchorOffset)
          .match(MENTION_TRIGGER)
        if (match) {
          const range = document.createRange()
          range.setStart(node, sel.anchorOffset - match[1].length - 1)
          range.setEnd(node, sel.anchorOffset)
          insertChipAt(range, mention)
          return
        }
      }
      // Otherwise append at the end.
      const range = document.createRange()
      range.selectNodeContents(el)
      range.collapse(false)
      insertChipAt(range, mention)
    },
    [insertChipAt],
  )

  const insertText = useCallback(
    (text: string) => {
      const el = editorRef.current
      if (!el) return
      el.focus()
      normalizeEmpty(el)
      const sel = window.getSelection()
      const range = document.createRange()
      range.selectNodeContents(el)
      range.collapse(false)
      sel?.removeAllRanges()
      sel?.addRange(range)
      // execCommand("insertText") fires a native input event (sync via
      // onInput) and renders \n as line breaks for free. Deprecated but
      // universally supported; the manual alternative re-implements it worse.
      document.execCommand("insertText", false, text)
      syncNow()
    },
    [syncNow],
  )

  const clear = useCallback(() => {
    const el = editorRef.current
    if (el) el.innerHTML = ""
    setPicker(null)
    syncNow()
  }, [syncNow])

  const focus = useCallback(() => {
    const el = editorRef.current
    if (!el) return
    el.focus()
    // Caret to the end (focus alone parks it at the start in some browsers).
    const sel = window.getSelection()
    const range = document.createRange()
    range.selectNodeContents(el)
    range.collapse(false)
    sel?.removeAllRanges()
    sel?.addRange(range)
  }, [])

  useImperativeHandle(
    ref,
    () => ({ insertMention, insertText, clear, focus }),
    [insertMention, insertText, clear, focus],
  )

  const handleKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      onSubmit()
    }
  }

  const handlePaste = (e: ClipboardEvent<HTMLDivElement>) => {
    // Plain text only — foreign contenteditable HTML never enters the box.
    e.preventDefault()
    const text = e.clipboardData.getData("text/plain")
    if (text) document.execCommand("insertText", false, text)
  }

  // Close the picker when the selection leaves the editor entirely.
  useEffect(() => {
    const handler = () => {
      const el = editorRef.current
      const sel = window.getSelection()
      if (el && sel?.anchorNode && !el.contains(sel.anchorNode)) setPicker(null)
    }
    document.addEventListener("selectionchange", handler)
    return () => document.removeEventListener("selectionchange", handler)
  }, [])

  return (
    <>
      {picker && (
        <MentionPicker
          query={picker.query}
          position={picker.rect}
          context={mentionContext ?? {}}
          onSelect={(mention) => {
            insertMention(mention)
            setPicker(null)
          }}
          onClose={() => setPicker(null)}
        />
      )}
      {/* React renders NO children here — the DOM owns the content. */}
      <div
        ref={editorRef}
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        data-placeholder={placeholder}
        data-tour={dataTour}
        onInput={syncNow}
        onKeyDown={handleKeyDown}
        onKeyUp={updatePicker}
        onMouseUp={updatePicker}
        onPaste={handlePaste}
        className={`min-h-0 flex-1 overflow-y-auto bg-transparent p-2 text-base break-words whitespace-pre-wrap outline-none ${
          disabled ? "pointer-events-none opacity-60" : ""
        } ${className ?? ""}`}
      />
    </>
  )
}
