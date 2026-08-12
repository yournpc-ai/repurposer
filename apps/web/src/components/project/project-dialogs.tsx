import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiDelete, apiPut } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"

/** Shared rename/delete dialogs for a project — used by ProjectCard (list)
 * and ProjectMenu (detail page chrome). The parent owns open state and gets
 * an onChanged callback after the mutation goes through. */

interface RenameProjectDialogProps {
  projectId: string
  title: string
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called with the new title after a successful rename. */
  onRenamed: (title: string) => void
}

export function RenameProjectDialog({
  projectId,
  title,
  open,
  onOpenChange,
  onRenamed,
}: RenameProjectDialogProps) {
  const { t } = useTranslation()
  const [value, setValue] = useState(title)
  const [busy, setBusy] = useState(false)

  // Re-seed the draft every time the dialog opens — the parent keeps this
  // mounted, and the title may have changed since the last open.
  useEffect(() => {
    if (open) setValue(title)
  }, [open, title])

  const handleRename = async () => {
    const next = value.trim()
    if (!next || busy) return
    if (next === title) {
      onOpenChange(false)
      return
    }
    setBusy(true)
    try {
      const res = await apiPut(`/api/v1/projects/${projectId}`, { title: next })
      if (res.ok) {
        onOpenChange(false)
        onRenamed(next)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("projects.renameTitle")}</DialogTitle>
        </DialogHeader>
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleRename()
          }}
          placeholder={t("projects.renamePlaceholder")}
          autoFocus
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button disabled={!value.trim() || busy} onClick={handleRename}>
            {busy ? t("common.saving") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface DeleteProjectDialogProps {
  projectId: string
  title: string
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called after a successful delete (the list refetches; the detail page
   * navigates away). */
  onDeleted: () => void
}

export function DeleteProjectDialog({
  projectId,
  title,
  open,
  onOpenChange,
  onDeleted,
}: DeleteProjectDialogProps) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)

  const handleDelete = async () => {
    if (busy) return
    setBusy(true)
    try {
      const res = await apiDelete(`/api/v1/projects/${projectId}`)
      if (res.ok) {
        onOpenChange(false)
        onDeleted()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("projects.deleteConfirm")}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {t("projects.deleteDesc", { title })}
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button variant="destructive" disabled={busy} onClick={handleDelete}>
            {busy ? t("common.loading") : t("common.delete")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
