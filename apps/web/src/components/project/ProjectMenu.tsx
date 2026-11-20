import { Ellipsis, Pencil, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import {
  DeleteProjectDialog,
  RenameProjectDialog,
} from "@/components/project/project-dialogs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface ProjectMenuProps {
  projectId: string
  title: string
  /** Hide destructive ops while a run is live — deleting mid-run races the
   * worker (same rule as ProjectCard). */
  runActive?: boolean
  /** Detail-page callbacks: rename updates local state; delete navigates
   * away (the page no longer exists). */
  onRenamed: (title: string) => void
  onDeleted: () => void
}

export function ProjectMenu({
  projectId,
  title,
  runActive,
  onRenamed,
  onDeleted,
}: ProjectMenuProps) {
  const { t } = useTranslation()
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  return (
    <>
      <div className="flex h-9 items-center">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                aria-label={t("projectMenu.open")}
                className="flex h-9 items-center gap-1 rounded-md pl-2 pr-1.5 transition-colors hover:bg-accent active:bg-accent"
              />
            }
          >
            <Ellipsis className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-44">
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={() => setRenameOpen(true)}>
                <Pencil className="mr-2 h-4 w-4" />
                {t("projects.rename")}
              </DropdownMenuItem>
              {!runActive && (
                <DropdownMenuItem
                  variant="destructive"
                  onClick={() => setDeleteOpen(true)}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  {t("common.delete")}
                </DropdownMenuItem>
              )}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <button
          type="button"
          onClick={() => setRenameOpen(true)}
          aria-label={t("projects.rename")}
          className="h-9 max-w-40 truncate rounded-md pl-1.5 pr-3 text-[13px] text-foreground transition-colors hover:bg-accent active:bg-accent"
        >
          {title}
        </button>
      </div>

      <RenameProjectDialog
        projectId={projectId}
        title={title}
        open={renameOpen}
        onOpenChange={setRenameOpen}
        onRenamed={onRenamed}
      />
      <DeleteProjectDialog
        projectId={projectId}
        title={title}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={onDeleted}
      />
    </>
  )
}
