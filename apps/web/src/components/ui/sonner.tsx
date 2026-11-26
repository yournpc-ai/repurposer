"use client"

import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, OctagonXIcon, Loader2Icon } from "@/components/ui/icons"

import { useTheme } from "@/lib/theme/ThemeProvider"

const Toaster = ({ ...props }: ToasterProps) => {
  const { resolved } = useTheme()

  const [host, setHost] = useState<HTMLDivElement | null>(null)
  useEffect(() => {
    // A native modal makes feedback mounted under body inert. Keep one live
    // region and move it with the active dialog so queued toasts survive.
    const region = document.createElement("div")
    region.style.display = "contents"
    const attach = () => {
      const layers = document.querySelectorAll<HTMLDialogElement>("dialog:modal")
      const parent =
        document.activeElement?.closest("dialog:modal") ?? layers[layers.length - 1] ?? document.body
      if (region.parentElement !== parent) parent.appendChild(region)
    }
    attach()
    setHost(region)
    document.addEventListener("repurposer:modal-change", attach)
    return () => {
      document.removeEventListener("repurposer:modal-change", attach)
      region.remove()
    }
  }, [])

  if (!host) return null
  return createPortal(
    <Sonner
      theme={resolved}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />,
    host,
  )
}

export { Toaster }
