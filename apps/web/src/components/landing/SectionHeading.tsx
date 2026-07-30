import { InView } from "@/components/landing/motion"
import { cn } from "@/lib/utils"
import type { ReactNode } from "react"

/** Shared landing section heading: title + optional description, in-view reveal. */
export function SectionHeading({
  title,
  description,
  align = "left",
}: {
  title: string
  description?: ReactNode
  align?: "left" | "center"
}): ReactNode {
  const centered = align === "center"

  return (
    <InView
      className={cn(
        "max-w-2xl",
        centered && "mx-auto flex flex-col items-center text-center"
      )}
    >
      <h2 className="text-balance font-display text-[clamp(30px,4.5vw,52px)] font-medium leading-[1.05] tracking-tight text-foreground">
        {title}
      </h2>
      {description && (
        <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}
    </InView>
  )
}
