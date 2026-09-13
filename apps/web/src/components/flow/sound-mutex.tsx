"use client"

/** 全局声音指针 (2026-09-13 用户拍板): one project canvas has ONE sound
 * source at a time — unmuting any video/audio mutes every other (ambient
 * muted playback keeps running; this is a MUTE mutex, never a pause one).
 * The provider mounts at the ResultsCanvas root so cards + the media
 * lightbox share one holder; surfaces without a provider (the recipe
 * manual's ThumbCard) fall back to per-card local state, behavior
 * unchanged. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

interface SoundMutex {
  /** The id currently holding the sound pointer (null = everyone muted). */
  holder: string | null
  claim: (id: string) => void
  /** No-op unless the caller IS the holder (stale releases never steal). */
  release: (id: string) => void
}

const SoundMutexContext = createContext<SoundMutex | null>(null)

export function SoundMutexProvider({ children }: { children: ReactNode }) {
  const [holder, setHolder] = useState<string | null>(null)
  const claim = useCallback((id: string) => setHolder(id), [])
  const release = useCallback(
    (id: string) => setHolder((h) => (h === id ? null : h)),
    [],
  )
  const value = useMemo(() => ({ holder, claim, release }), [holder, claim, release])
  return <SoundMutexContext.Provider value={value}>{children}</SoundMutexContext.Provider>
}

/** A media card's mute state under the mutex: `muted` derives from the
 * holder (default muted — nobody holds), `toggle` claims or yields.
 * Unmounting the holder releases the pointer. */
export function useSoundMutex(id: string): { muted: boolean; toggle: () => void } {
  const ctx = useContext(SoundMutexContext)
  const [localMuted, setLocalMuted] = useState(true)
  const holding = ctx?.holder === id
  useEffect(() => {
    if (!holding || !ctx) return
    return () => ctx.release(id)
  }, [ctx, holding, id])
  if (!ctx) {
    return { muted: localMuted, toggle: () => setLocalMuted((v) => !v) }
  }
  return {
    muted: !holding,
    toggle: () => (holding ? ctx.release(id) : ctx.claim(id)),
  }
}

/** Hold the pointer for as long as `active` (the lightbox plays with sound
 * for as long as it's open; closing yields — the canvas stays all-muted). */
export function useSoundMutexHold(active: boolean, id: string): void {
  const ctx = useContext(SoundMutexContext)
  useEffect(() => {
    if (!ctx || !active) return
    ctx.claim(id)
    return () => ctx.release(id)
  }, [ctx, active, id])
}
