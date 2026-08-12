import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Ban, Plus, Quote, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

/**
 * Style list editors (persona form tab): the AI-refined list fields render
 * as chips clouds (short words) and quote cards (sentences) instead of
 * newline-joined textareas. Interaction laws for both: × removes (no
 * confirm — the save button is the commit boundary), "+ Add" opens an
 * inline input (Enter / blur commits, Esc cancels), clicking an entry
 * edits it inline. Fills only (`bg-muted`), no strokes, per the card-depth
 * rules; the warning variant adds a destructive-token Ban icon, no emoji.
 */

interface ListEditorProps {
  items: string[]
  onChange: (next: string[]) => void
  addLabel: string
  emptyText: string
}

function useListEditor(items: string[], onChange: (next: string[]) => void) {
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState("")
  const [editIndex, setEditIndex] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState("")

  const remove = (index: number) => onChange(items.filter((_, i) => i !== index))

  const commitAdd = () => {
    const value = draft.trim()
    if (value) onChange([...items, value])
    setDraft("")
    setAdding(false)
  }

  const startEdit = (index: number) => {
    setEditIndex(index)
    setEditDraft(items[index])
  }

  const commitEdit = () => {
    const value = editDraft.trim()
    if (value && editIndex !== null) {
      onChange(items.map((item, i) => (i === editIndex ? value : item)))
    }
    setEditIndex(null)
  }

  const cancelEdit = () => setEditIndex(null)

  return {
    adding,
    setAdding,
    draft,
    setDraft,
    editIndex,
    editDraft,
    setEditDraft,
    remove,
    commitAdd,
    startEdit,
    commitEdit,
    cancelEdit,
  }
}

export function ChipList({
  items,
  onChange,
  addLabel,
  emptyText,
  variant = "default",
}: ListEditorProps & { variant?: "default" | "warning" }) {
  const { t } = useTranslation()
  const ed = useListEditor(items, onChange)

  return (
    <div className="flex flex-wrap items-center gap-2">
      {items.map((item, i) =>
        ed.editIndex === i ? (
          <Input
            key={i}
            autoFocus
            value={ed.editDraft}
            onChange={(e) => ed.setEditDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") ed.commitEdit()
              if (e.key === "Escape") ed.cancelEdit()
            }}
            onBlur={ed.commitEdit}
            className="h-8 w-auto min-w-32"
            aria-label={t("personaDetail.editItem")}
          />
        ) : (
          <span
            key={i}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-muted px-2.5 text-sm"
          >
            {variant === "warning" && <Ban className="h-3.5 w-3.5 text-destructive" />}
            <button
              type="button"
              onClick={() => ed.startEdit(i)}
              className="outline-none"
              aria-label={t("personaDetail.editItem")}
            >
              {item}
            </button>
            <button
              type="button"
              onClick={() => ed.remove(i)}
              aria-label={t("personaDetail.removeItem")}
            >
              <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
            </button>
          </span>
        )
      )}
      {items.length === 0 && !ed.adding && (
        <span className="text-sm text-muted-foreground">{emptyText}</span>
      )}
      {ed.adding ? (
        <Input
          autoFocus
          value={ed.draft}
          onChange={(e) => ed.setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") ed.commitAdd()
            if (e.key === "Escape") ed.setAdding(false)
          }}
          onBlur={ed.commitAdd}
          className="h-8 w-40"
          placeholder={addLabel}
          aria-label={addLabel}
        />
      ) : (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 px-2 text-muted-foreground"
          onClick={() => ed.setAdding(true)}
        >
          <Plus className="h-3.5 w-3.5" />
          {addLabel}
        </Button>
      )}
    </div>
  )
}

export function QuoteCardList({ items, onChange, addLabel, emptyText }: ListEditorProps) {
  const { t } = useTranslation()
  const ed = useListEditor(items, onChange)

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="flex items-start gap-3 rounded-lg bg-muted p-4">
          <Quote className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          {ed.editIndex === i ? (
            <Textarea
              autoFocus
              rows={2}
              value={ed.editDraft}
              onChange={(e) => ed.setEditDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  ed.commitEdit()
                }
                if (e.key === "Escape") ed.cancelEdit()
              }}
              onBlur={ed.commitEdit}
              className="flex-1"
              aria-label={t("personaDetail.editItem")}
            />
          ) : (
            <button
              type="button"
              onClick={() => ed.startEdit(i)}
              className="flex-1 text-left text-sm leading-relaxed outline-none"
              aria-label={t("personaDetail.editItem")}
            >
              {item}
            </button>
          )}
          <button
            type="button"
            onClick={() => ed.remove(i)}
            aria-label={t("personaDetail.removeItem")}
            className="shrink-0"
          >
            <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
          </button>
        </div>
      ))}
      {items.length === 0 && !ed.adding && (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      )}
      {ed.adding ? (
        <Textarea
          autoFocus
          rows={2}
          value={ed.draft}
          onChange={(e) => ed.setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              ed.commitAdd()
            }
            if (e.key === "Escape") ed.setAdding(false)
          }}
          onBlur={ed.commitAdd}
          placeholder={addLabel}
          aria-label={addLabel}
        />
      ) : (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 px-2 text-muted-foreground"
          onClick={() => ed.setAdding(true)}
        >
          <Plus className="h-3.5 w-3.5" />
          {addLabel}
        </Button>
      )}
    </div>
  )
}
