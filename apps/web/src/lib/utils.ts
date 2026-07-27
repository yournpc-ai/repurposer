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

/** Format an ISO timestamp as a localized relative time ("3 days ago" /
 * "3 天前") via Intl.RelativeTimeFormat — follows the active i18n locale,
 * no extra copy to maintain. Returns "" for unparseable input. */
export function formatRelativeTime(iso: string, locale: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ""
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" })
  const minutes = Math.round((Date.now() - then) / 60000)
  if (minutes < 1) return rtf.format(0, "minute")
  if (minutes < 60) return rtf.format(-minutes, "minute")
  const hours = Math.round(minutes / 60)
  if (hours < 24) return rtf.format(-hours, "hour")
  const days = Math.round(hours / 24)
  if (days < 30) return rtf.format(-days, "day")
  const months = Math.round(days / 30)
  if (months < 12) return rtf.format(-months, "month")
  return rtf.format(-Math.round(months / 12), "year")
}
