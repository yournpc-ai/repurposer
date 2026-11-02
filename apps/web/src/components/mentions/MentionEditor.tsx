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
import { cn } from "@/lib/utils"
import { MentionPicker } from "@/components/mentions/MentionPicker"
import {
  SKILL_CHIP_CLASS_NAME,
  skillChipLabel,
} from "@/components/composer/SkillChip"
import { SkillPicker } from "@/components/composer/SkillPicker"
import { skillTriggerQuery, type SkillOption } from "@/lib/skills"

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
 * Skill chips stay inline too, but serialize to nothing: their exact
 * reference rides selectedSkill, never a second prompt token.
 */

/** An "@" at line start or after whitespace opens the picker; the capture
 * group is the filter query. The whitespace guard keeps email-style text
 * ("name@host") from false-triggering; Unicode letters match CJK titles. */
const MENTION_TRIGGER = /(?:^|\s)@([\p{L}\p{N}_-]*)$/u

export interface MentionEditorHandle {
  /** Insert a mention chip at the active "@query" (replacing it), else at
   * the end of the text. Registry rules apply: same type+id dedupes, an
   * exclusive type replaces its previous chip. */
  insertMention: (mention: ChatMention) => void
  /** Insert plain text at the end ("\n" becomes a line break). */
  insertText: (text: string) => void
  /** Select the first occurrence of plain text (recipe prefill placeholders).
   * Returns whether the text was found. */
  selectText: (text: string) => boolean
  clear: (options?: { preserveSkill?: boolean }) => void
  focus: () => void
  /** The content's intrinsic height (the editable's scrollHeight) — for
   * hosts whose band grows with the draft (the home composer's
   * content-driven band). */
  getContentHeight: () => number
}

export interface MentionEditorProps {
  placeholder?: string
  disabled?: boolean
  onChange: (text: string, mentions: ChatMention[]) => void
  /** Enter without shift (picker closed, not mid-IME). */
  onSubmit: () => void
  /** Live surface data for registry candidate feeds (keep referentially
   * stable — e.g. useMemo — or the picker reloads every render). */
  mentionContext?: MentionContext
  /** Controlled, optional single Skill binding. The option supplies the exact
   * reference for POST /chat plus the DTO display name for the chip. */
  selectedSkill?: SkillOption | null
  onSkillChange?: (option: SkillOption | null) => void
  className?: string
  "data-tour"?: string
  ref?: Ref<MentionEditorHandle>
}

const MENTION_ATTR = "data-mention-type"
const SKILL_ATTR = "data-skill-chip"

function skillKey(option: SkillOption): string {
  const reference = option.reference
  return reference.kind === "builtin"
    ? `builtin:${reference.skill_id}:${reference.version}`
    : `external:${reference.skill_version_id}`
}

/** An "empty" editable usually isn't: focusing inserts a browser placeholder
 * <br>, and anything appended lands AFTER it (the ghost first line). Treat
 * placeholder-only content as truly empty before programmatic inserts. */
function normalizeEmpty(el: HTMLElement) {
  if (!el.textContent?.trim() && !el.querySelector(`[${MENTION_ATTR}],[${SKILL_ATTR}]`)) {
    el.innerHTML = ""
  }
}

/** Serialize the editable DOM into prompt text: text nodes verbatim, chips
 * as `@label` (a quoted chip — 选区引用 — carries its pinned passage inline
 * as `@label "passage"`, so the sentence and the history both keep what the
 * user pointed at), block boundaries as newlines. */
function serializeNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? ""
  if (!(node instanceof HTMLElement)) return ""
  if (node.hasAttribute(SKILL_ATTR)) return ""
  if (node.dataset.mentionType) {
    const base = `@${node.dataset.mentionLabel ?? ""}`
    const quote = node.dataset.mentionQuote
    return quote ? `${base} "${quote}"` : base
  }
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
  selectedSkill,
  onSkillChange,
  className,
  "data-tour": dataTour,
  ref,
}: MentionEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null)
  const [picker, setPicker] = useState<{
    kind: "mention" | "skill"
    query: string
    rect: DOMRect
  } | null>(null)

  /** DOM → state: the single sync funnel every edit path calls. */
  const syncNow = useCallback(() => {
    const el = editorRef.current
    if (!el) return
    // A deleted-to-empty editable keeps a ghost residue (a lone <br> or an
    // empty text node — the browser's editing-line scaffolding): invisible,
    // but it defeats the CSS :empty placeholder for the rest of the
    // session (2026-09-13: @ → cancel → delete left the dock input
    // placeholderless even with an empty value). Reset to a truly empty
    // DOM at the funnel so the placeholder comes back; the guard mirrors
    // normalizeEmpty but never eats intentional whitespace (no trim).
    if (!el.textContent && !el.querySelector(`[${MENTION_ATTR}],[${SKILL_ATTR}]`)) {
      el.innerHTML = ""
    }
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
      // The pinned passage round-trips through the DOM (选区引用 — a rollback
      // re-insert keeps it; absent = the whole entity is the referent).
      ...(node.dataset.mentionQuote ? { quote: node.dataset.mentionQuote } : {}),
    }))
    onChange(text, mentions)
    if (selectedSkill && !el.querySelector(`[${SKILL_ATTR}]`)) {
      onSkillChange?.(null)
    }
  }, [onChange, onSkillChange, selectedSkill])

  /** The inline chip node: `@label` in one contenteditable=false span.
   * Text-only (no icon) — the @ prefix makes it self-describing in the
   * sentence; deletion uses the editor's ordinary text-editing gestures. */
  const buildChip = useCallback(
    (mention: ChatMention): HTMLSpanElement => {
      const chip = document.createElement("span")
      chip.contentEditable = "false"
      chip.dataset.mentionType = mention.type
      chip.dataset.mentionId = mention.id
      chip.dataset.mentionLabel = mention.label
      if (mention.quote) chip.dataset.mentionQuote = mention.quote
      chip.className =
        "mx-0.5 inline-flex items-baseline gap-0.5 rounded-md bg-muted px-1 text-foreground"

      const label = document.createElement("span")
      label.textContent = `@${mention.label}`
      chip.appendChild(label)

      // 选区引用: the pinned passage shows as a muted snippet — the chip
      // says WHICH PART, not just which product (display-truncated only;
      // the dataset carries the full quote).
      if (mention.quote) {
        const quote = document.createElement("span")
        const snippet = mention.quote.replace(/\s+/g, " ").trim()
        quote.textContent = `“${snippet.length > 24 ? `${snippet.slice(0, 24)}…` : snippet}”`
        quote.className = "text-muted-foreground"
        chip.appendChild(quote)
      }

      return chip
    },
    [],
  )

  /** Track the "@" and "/" triggers against the live selection: query = text
   * between the trigger and the caret; either picker anchors to the caret. */
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
    const beforeCaret = (sel.anchorNode.textContent ?? "").slice(
      0,
      sel.anchorOffset,
    )
    const mentionMatch = beforeCaret.match(MENTION_TRIGGER)
    const skillQuery = mentionMatch ? null : skillTriggerQuery(beforeCaret)
    if (!mentionMatch && skillQuery === null) {
      setPicker(null)
      return
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect()
    setPicker(
      mentionMatch
        ? { kind: "mention", query: mentionMatch[1], rect }
        : { kind: "skill", query: skillQuery ?? "", rect },
    )
  }, [])

  /** Skill is also an inline non-editable node, but its green slash family is
   * deliberately different from @. Serialization ignores the whole node: the
   * structured reference rides selectedSkill, never the prompt or mentions. */
  const buildSkillChip = useCallback(
    (option: SkillOption): HTMLSpanElement => {
      const chip = document.createElement("span")
      chip.contentEditable = "false"
      chip.dataset.skillChip = skillKey(option)
      chip.className = SKILL_CHIP_CLASS_NAME

      const label = document.createElement("span")
      label.textContent = skillChipLabel(option, i18n.t("skills.external"))
      label.className = "max-w-56 truncate"
      chip.appendChild(label)
      return chip
    },
    [],
  )

  const insertSkillChipAt = useCallback(
    (range: Range, option: SkillOption) => {
      const el = editorRef.current
      el?.querySelectorAll(`[${SKILL_ATTR}]`).forEach((node) => node.remove())
      range.deleteContents()
      const chip = buildSkillChip(option)
      range.insertNode(chip)
      const spacer = document.createTextNode(" ")
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
    [buildSkillChip, syncNow],
  )

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

  const selectSkill = useCallback(
    (option: SkillOption) => {
      const el = editorRef.current
      if (!el) return
      el.focus()
      normalizeEmpty(el)
      const sel = window.getSelection()
      let range: Range | null = null
      if (
        sel &&
        sel.rangeCount > 0 &&
        el.contains(sel.anchorNode) &&
        sel.anchorNode?.nodeType === Node.TEXT_NODE
      ) {
        const node = sel.anchorNode as Text
        const beforeCaret = (node.textContent ?? "").slice(0, sel.anchorOffset)
        const query = skillTriggerQuery(beforeCaret)
        if (query !== null) {
          range = document.createRange()
          range.setStart(node, sel.anchorOffset - query.length - 1)
          range.setEnd(node, sel.anchorOffset)
        }
      }
      if (!range) {
        range = document.createRange()
        range.selectNodeContents(el)
        range.collapse(false)
      }
      insertSkillChipAt(range, option)
      onSkillChange?.(option)
      setPicker(null)
      el.focus()
    },
    [insertSkillChipAt, onSkillChange],
  )

  const clear = useCallback((options?: { preserveSkill?: boolean }) => {
    const el = editorRef.current
    const preserved = options?.preserveSkill
      ? el?.querySelector<HTMLElement>(`[${SKILL_ATTR}]`)
      : null
    preserved?.remove()
    if (el) el.innerHTML = ""
    if (el && preserved) el.append(preserved, document.createTextNode(" "))
    setPicker(null)
    if (!options?.preserveSkill) onSkillChange?.(null)
    syncNow()
  }, [onSkillChange, syncNow])

  /** Select a literal text run inside the editable (the recipe prefill's
   * visible blank). The DOM walker keeps this honest for the plain-text
   * prefill while never reaching into mention chips. */
  const selectText = useCallback((needle: string) => {
    const el = editorRef.current
    if (!el || !needle) return false
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    let node = walker.nextNode()
    while (node) {
      const text = node.textContent ?? ""
      const start = text.indexOf(needle)
      if (start >= 0) {
        el.focus()
        const range = document.createRange()
        range.setStart(node, start)
        range.setEnd(node, start + needle.length)
        const sel = window.getSelection()
        sel?.removeAllRanges()
        sel?.addRange(range)
        return true
      }
      node = walker.nextNode()
    }
    return false
  }, [])

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
    () => ({
      insertMention,
      insertText,
      selectText,
      clear,
      focus,
      getContentHeight: () => editorRef.current?.scrollHeight ?? 0,
    }),
    [insertMention, insertText, selectText, clear, focus],
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

  // Reconcile external bindings (Home card / rollback) without remounting or
  // moving the caret. Picker selection has already inserted its exact node.
  useEffect(() => {
    const el = editorRef.current
    if (!el) return
    const existing = el.querySelector<HTMLElement>(`[${SKILL_ATTR}]`)
    if (!selectedSkill) {
      if (existing) {
        existing.remove()
        syncNow()
      }
      return
    }
    if (existing?.dataset.skillChip === skillKey(selectedSkill)) return
    const chip = buildSkillChip(selectedSkill)
    if (existing) {
      existing.replaceWith(chip)
    } else {
      // A card-born binding leads the prefill: `/Skill prompt`. Do not move
      // the selection — recipe placeholder selection belongs to the caller.
      el.prepend(chip, document.createTextNode(" "))
    }
    syncNow()
  }, [buildSkillChip, selectedSkill, syncNow])

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
      {picker?.kind === "mention" && (
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
      {picker?.kind === "skill" && (
        <SkillPicker
          query={picker.query}
          position={picker.rect}
          onSelect={selectSkill}
          onClose={() => setPicker(null)}
        />
      )}
      {/* React renders NO children here — the DOM owns text and inline chips. */}
      <div
        ref={editorRef}
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        data-slot="input-group-control"
        data-placeholder={placeholder}
        data-tour={dataTour}
        onInput={syncNow}
        onKeyDown={handleKeyDown}
        onKeyUp={updatePicker}
        onMouseUp={updatePicker}
        onPaste={handlePaste}
        className={cn(
          "min-h-0 min-w-0 flex-1 overflow-y-auto bg-transparent p-2 text-base break-words whitespace-pre-wrap outline-none thin-scroll",
          disabled && "pointer-events-none opacity-60",
          className,
        )}
      />
    </>
  )
}
