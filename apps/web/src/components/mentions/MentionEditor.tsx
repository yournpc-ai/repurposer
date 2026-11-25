"use client"

import {
  lazy,
  Suspense,
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
import { formatMediaTimeMs, type MediaRegionSelection } from "@/lib/mediaRegionSelection"
import { cn } from "@/lib/utils"
import { MentionPicker } from "@/components/mentions/MentionPicker"
import { MENTION_CHIP_CLASS_NAME } from "@/components/mentions/MentionChip"
import {
  SKILL_CHIP_CLASS_NAME,
  skillChipLabel,
} from "@/components/composer/SkillChip"
import { SkillPicker } from "@/components/composer/SkillPicker"
import {
  skillDisplayName,
  skillTriggerQuery,
  type SkillOption,
} from "@/lib/skills"

const LazySlotPreviewDialog = lazy(() =>
  import("@/components/skills/SlotPreviewDialog").then((m) => ({
    default: m.SlotPreviewDialog,
  })),
)

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
  /** Append a brief ([label] is required, [optional:label] is optional). Return the visible draft. */
  insertBrief: (template: string) => string
  selectFirstRequired: () => boolean
  getSubmitText: () => string
  /** Select an occurrence of plain text (recipe prefill placeholders).
   * Returns whether the text was found. */
  selectText: (text: string, occurrence?: "first" | "last") => boolean
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
  mentionChipClassName?: string
  /** Controlled, optional single Skill binding. The option supplies the exact
   * reference for POST /chat plus the DTO display name for the chip. */
  selectedSkill?: SkillOption | null
  onSkillChange?: (option: SkillOption | null) => void
  className?: string
  "data-tour"?: string
  ref?: Ref<MentionEditorHandle>
}

// A stable, empty initial value makes the editable an opaque DOM subtree during hydration.
// After mount the browser and the existing chip editor own every child.
const INITIAL_EDITOR_HTML = { __html: "" }

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

function readMentionRegion(raw: string | undefined): MediaRegionSelection | undefined {
  if (!raw) return undefined
  try {
    return JSON.parse(raw) as MediaRegionSelection
  } catch {
    return undefined
  }
}

/** Serialize the editable DOM into prompt text: text nodes verbatim, chips
 * as `@label` (a quoted chip — 选区引用 — carries its pinned passage inline
 * as `@label "passage"`, so the sentence and the history both keep what the
 * user pointed at), block boundaries as newlines. */
function serializeNode(node: Node, forSubmit: boolean): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? ""
  if (!(node instanceof HTMLElement)) return ""
  if (node.hasAttribute(SKILL_ATTR) || (forSubmit && node.hasAttribute("data-brief-slot"))) return ""
  if (node.dataset.mentionType) {
    const base = `@${node.dataset.mentionLabel ?? ""}`
    const quote = node.dataset.mentionQuote
    const region = readMentionRegion(node.dataset.mentionRegion)
    const regionText = region ? ` ${i18n.t("mentions.regionText", {
      x: region.sourceRect.x,
      y: region.sourceRect.y,
      width: region.sourceRect.width,
      height: region.sourceRect.height,
      sourceWidth: region.sourceSize.width,
      sourceHeight: region.sourceSize.height,
      time: formatMediaTimeMs(region.mediaTimeMs),
    })}` : ""
    return `${base}${quote ? ` "${quote}"` : ""}${regionText}`
  }
  if (node.tagName === "BR") return "\n"
  const inner = Array.from(node.childNodes).map((child) => serializeNode(child, forSubmit)).join("")
  // Block elements (Enter/shift-Enter lines) are newline-separated.
  return node.tagName === "DIV" ? `\n${inner}` : inner
}

function readEditorText(el: HTMLElement | null, forSubmit = false): string {
  return Array.from(el?.childNodes ?? [], (node) => serializeNode(node, forSubmit)).join("").replace(/^\n/, "")
}

