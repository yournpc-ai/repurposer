import { Outlet, createFileRoute } from "@tanstack/react-router"

import { AppSidebar } from "@/components/app-sidebar"
import { AppHeader } from "@/components/AppHeader"
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"

/**
 * Pathless layout route for the authenticated workbench: everything under
 * `_app` gets the sidebar chrome. The public landing page (`/`) lives
 * outside this layout.
 */
export const Route = createFileRoute("/_app")({
  component: AppLayout,
})

function AppLayout() {
  return (
    <SidebarProvider defaultOpen={false}>
      <AppSidebar />
      <SidebarInset className="relative overflow-x-clip">
        <AppHeader />
        <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
          <div className="absolute -left-[20%] -top-[10%] h-[50%] w-[50%] rounded-full bg-primary/5 blur-[120px]" />
          <div className="absolute -right-[20%] top-[20%] h-[40%] w-[40%] rounded-full bg-primary/3 blur-[100px]" />
        </div>
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  )
}
