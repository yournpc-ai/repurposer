import { useSyncExternalStore } from "react"

const QUERY = "(prefers-reduced-motion: reduce)"

/** True when the user prefers reduced motion. SSR-safe (false on the
 * server); every animation gate in the app reads this one hook. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia(QUERY)
      mq.addEventListener("change", onChange)
      return () => mq.removeEventListener("change", onChange)
    },
    () => window.matchMedia(QUERY).matches,
    () => false
  )
}