function selectSlot(editor: HTMLElement, slot: Element) {
  editor.focus()
  const range = document.createRange()
  // Native composition needs an editable selection inside the capsule.
  range.selectNodeContents(slot)
  const selection = window.getSelection()
  selection?.removeAllRanges()
  selection?.addRange(range)
}

export function MentionEditor({
  placeholder,
  disabled,
  onChange,
  onSubmit,
  mentionContext,
  mentionChipClassName,
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
    // Leave the browser's text nodes and caret in place when a slot becomes prose.
    for (const slot of el.querySelectorAll<HTMLElement>("[data-brief-slot]")) {
      if (slot.textContent === slot.dataset.placeholderText) continue
      slot.removeAttribute("data-brief-slot")
      slot.removeAttribute("data-placeholder-text")
      slot.removeAttribute("class")
    }
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
    const text = readEditorText(el)
    const mentions: ChatMention[] = Array.from(
      el.querySelectorAll<HTMLElement>(`[${MENTION_ATTR}]`),
    ).map((node) => {
      const region = readMentionRegion(node.dataset.mentionRegion)
      return {
        type: node.dataset.mentionType as ChatMention["type"],
        id: node.dataset.mentionId ?? "",
        label: node.dataset.mentionLabel ?? "",
        // Quote and region live only on their chip: deleting the chip removes
        // the serialized text and every structured field in the same sync.
        ...(node.dataset.mentionQuote ? { quote: node.dataset.mentionQuote } : {}),
        ...(region ? { region } : {}),
      }
    })
    onChange(text, mentions)
    if (selectedSkill && !el.querySelector(`[${SKILL_ATTR}]`)) {
      onSkillChange?.(null)
    }
    return text
  }, [onChange, onSkillChange, selectedSkill])

  const [adoptedInitialDraft, setAdoptedInitialDraft] = useState(false)
  useEffect(() => {
    if (adoptedInitialDraft) return
    setAdoptedInitialDraft(true)
    if (editorRef.current?.textContent) syncNow()
  }, [adoptedInitialDraft, syncNow])

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
      if (mention.region) chip.dataset.mentionRegion = JSON.stringify(mention.region)
      chip.className = cn(MENTION_CHIP_CLASS_NAME, mentionChipClassName)

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
      if (mention.region) {
        const region = document.createElement("span")
        region.textContent = i18n.t("mentions.regionChip", {
          time: formatMediaTimeMs(mention.region.mediaTimeMs),
          width: mention.region.sourceRect.width,
          height: mention.region.sourceRect.height,
        })
        region.className = "text-muted-foreground"
        chip.appendChild(region)
      }

      return chip
    },
    [mentionChipClassName],
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
      label.textContent = skillChipLabel(
        option,
        i18n.t("skills.external"),
        skillDisplayName(option, i18n.t),
      )
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

  const insertBrief = useCallback((template: string) => {
    const el = editorRef.current
    if (!el) return ""
    normalizeEmpty(el)
    const fragment = document.createDocumentFragment()
    let firstRequired: HTMLElement | undefined
    let offset = 0
    for (const match of template.matchAll(/\[(optional:)?([^\[\]\n]+)\]/g)) {
      fragment.append(template.slice(offset, match.index))
      const slot = document.createElement("span")
      slot.dataset.briefSlot = match[1] ? "optional" : "required"
      slot.className = "rounded bg-muted px-1.5 py-0.5 text-muted-foreground selection:bg-foreground selection:text-background"
      slot.textContent = `[${match[2]}]`
      slot.dataset.placeholderText = slot.textContent
      fragment.append(slot)
      if (!match[1]) firstRequired ??= slot
      offset = match.index + match[0].length
    }
    fragment.append(template.slice(offset))
    el.append(fragment)
    setPicker(null)
    if (firstRequired) selectSlot(el, firstRequired)
    else el.focus()
    return syncNow() ?? ""
  }, [syncNow])

  const selectFirstRequired = useCallback(() => {
    const el = editorRef.current
    const slot = el?.querySelector('[data-brief-slot="required"]')
    if (!el || !slot) return false
    selectSlot(el, slot)
    return true
  }, [])

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
  const selectText = useCallback((needle: string, occurrence: "first" | "last" = "first") => {
    const el = editorRef.current
    if (!el || !needle) return false
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    let match: Range | undefined
    let node = walker.nextNode()
    while (node) {
      const text = node.textContent ?? ""
      const start = occurrence === "last" ? text.lastIndexOf(needle) : text.indexOf(needle)
      if (start >= 0 && !node.parentElement?.closest(`[${SKILL_ATTR}],[${MENTION_ATTR}]`)) {
        match = document.createRange()
        match.setStart(node, start)
        match.setEnd(node, start + needle.length)
        if (occurrence === "first") break
      }
      node = walker.nextNode()
    }
    if (!match) return false
    el.focus()
    const sel = window.getSelection()
    sel?.removeAllRanges()
    sel?.addRange(match)
    return true
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
      insertBrief,
      selectFirstRequired,
      getSubmitText: () => readEditorText(editorRef.current, true),
      selectText,
      clear,
      focus,
      getContentHeight: () => editorRef.current?.scrollHeight ?? 0,
    }),
    [insertMention, insertText, insertBrief, selectFirstRequired, selectText, clear, focus],
  )

  const handleKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (picker || e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return
    if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const el = e.currentTarget
      const selection = window.getSelection()
      if (!selection?.rangeCount) return
      const caret = selection.getRangeAt(0).cloneRange()
      caret.collapse(false)
      for (const slot of el.querySelectorAll("[data-brief-slot]")) {
        const next = document.createRange()
        next.selectNode(slot)
        if (next.compareBoundaryPoints(Range.START_TO_START, caret) >= 0) {
          e.preventDefault()
          selectSlot(el, slot)
          break
        }
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
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

  const [slotPreviewTarget, setSlotPreviewTarget] = useState<{
    skillVersionId: string
    name: string
    defaultStylePreset?: string | null
  } | null>(null)

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
          onPreviewSlotPromo={(option) => {
            if (option.reference.kind !== "external") return
            setPicker(null)
            setSlotPreviewTarget({
              skillVersionId: option.reference.skill_version_id,
              name: option.name,
              defaultStylePreset: option.blueprint_summary?.style_preset ?? null,
            })
          }}
        />
      )}
      {slotPreviewTarget && (
        <Suspense fallback={null}>
          <LazySlotPreviewDialog
            open
            onOpenChange={(nextOpen) => {
              if (!nextOpen) setSlotPreviewTarget(null)
            }}
            skillVersionId={slotPreviewTarget.skillVersionId}
            skillName={slotPreviewTarget.name}
            defaultStylePreset={slotPreviewTarget.defaultStylePreset}
          />
        </Suspense>
      )}
      {/* React renders NO children here — the DOM owns text and inline chips. */}
      <div
        ref={editorRef}
        contentEditable={disabled ? false : adoptedInitialDraft ? true : "plaintext-only"}
        dangerouslySetInnerHTML={INITIAL_EDITOR_HTML}
        suppressHydrationWarning
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        data-slot="input-group-control"
        data-placeholder={placeholder}
        data-tour={dataTour}
        onCompositionEnd={() => {
          syncNow()
          updatePicker()
        }}
        onInput={(event) => {
          if ((event.nativeEvent as InputEvent).isComposing) return
          syncNow()
          updatePicker()
        }}
        onKeyDown={handleKeyDown}
        onKeyUp={(event) => {
          if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) updatePicker()
        }}
        onBlur={() => setPicker(null)}
        onClick={(event) => {
          const slot = (event.target as HTMLElement).closest("[data-brief-slot]")
          if (slot) selectSlot(event.currentTarget, slot)
        }}
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
