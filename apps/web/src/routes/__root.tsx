import { HeadContent, Scripts, createRootRoute, Outlet } from "@tanstack/react-router"
import { createServerFn } from "@tanstack/react-start"
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools"
import { TanStackDevtools } from "@tanstack/react-devtools"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { I18nProvider } from "@/lib/i18n/I18nProvider"
import { ThemeProvider } from "@/lib/theme/ThemeProvider"

import { AuthProvider } from "@/components/AuthProvider"
import { LANG_COOKIE, normalizeLocale, type Locale } from "@/lib/i18n"
import appCss from "../styles.css?url"

// Server-module imports are denied in the client bundle (import-protection),
// even behind a dynamic import — the cookie read crosses via a server fn,
// whose handler is eliminated from the client build.
const readLangCookieOnServer = createServerFn({ method: "GET" }).handler(
  async (): Promise<Locale | null> => {
    const { getCookie } = await import("@tanstack/react-start/server")
    return normalizeLocale(getCookie(LANG_COOKIE))
  }
)

export const Route = createRootRoute({
  loader: async (): Promise<{ lang: Locale | null }> => {
    // SSR: read the language cookie so the server renders in the user's
    // language — the first client render reads the same cookie, so hydration
    // never sees a language switch. On client navigations the mounted
    // provider keeps its own language; this value is unused there.
    if (typeof document === "undefined") {
      return { lang: await readLangCookieOnServer() }
    }
    return { lang: null }
  },
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Repurposer" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      // Brand icons: SVG (dark-mode aware) for modern browsers, PNG fallbacks
      // for Safari tabs, apple-touch for iOS. Source of truth: LogoMark.tsx.
      { rel: "icon", type: "image/svg+xml", href: "/favicon.svg" },
      { rel: "icon", type: "image/png", sizes: "32x32", href: "/icon-32.png" },
      { rel: "icon", type: "image/png", sizes: "16x16", href: "/icon-16.png" },
      { rel: "apple-touch-icon", href: "/icon-180.png" },
      { rel: "manifest", href: "/manifest.json" },
    ],
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
  const { lang } = Route.useLoaderData()
  return (
    <ThemeProvider>
      <I18nProvider lang={lang}>
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
  // SSR renders in the cookie language — the document element must say the
  // same (search engines / screen readers read this, never the i18n state).
  const { lang } = Route.useLoaderData()
  return (
    <html lang={lang ?? "en"} suppressHydrationWarning>
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
