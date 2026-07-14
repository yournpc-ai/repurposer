import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export function DerivativeCardSkeleton() {
  return (
    <Card className="space-y-4 p-4 ring-1 ring-border shadow-xl">
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-12" />
        <Skeleton className="h-4 w-24" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
      </div>
    </Card>
  )
}
