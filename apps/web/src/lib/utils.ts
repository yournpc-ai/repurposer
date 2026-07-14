import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format seconds as MM:SS. */
export function formatDuration(
  seconds: number | null | undefined,
  fallback = "--:--"
): string {
  if (seconds == null || seconds <= 0 || !Number.isFinite(seconds)) {
    return fallback
  }
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, "0")}`
}
