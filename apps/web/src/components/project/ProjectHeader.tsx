"use client"

import { Link } from "@tanstack/react-router"
import { ArrowLeft } from "lucide-react"
import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"
import { CreditsPill } from "@/components/credits/CreditsPill"
import { ProjectMenu } from "@/components/project/ProjectMenu"

/**
 * The project page's full-width header (2026-10-15 user ruling — Pexo
 * parity, supersedes the floating-corner chrome experiment): a TRANSPARENT
 * bare bar — NO glass (the dock-surface band read as an off-color strip
 * over the dark canvas, same-day reversal). Nothing ever scrolls under it
 * by construction: the chat stage's scroller starts BELOW the bar (the
 * stage wrapper carries pt-14 in the full form), so a backdrop here would
 * have nothing to do. LEFT = the two-form machine (pre-run back button ↔
 * worldLive ProjectMenu, the same crossfade as the floating-pill era);
 * RIGHT = the credits read surface. All controls bare.
 *
 * Fixed + z-[60]: the page's world is the ChatDock's fixed inset-0 z-50
 * overlay, so an in-flow header would paint UNDER the world it frames.
 * On <md it replaces the MobileHeader visually (the ChatDock overlay covers
 * that one anyway); the canvas's top-right chrome (zoom pill / inspector)
 * keeps its header-cleared seats below the bar.
 */
export function ProjectHeader({
  projectId,
  title,
  worldLive,
  runActive,
  onRenamed,
  onDeleted,
  creditsRefreshKey,
}: {
  projectId: string
  title: string
  /** The two-form machine's driver: pre-generation = plain back button;
   * the graph world's arrival crossfades it into the full ProjectMenu. */
  worldLive: boolean
  runActive?: boolean
  onRenamed: (title: string) => void
  onDeleted: () => void
  creditsRefreshKey: string
}) {
  const { t } = useTranslation()
  return (
    <header className="fixed inset-x-0 top-0 z-[60] flex h-14 items-center justify-between gap-2 px-3 md:px-4">
      {/* The two-form machine (2026-09-02): both forms stacked in one slot —
          the active one in flow, the inactive absolutely overlaid (hence
          `relative`) — so the crossfade never shifts layout. */}
      <div className="relative flex min-w-0 items-center">
        <div
          className={cn(
            "transition-[opacity,transform] duration-500 ease-out motion-reduce:transition-none",
            worldLive
              ? "opacity-100"
              : "pointer-events-none absolute left-0 top-0 -translate-x-2 opacity-0"
          )}
          aria-hidden={!worldLive}
        >
          <ProjectMenu
            projectId={projectId}
            title={title}
            runActive={runActive}
            onRenamed={onRenamed}
            onDeleted={onDeleted}
          />
        </div>
        <div
          className={cn(
            "transition-[opacity,transform] duration-500 ease-out motion-reduce:transition-none",
            worldLive
              ? "pointer-events-none absolute left-0 top-0 -translate-x-2 opacity-0"
              : "opacity-100"
          )}
          aria-hidden={worldLive}
        >
          <Link
            to="/projects"
            tabIndex={worldLive ? -1 : 0}
            className="flex h-9 items-center gap-1.5 rounded-md pl-2 pr-3 text-[13px] transition-colors hover:bg-accent active:bg-accent"
          >
            {/* Breadcrumb recipe: the icon stays a muted ornament, the label
                stays foreground — 灰给信息，动作和身份保持前景色 (the credits
                pill's quiet readout is the opposite semantic). */}
            <ArrowLeft className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-foreground">{t("projectMenu.backShort")}</span>
          </Link>
        </div>
      </div>

      <CreditsPill refreshKey={creditsRefreshKey} />
    </header>
  )
}
