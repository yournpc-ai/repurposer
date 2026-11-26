"use client"

import { Loading, Skeleton } from "@/components/ui/skeleton-clean"

/**
 * AffectUI Clean loading skeleton for the project chat thread.
 * Matches the real `.ui-th-body` / `.ui-th-col` column width and bottom
 * composer geometry so fast loads stay silent (150ms delay) and slower loads
 * transition into the real conversation without layout jump.
 */
export function ThreadLoadingSkeleton({
  label,
  includeComposer = false,
}: {
  label: string
  includeComposer?: boolean
}) {
  return (
    <Loading
      label={label}
      className={
        includeComposer
          ? "ui-th-body h-full bg-background"
          : "flex h-full min-h-0 flex-1 flex-col"
      }
    >
      <div className="ui-th-lane min-h-0 flex-1 overflow-hidden">
        <div className="ui-th-col flex flex-col gap-7 pt-6">
          {/* Turn 1: User bubble */}
          <div className="flex justify-end">
            <Skeleton width={236} height={40} radius={18} />
          </div>

          {/* Turn 1: Assistant response + media card */}
          <div className="flex flex-col gap-3">
            <Skeleton width={132} height={14} radius={6} />
            <div className="flex flex-col gap-2">
              <Skeleton line width="92%" height={11} />
              <Skeleton line width="84%" height={11} />
              <Skeleton line width="58%" height={11} />
            </div>
            <Skeleton width={320} height={180} radius={12} className="mt-1" />
          </div>

          {/* Turn 2: Follow-up user bubble + concise reply */}
          <div className="flex justify-end">
            <Skeleton width={172} height={38} radius={18} />
          </div>
          <div className="flex flex-col gap-2">
            <Skeleton line width="76%" height={11} />
            <Skeleton line width="46%" height={11} />
          </div>
        </div>
      </div>

      {includeComposer ? (
        <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-4 pt-2 md:px-6">
          <div className="flex flex-col gap-3 rounded-[22px] border border-subtle bg-card px-3.5 py-3">
            <Skeleton line width="38%" height={12} />
            <div className="flex items-center justify-between pt-2">
              <Skeleton width={32} height={32} radius="50%" />
              <Skeleton width={32} height={32} radius="50%" />
            </div>
          </div>
        </div>
      ) : null}
    </Loading>
  )
}
