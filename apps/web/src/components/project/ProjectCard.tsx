import { Link } from "@tanstack/react-router"
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react"
import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { Spinner } from "@/components/ui/spinner-clean"
import { DeleteProjectDialog, RenameProjectDialog } from "@/components/project/project-dialogs"
import { Checkbox } from "@/components/ui/checkbox-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { DropdownMenu } from "@/components/ui/dropdown-menu-clean"
import { Card, CardHeader } from "@/components/ui/card-clean"
import { formatRelativeTime } from "@/lib/utils"

export interface Project {
  id: string
  title: string
  status: string
  created_at?: string | null
  updated_at?: string | null
}

interface ProjectCardProps {
  project: Project
  /** Refetch hook for the list after a rename/delete goes through. */
  onChanged?: () => void
  /** Bulk-selection state (page-owned). Selected cards keep the accent seat;
   * the circle itself hides on live-run projects (delete is refused mid-run,
   * same law as the ⋯ menu). */
  selectionDisabled?: boolean
  selected?: boolean
  onToggleSelect?: () => void
}

export function ProjectCard({ project, onChanged, selected, selectionDisabled, onToggleSelect }: ProjectCardProps) {
  const { t, i18n } = useTranslation()
  const menuTrigger = useRef<HTMLButtonElement>(null)
  const [renameOpen, setRenameOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  const active = project.status === "processing" || project.status === "uploading"
  const stageLabel = active ? t(`projects.status.${project.status}`) : null
  const when = project.updated_at ?? project.created_at
  const timeLabel = when ? formatRelativeTime(when, i18n.language) : null
  const bottomLine = [stageLabel, timeLabel].filter(Boolean).join(" · ")

  return (
    <>
      <div className="project-entry group relative">
        {!active && onToggleSelect && (
          <span className="project-checkbox" data-selected={selected || undefined}>
            <Checkbox
              aria-label={t("projects.selection.toggleNamed", { title: project.title })}
              disabled={selectionDisabled}
              checked={!!selected}
              onChange={onToggleSelect}
            />
          </span>
        )}
        <Card interactive selected={selected}>
          <CardHeader
            icon={
              <span className="grid size-8 place-items-center" aria-hidden="true">
                {active ? <Spinner size={20} /> : <FolderMark />}
              </span>
            }
            title={
              <Link to="/projects/$id" params={{ id: project.id }}>
                <span className="block truncate" title={project.title}>{project.title}</span>
              </Link>
            }
            description={bottomLine}
            action={
              <div className={active || !onToggleSelect ? undefined : "ps-7"}>
                <DropdownMenu
                  open={menuOpen}
                  onOpenChange={setMenuOpen}
                  align="end"
                  trigger={({ triggerProps }) => (
                    <IconButton
                      ref={menuTrigger}
                      {...triggerProps}
                      label={t("projects.menuMore")}
                      icon={<MoreHorizontal />}
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
                    ...(active
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
            }
          />
        </Card>
      </div>

      <RenameProjectDialog
        projectId={project.id}
        title={project.title}
        open={renameOpen}
        onOpenChange={setRenameOpen}
        onRenamed={() => onChanged?.()}
      />
      <DeleteProjectDialog
        projectId={project.id}
        title={project.title}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={() => onChanged?.()}
      />
    </>
  )
}

const FolderMark = () => (
  <svg className="size-8" viewBox="0 0 67 67" fill="none" aria-hidden="true">
    <path d="M11.17 15.35v15.36h44.67v-6.98c0-3.86-3.13-6.98-6.98-6.98H33.5l-3.93-5.89a5.58 5.58 0 0 0-4.64-2.49h-6.78c-3.86 0-6.98 3.13-6.98 6.98Z" fill="#00A1FF" />
    <path d="M33.5 16.75l-3.93-5.89a5.58 5.58 0 0 0-4.64-2.49h-6.78c-3.86 0-6.98 3.13-6.98 6.98v15.36h44.67v-6.98c0-3.86-3.13-6.98-6.98-6.98H33.5Zm0 0h-9.77" stroke="#00A1FF" strokeWidth="4.19" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M6.59 42.38c-1.05-5.26-1.57-7.89-.08-9.67l.31-.34c1.66-1.66 4.59-1.66 10.45-1.66h32.46c5.86 0 8.79 0 10.45 1.66l.31.34c1.49 1.78.97 4.41-.08 9.67-1.51 7.56-2.26 11.34-5.1 13.66l-.6.46c-3.01 2.13-7.23 2.13-15.66 2.13h-11.1c-8.43 0-12.64 0-15.66-2.13l-.6-.46c-2.84-2.32-3.6-6.1-5.1-13.66Z" fill="#3CC7FF" stroke="#3CC7FF" strokeWidth="4.19" />
  </svg>
);
