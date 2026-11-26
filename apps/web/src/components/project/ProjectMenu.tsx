import { Ellipsis, Pencil, Trash2 } from "@/components/ui/icons"
import { IconButton } from "@/components/ui/icon-button-clean"
import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { DeleteProjectDialog, RenameProjectDialog } from "@/components/project/project-dialogs"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"

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

export function ProjectMenu({ projectId, title, runActive, onRenamed, onDeleted }: ProjectMenuProps) {
  const { t } = useTranslation()
  const menuTrigger = useRef<HTMLButtonElement>(null)
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  return (
    <>
      <div className="flex h-8 min-w-0 items-center gap-0.5">
        <button
          type="button"
          onClick={() => setRenameOpen(true)}
          aria-label={t("projects.rename")}
          className="h-8 min-w-0 max-w-56 truncate rounded-md px-2 text-[13px] font-medium text-foreground transition-colors hover:bg-accent active:bg-accent"
        >
          {title}
        </button>
        <DropdownMenu
          align="start"
          trigger={({ triggerProps }) => (
            <IconButton
              ref={menuTrigger}
              {...triggerProps}
              size="sm"
              icon={<Ellipsis />}
              label={t("projectMenu.open")}
            />
          )}
          items={[
            {
              label: t("projects.rename"),
              icon: <Pencil />,
              onSelect: () => {
                menuTrigger.current?.focus()
                setRenameOpen(true)
              },
            },
            ...(runActive
              ? []
              : [
                  {
                    label: t("common.delete"),
                    danger: true,
                    icon: <Trash2 />,
                    onSelect: () => {
                      menuTrigger.current?.focus()
                      setDeleteOpen(true)
                    },
                  },
                ]),
          ]}
        />
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
