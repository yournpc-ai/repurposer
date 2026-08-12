import { useNavigate } from "@tanstack/react-router"
import { ArrowLeft, ChevronDown, Pencil, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { LogoMark } from "@/components/LogoMark"
import {
  DeleteProjectDialog,
  RenameProjectDialog,
} from "@/components/project/project-dialogs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
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

/** The fullscreen project page's top-left chrome (ADR-041 canvas world): a
 * frosted pill — brand-mark trigger opens the project menu (navigation +
 * project-level ops), the truncated title rides beside it. */
export function ProjectMenu({
  projectId,
  title,
  runActive,
  onRenamed,
  onDeleted,
}: ProjectMenuProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  return (
    <>
      <div className="overlay-surface flex h-9 items-center rounded-md">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                aria-label={t("projectMenu.open")}
                className="flex h-9 items-center gap-1 rounded-l-md pl-2 pr-1.5 transition-colors hover:bg-accent"
              />
            }
          >
            <LogoMark className="h-5 w-5" />
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-44">
            <DropdownMenuGroup>
              <DropdownMenuItem
                onClick={() => navigate({ to: "/projects" })}
              >
                <ArrowLeft className="mr-2 h-4 w-4" />
                {t("projectMenu.backToProjects")}
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
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
        <span className="max-w-40 truncate pl-1.5 pr-3 text-sm">{title}</span>
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
