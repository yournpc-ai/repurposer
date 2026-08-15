import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { isAuthenticated } from "@/lib/auth"
import { UNAUTHORIZED_EVENT } from "@/lib/api"
import { LoginDialog } from "@/components/LoginDialog"

interface AuthContextValue {
  isAuthenticated: boolean
  loginOpen: boolean
  setLoginOpen: (open: boolean) => void
  requireAuth: (callback?: () => void | Promise<void>) => void | Promise<void>
  refreshAuth: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const PUBLIC_PATHS = new Set(["/"])

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(false)
  const [loginOpen, setLoginOpen] = useState(false)
  const [mounted, setMounted] = useState(false)
  const routerState = useRouterState()
  const pathname = routerState.location.pathname
  const navigate = useNavigate()

  const refreshAuth = useCallback(() => {
    setAuthed(isAuthenticated())
  }, [])

  useEffect(() => {
    setMounted(true)
    refreshAuth()
  }, [refreshAuth])

  // Any API call that answers 401 (expired/invalid token) forces re-login.
  useEffect(() => {
    const onUnauthorized = () => {
      refreshAuth()
      setLoginOpen(true)
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [refreshAuth])

  const requireAuth = useCallback(
    async (callback?: () => void | Promise<void>) => {
      if (isAuthenticated()) {
        await callback?.()
      } else {
        setLoginOpen(true)
      }
    },
    []
  )

  const isPublicPath = PUBLIC_PATHS.has(pathname)
  const shouldBlock = mounted && !isPublicPath && !authed

  useEffect(() => {
    if (shouldBlock) {
      setLoginOpen(true)
    }
  }, [shouldBlock])

  const handleLoginOpenChange = useCallback(
    (open: boolean) => {
      setLoginOpen(open)
      // Bounce home only when the dialog closed WITHOUT a login. `shouldBlock`
      // is stale here on the success path (setAuth → close → refreshAuth:
      // the authed state refreshes after this callback), so read the storage
      // synchronously — setAuth has already landed by the time we close.
      if (!open && shouldBlock && !isAuthenticated()) {
        navigate({ to: "/" })
      }
    },
    [shouldBlock, navigate]
  )

  const handleLoginSuccess = useCallback(() => {
    refreshAuth()
    // The landing page is marketing-only — a fresh login there has nothing
    // to stay for, so carry the user into the studio. On protected pages the
    // close handler above already keeps the user in place.
    if (PUBLIC_PATHS.has(pathname)) {
      void navigate({ to: "/home" })
    }
  }, [refreshAuth, navigate, pathname])

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: authed,
        loginOpen,
        setLoginOpen,
        requireAuth,
        refreshAuth,
      }}
    >
      {children}
      <LoginDialog
        open={loginOpen}
        onOpenChange={handleLoginOpenChange}
        onSuccess={handleLoginSuccess}
      />
      {shouldBlock && (
        <div className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm" />
      )}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider")
  }
  return ctx
}
