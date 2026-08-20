import { createContext, useContext, useEffect, useState } from "react"

export type Theme = "light" | "dark" | "system"
export type ResolvedTheme = "light" | "dark"

export const THEME_STORAGE_KEY = "repurposer-theme"

type ThemeContextValue = {
  /** The user's stored preference: light, dark, or system. */
  theme: Theme
  /** The actual theme applied to the document. */
  resolved: ResolvedTheme
  setTheme: (theme: Theme) => void
  /** Toggle light/dark with a circular View Transition reveal from the event origin. */
  toggleTheme: (e?: { clientX: number; clientY: number }) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider")
  return ctx
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return false
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

function resolveTheme(theme: Theme): ResolvedTheme {
  if (theme === "system") return systemPrefersDark() ? "dark" : "light"
  return theme
}

/** Apply the resolved theme to <html> by toggling the `dark` class. */
function applyResolved(resolved: ResolvedTheme) {
  const root = document.documentElement
  root.classList.toggle("dark", resolved === "dark")
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (callback: () => void) => { ready: Promise<void> }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // SSR-safe: render with `dark` and reconcile on mount. The anti-FOUC inline
  // script in __root.tsx has already applied the correct class before paint.
  const [theme, setThemeState] = useState<Theme>("system")
  const [resolved, setResolved] = useState<ResolvedTheme>("dark")

  // On mount, read the stored preference and sync state with the DOM.
  useEffect(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY) as Theme | null
    const initial: Theme = stored === "light" || stored === "dark" || stored === "system" ? stored : "system"
    setThemeState(initial)
    const r = resolveTheme(initial)
    setResolved(r)
    // The anti-FOUC inline script paints `system` as dark unconditionally;
    // reconcile the DOM with the real resolution — without this a
    // light-system user stays dark and the first toggle is a visual no-op.
    applyResolved(r)
  }, [])

  // Follow system changes while preference is `system`.
  useEffect(() => {
    if (theme !== "system") return
    const mql = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      const next = mql.matches ? "dark" : "light"
      setResolved(next)
      applyResolved(next)
    }
    mql.addEventListener("change", onChange)
    return () => mql.removeEventListener("change", onChange)
  }, [theme])

  const setTheme = (next: Theme) => {
    setThemeState(next)
    localStorage.setItem(THEME_STORAGE_KEY, next)
    const r = resolveTheme(next)
    setResolved(r)
    applyResolved(r)
  }

  const toggleTheme = (e?: { clientX: number; clientY: number }) => {
    const nextResolved: ResolvedTheme = resolved === "dark" ? "light" : "dark"
    const apply = () => setTheme(nextResolved)

    const doc = document as ViewTransitionDocument
    if (!doc.startViewTransition || prefersReducedMotion()) {
      apply()
      return
    }

    const x = e?.clientX ?? window.innerWidth
    const y = e?.clientY ?? 0
    const radius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y)
    )

    const transition = doc.startViewTransition(apply)
    transition.ready.then(() => {
      document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${radius}px at ${x}px ${y}px)`,
          ],
        },
        {
          duration: 450,
          easing: "ease-in-out",
          pseudoElement: "::view-transition-new(root)",
        }
      )
    })
  }

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
