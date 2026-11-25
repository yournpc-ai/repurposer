"use client"

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react"

export interface StudioHeaderSlot {
  left?: ReactNode
  actions?: ReactNode
}

interface StudioHeaderStore {
  getSnapshot: () => StudioHeaderSlot
  setSlot: (slot: StudioHeaderSlot) => void
  clearSlot: () => void
  subscribe: (listener: () => void) => () => void
}

const EMPTY_SLOT: StudioHeaderSlot = {}

function createStudioHeaderStore(): StudioHeaderStore {
  let current: StudioHeaderSlot = EMPTY_SLOT
  const listeners = new Set<() => void>()
  const emit = () => {
    for (const listener of listeners) listener()
  }
  return {
    getSnapshot: () => current,
    setSlot: (next: StudioHeaderSlot) => {
      current = next
      emit()
    },
    clearSlot: () => {
      if (current === EMPTY_SLOT) return
      current = EMPTY_SLOT
      emit()
    },
    subscribe: (listener: () => void) => {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
  }
}

const StudioHeaderContext = createContext<StudioHeaderStore | null>(null)

export function StudioHeaderProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<StudioHeaderStore | null>(null)
  if (!storeRef.current) {
    storeRef.current = createStudioHeaderStore()
  }
  return (
    <StudioHeaderContext.Provider value={storeRef.current}>
      {children}
    </StudioHeaderContext.Provider>
  )
}

const noopSubscribe = () => () => {}
const emptySnapshot = () => EMPTY_SLOT

export function useStudioHeaderSlot(): StudioHeaderSlot {
  const store = useContext(StudioHeaderContext)
  return useSyncExternalStore(
    store ? store.subscribe : noopSubscribe,
    store ? store.getSnapshot : emptySnapshot,
    emptySnapshot,
  )
}

/** Inject route-specific left breadcrumb/title and right action buttons into the
 * single 48px StudioHeader bar. Automatically clears on unmount without
 * re-rendering sibling routes. */
export function useStudioHeader(slot: StudioHeaderSlot | null) {
  const store = useContext(StudioHeaderContext)
  const left = slot?.left
  const actions = slot?.actions
  const hasSlot = slot !== null

  useEffect(() => {
    if (!store) return
    if (!hasSlot) {
      store.clearSlot()
      return
    }
    store.setSlot({ left, actions })
  }, [store, hasSlot, left, actions])

  useEffect(() => {
    if (!store) return
    return () => {
      store.clearSlot()
    }
  }, [store])
}
