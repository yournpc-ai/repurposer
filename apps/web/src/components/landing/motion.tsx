import { motion, type MotionProps, type Variants } from "motion/react"
import {
  createContext,
  useContext,
  useSyncExternalStore,
  type ReactNode,
} from "react"

/**
 * Landing-page motion kit, ported from the Cortex template. Scoped to the
 * landing route on purpose — the workbench uses motion/react's own hooks.
 *
 * Every scroll scene consumes `useReducedMotion` from here and ships a static
 * fallback, so the whole page stays usable under prefers-reduced-motion.
 */

function subscribeToReducedMotion(callback: () => void): () => void {
  const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)")
  mediaQuery.addEventListener("change", callback)
  return () => mediaQuery.removeEventListener("change", callback)
}

const ReducedMotionContext = createContext<boolean>(false)

export function useReducedMotion(): boolean {
  return useContext(ReducedMotionContext)
}

export function ReducedMotionProvider({
  children,
}: {
  children: ReactNode
}): ReactNode {
  const prefersReducedMotion = useSyncExternalStore(
    subscribeToReducedMotion,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false
  )

  return (
    <ReducedMotionContext.Provider value={prefersReducedMotion}>
      {children}
    </ReducedMotionContext.Provider>
  )
}

function subscribeToMinWidth(query: string) {
  return (callback: () => void): (() => void) => {
    const mediaQuery = window.matchMedia(query)
    mediaQuery.addEventListener("change", callback)
    return () => mediaQuery.removeEventListener("change", callback)
  }
}

export function useIsDesktop(): boolean {
  // lg breakpoint: the pinned AppShowcase needs room for its browser frame,
  // which is far wider than the template's phone mock.
  const query = "(min-width: 1024px)"
  return useSyncExternalStore(
    subscribeToMinWidth(query),
    () => window.matchMedia(query).matches,
    () => true
  )
}

export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
}

export const reducedMotionVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
}

export const softEase = [0.22, 1, 0.36, 1] as const

/** Reveal-on-view wrapper shared by section headings and list rows. */
export function InView({
  variants = fadeInUp,
  children,
  className,
  transition,
  ...props
}: {
  variants?: Variants
  children?: ReactNode
  className?: string
} & MotionProps): ReactNode {
  const prefersReducedMotion = useReducedMotion()

  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
      variants={prefersReducedMotion ? reducedMotionVariants : variants}
      transition={
        prefersReducedMotion
          ? { duration: 0.01 }
          : (transition ?? { duration: 0.7, ease: softEase })
      }
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  )
}
