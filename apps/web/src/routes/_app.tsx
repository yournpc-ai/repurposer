import "@/studio.css"
import { useEffect, useRef } from "react"
import {
  Outlet,
  createFileRoute,
  useLocation,
  useMatch,
  useNavigate,
} from "@tanstack/react-router"
import { createServerFn } from "@tanstack/react-start"

import { AppSidebar, SIDEBAR_COOKIE_NAME } from "@/components/app-sidebar"
import { StudioHeader } from "@/components/StudioHeader"
import { StudioHeaderProvider } from "@/components/StudioHeaderContext"
import {
  useSettingsDialog,
  type CheckoutReturn,
  type CheckoutReturnSurface,
} from "@/components/settings/settings-dialog-context"
import { WorkbenchProvider } from "@/components/workbench/WorkbenchContext"
import { WorkbenchPane } from "@/components/workbench/WorkbenchPane"

interface AppCheckoutSearch {
  checkout?: CheckoutReturn["outcome"]
  order_id?: string
  checkout_surface?: CheckoutReturnSurface
}


// Server-module imports are denied in the client bundle (same pattern as the
// root route's language cookie read).
const readSidebarCookieOnServer = createServerFn({ method: "GET" }).handler(
  async (): Promise<boolean> => {
    const { getCookie } = await import("@tanstack/react-start/server")
    return getCookie(SIDEBAR_COOKIE_NAME) === "true"
  }
)

export const Route = createFileRoute("/_app")({
  validateSearch: (search: Record<string, unknown>): AppCheckoutSearch => {
    const next: AppCheckoutSearch = {}
    if (search.checkout === "success" || search.checkout === "cancelled") {
      next.checkout = search.checkout
    }
    if (typeof search.order_id === "string" && search.order_id.trim()) {
      next.order_id = search.order_id.trim()
    }
    if (search.checkout_surface === "settings") {
      next.checkout_surface = "settings"
    }
    return next
  },
  loader: async (): Promise<{ sidebarOpen: boolean }> => {
    if (typeof document === "undefined") {
      return { sidebarOpen: await readSidebarCookieOnServer() }
    }
    const entry = document.cookie
      .split("; ")
      .find((row) => row.startsWith(`${SIDEBAR_COOKIE_NAME}=`))
    return { sidebarOpen: entry?.split("=")[1] === "true" }
  },
  component: AppLayout,
})

function AppLayout() {
  const { sidebarOpen } = Route.useLoaderData()
  const { checkout, order_id: orderId, checkout_surface: checkoutSurface } = Route.useSearch()
  const location = useLocation()
  const navigate = useNavigate()
  const { handleCheckoutReturn } = useSettingsDialog()
  const projectMatch = useMatch({ from: "/_app/projects/$id", shouldThrow: false })
  const activeProjectId = projectMatch?.params.id ?? null
  const appRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!checkout || !orderId) return
    // The legacy /settings callback shim handles its own redirect to /home.
    if (location.pathname === "/settings") return
    handleCheckoutReturn({
      orderId,
      outcome: checkout,
      surface: checkoutSurface ?? "inline",
    })
    void navigate({
      to: ".",
      search: (prev) => {
        const next = { ...(prev as Record<string, unknown>) }
        delete next.checkout
        delete next.order_id
        delete next.checkout_surface
        return next
      },
      replace: true,
    })
  }, [checkout, orderId, checkoutSurface, location.pathname, handleCheckoutReturn, navigate])
  const shell = (
    <div ref={appRef} className="ui-as-app">
      <AppSidebar defaultOpen={sidebarOpen} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <StudioHeader />
        <div className="flex min-h-0 min-w-0 flex-1">
          <main className="ui-as-main">
            <div className="min-h-0 flex-1 overflow-auto">
              <Outlet />
            </div>
          </main>
          {activeProjectId ? (
            <WorkbenchPane containerRef={appRef} tabsInHeader />
          ) : null}
        </div>
      </div>
    </div>
  )
  return (
    <StudioHeaderProvider>
      {activeProjectId ? (
        <WorkbenchProvider key={activeProjectId} projectId={activeProjectId}>
          {shell}
        </WorkbenchProvider>
      ) : (
        shell
      )}
    </StudioHeaderProvider>
  )
}
