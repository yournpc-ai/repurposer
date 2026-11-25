/** Assistant prose — markdown, no bubble (Opus pattern). Streamdown parses
 * incomplete markdown safely mid-stream, so the live preview and the settled
 * message share one renderer. */

import { useMemo, type ComponentPropsWithoutRef } from "react"
import { Film, Image as ImageIcon, Play, Sparkles } from "lucide-react"
import { defaultUrlTransform, Streamdown, type Components, type UrlTransform } from "streamdown"
import { useTranslation } from "react-i18next"

import {
  parseWorkbenchHref,
  useOptionalWorkbench,
  type WorkbenchOpenTarget,
} from "@/components/workbench/WorkbenchContext"
import { cn } from "@/lib/utils"
import { shouldAnimateEntrance } from "../timeline/reveal"

const workbenchSafeUrlTransform: UrlTransform = (url, key, node) => {
  if (typeof url === "string" && url.trim().startsWith("#workbench:")) {
    return url.trim()
  }
  return defaultUrlTransform(url, key, node)
}

function chipIcon(target: WorkbenchOpenTarget) {
  if (target.tab === "slots") return <Sparkles className="size-3 shrink-0" />
  if (target.tab === "inspector") return <ImageIcon className="size-3 shrink-0" />
  if (target.outputId) return <Play className="size-3 shrink-0" />
  return <Film className="size-3 shrink-0" />
}

export function AssistantText({
  text,
  streaming,
  hydrated,
}: {
  text: string
  streaming?: boolean
  hydrated?: boolean
}) {
  const { t } = useTranslation()
  const workbench = useOptionalWorkbench()

  const components = useMemo<Components>(() => {
    return {
      a: ({ href, children, className, ...rest }: ComponentPropsWithoutRef<"a">) => {
        const target = parseWorkbenchHref(href)
        if (target) {
          return (
            <button
              type="button"
              data-workbench-href={href}
              onClick={() => workbench?.openWorkbench(target)}
              title={t("workbench.openInWorkbench")}
              className={cn(
                "mx-0.5 inline-flex items-center gap-1 rounded-md border border-border/80 bg-muted/60 px-1.5 py-0.5 align-baseline text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring",
                !workbench && "cursor-default opacity-80",
              )}
            >
              {chipIcon(target)}
              <span>{children}</span>
            </button>
          )
        }
        return (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={cn("underline underline-offset-2 hover:text-foreground", className)}
            {...rest}
          >
            {children}
          </a>
        )
      },
      table: ({ children, className, ...rest }) => {
        const { node: _node, ...tableProps } = rest as ComponentPropsWithoutRef<"table"> & { node?: unknown }
        return (
          <div className="ui-th-table-breakout" data-breakout-table="true">
            <div className="ui-th-table-frame thin-scroll">
              <table className={cn("ui-th-table", className)} {...tableProps}>
                {children}
              </table>
            </div>
          </div>
        )
      },
      thead: ({ children, className, ...rest }) => {
        const { node: _node, ...theadProps } = rest as ComponentPropsWithoutRef<"thead"> & { node?: unknown }
        return (
          <thead className={cn("ui-th-table__head", className)} {...theadProps}>
            {children}
          </thead>
        )
      },
      tbody: ({ children, className, ...rest }) => {
        const { node: _node, ...tbodyProps } = rest as ComponentPropsWithoutRef<"tbody"> & { node?: unknown }
        return (
          <tbody className={cn("ui-th-table__body", className)} {...tbodyProps}>
            {children}
          </tbody>
        )
      },
      tr: ({ children, className, ...rest }) => {
        const { node: _node, ...trProps } = rest as ComponentPropsWithoutRef<"tr"> & { node?: unknown }
        return (
          <tr className={cn("ui-th-table__row", className)} {...trProps}>
            {children}
          </tr>
        )
      },
      th: ({ children, className, ...rest }) => {
        const { node: _node, ...thProps } = rest as ComponentPropsWithoutRef<"th"> & { node?: unknown }
        return (
          <th className={cn("ui-th-table__th", className)} {...thProps}>
            {children}
          </th>
        )
      },
      td: ({ children, className, ...rest }) => {
        const { node: _node, ...tdProps } = rest as ComponentPropsWithoutRef<"td"> & { node?: unknown }
        return (
          <td className={cn("ui-th-table__td", className)} {...tdProps}>
            {children}
          </td>
        )
      },
    }
  }, [workbench, t])

  return (
    <div className="ui-th-message">
      <Streamdown
        mode={streaming ? "streaming" : "static"}
        isAnimating={streaming}
        components={components}
        urlTransform={workbenchSafeUrlTransform}
        className={cn(
          "text-sm leading-relaxed",
          shouldAnimateEntrance(hydrated) &&
            "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300",
        )}
      >
        {text}
      </Streamdown>
    </div>
  )
}
