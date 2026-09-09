/** Auth context + hook, split from AuthProvider.tsx so the provider file
 * exports only components. A mixed component/hook export breaks Vite Fast
 * Refresh — invalidating AuthProvider used to remount the tree with
 * CreditsPill outside the provider ("useAuth must be used within
 * AuthProvider" on every HMR, 2026-09-10). */

import { createContext, useContext } from "react"

export interface AuthContextValue {
  isAuthenticated: boolean
  loginOpen: boolean
  setLoginOpen: (open: boolean) => void
  requireAuth: (callback?: () => void | Promise<void>) => void | Promise<void>
  refreshAuth: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider")
  }
  return ctx
}
