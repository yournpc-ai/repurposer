import "@/studio.css"
import { Outlet, createFileRoute } from "@tanstack/react-router"
import { createServerFn } from "@tanstack/react-start"

import { AppSidebar, SIDEBAR_COOKIE_NAME } from "@/components/app-sidebar"
import { StudioHeader } from "@/components/StudioHeader"
import { StudioHeaderProvider } from "@/components/StudioHeaderContext"


// Server-module imports are denied in the client bundle (same pattern as the
// root route's language cookie read).
const readSidebarCookieOnServer = createServerFn({ method: "GET" }).handler(
  async (): Promise<boolean> => {
    const { getCookie } = await import("@tanstack/react-start/server")
    return getCookie(SIDEBAR_COOKIE_NAME) === "true"
  }
)

export const Route = createFileRoute("/_app")({
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
  return (
    <StudioHeaderProvider>
      <div className="ui-as-app">
        <AppSidebar defaultOpen={sidebarOpen} />
        <main className="ui-as-main">
          <StudioHeader />
          <div className="min-h-0 flex-1 overflow-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </StudioHeaderProvider>
  )
}
