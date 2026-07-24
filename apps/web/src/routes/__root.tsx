import { HeadContent, Scripts, createRootRoute, Outlet } from "@tanstack/react-router"
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools"
import { TanStackDevtools } from "@tanstack/react-devtools"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { I18nProvider } from "@/lib/i18n/I18nProvider"
import { ThemeProvider } from "@/lib/theme/ThemeProvider"

import { AuthProvider } from "@/components/AuthProvider"
import appCss from "../styles.css?url"

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Repurposer" },
    ],
    links: [{ rel: "stylesheet", href: appCss }],
    scripts: [
      {
        children: `
          (function(){
            try {
              const theme = localStorage.getItem('repurposer-theme') || 'system';
              const resolved = theme === 'system'
                ? 'dark'
                : theme;
              if (resolved !== 'dark') document.documentElement.classList.remove('dark');
              else document.documentElement.classList.add('dark');
            } catch(e){}
          })();
        `,
      },
    ],
  }),
  component: RootComponent,
  shellComponent: RootDocument,
})

function RootComponent() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <TooltipProvider>
          <AuthProvider>
            <Outlet />
            <Toaster />
          </AuthProvider>
        </TooltipProvider>
      </I18nProvider>
    </ThemeProvider>
  )
}

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        {import.meta.env.DEV && (
          <TanStackDevtools
            config={{ position: "bottom-right" }}
            plugins={[{ name: "Tanstack Router", render: <TanStackRouterDevtoolsPanel /> }]}
          />
        )}
        <Scripts />
      </body>
    </html>
  )
}
