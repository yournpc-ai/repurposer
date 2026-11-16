"use client"

import { CreditsPill } from "@/components/credits/CreditsPill"
import { ProjectMenu } from "@/components/project/ProjectMenu"

export function ProjectHeader({
  projectId,
  title,
  runActive,
  onRenamed,
  onDeleted,
  creditsRefreshKey,
}: {
  projectId: string
  title: string
  runActive?: boolean
  onRenamed: (title: string) => void
  onDeleted: () => void
  creditsRefreshKey: string
}) {
  return (
    <header className="fixed inset-x-0 top-0 z-[60] flex h-14 items-center justify-between gap-2 px-3 md:px-4">
      <ProjectMenu
        projectId={projectId}
        title={title}
        runActive={runActive}
        onRenamed={onRenamed}
        onDeleted={onDeleted}
      />

      <CreditsPill refreshKey={creditsRefreshKey} />
    </header>
  )
}
