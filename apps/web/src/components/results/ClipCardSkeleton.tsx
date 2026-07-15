import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export function ClipCardSkeleton() {
  return (
    <Card className="flex flex-col gap-0 overflow-hidden ring-1 ring-border">
      <div className="relative aspect-square bg-muted">
        <Skeleton className="absolute inset-0 rounded-none" />
      </div>
      <div className="space-y-3 p-3">
        <Skeleton className="h-4 w-3/4" />
        <div className="flex gap-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-3 w-16" />
        </div>
      </div>
    </Card>
  )
}
