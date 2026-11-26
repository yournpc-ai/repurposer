import "@/studio.css"
import { useRef } from "react"
import { Outlet, createFileRoute, useMatch } from "@tanstack/react-router"
import { createServerFn } from "@tanstack/react-start"

import { AppSidebar, SIDEBAR_COOKIE_NAME } from "@/components/app-sidebar"
import { StudioHeader } from "@/components/StudioHeader"
import { StudioHeaderProvider } from "@/components/StudioHeaderContext"
import { WorkbenchProvider } from "@/components/workbench/WorkbenchContext"
import { WorkbenchPane } from "@/components/workbench/WorkbenchPane"


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
  const projectMatch = useMatch({ from: "/_app/projects/$id", shouldThrow: false })
  const activeProjectId = projectMatch?.params.id ?? null
  const appRef = useRef<HTMLDivElement>(null)
  const shell = (
    <div ref={appRef} className="ui-as-app">
      <AppSidebar defaultOpen={sidebarOpen} />
      <main className="ui-as-main">
        <StudioHeader />
        <div className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </div>
      </main>
      {activeProjectId ? <WorkbenchPane containerRef={appRef} /> : null}
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
