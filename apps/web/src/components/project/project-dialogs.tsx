import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiDelete, apiPost, apiPut } from "@/lib/api"
import { Button } from "@/components/ui/button-clean"
import { AlertDialog, Dialog } from "@/components/ui/dialog-clean"
import { TextField } from "@/components/ui/text-field-clean"

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
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="sm"
      closeLabel={t("common.close")}
      title={t("projects.renameTitle")}
    >
      <TextField
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") handleRename()
        }}
        aria-label={t("projects.renameTitle")}
        placeholder={t("projects.renamePlaceholder")}
        autoFocus
      />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={() => onOpenChange(false)}>
          {t("common.cancel")}
        </Button>
        <Button size="sm" disabled={!value.trim() || busy} onClick={handleRename}>
          {busy ? t("common.saving") : t("common.save")}
        </Button>
      </div>
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
  return (
    <AlertDialog
      open={open}
      onOpenChange={onOpenChange}
      danger
      title={t("projects.deleteConfirm")}
      description={t("projects.deleteDesc", { title })}
      cancelLabel={t("common.cancel")}
      confirmLabel={t("common.delete")}
      onConfirm={async () => {
        const response = await apiDelete(`/api/v1/projects/${projectId}`)
        if (!response.ok) throw new Error("Project deletion failed")
        onDeleted()
      }}
    />
  )
}

interface DeleteProjectsDialogProps {
  /** The bulk selection — one bulk-delete call, one server-side transaction. */
  projectIds: string[]
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called after the pass finishes (the list refetches, selection clears). */
  onDeleted: () => void
}

export function DeleteProjectsDialog({
  projectIds,
  open,
  onOpenChange,
  onDeleted,
}: DeleteProjectsDialogProps) {
  const { t } = useTranslation()
  return (
    <AlertDialog
      open={open}
      onOpenChange={onOpenChange}
      danger
      title={t("projects.selection.deleteConfirm", { count: projectIds.length })}
      description={t("projects.selection.deleteDesc")}
      cancelLabel={t("common.cancel")}
      confirmLabel={t("common.delete")}
      onConfirm={async () => {
        const response = await apiPost("/api/v1/projects/bulk-delete", { ids: projectIds })
        if (!response.ok) throw new Error("Bulk project deletion failed")
        onDeleted()
      }}
    />
  )
}
