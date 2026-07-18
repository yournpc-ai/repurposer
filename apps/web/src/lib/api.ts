/** Thin API client with bearer token from the auth flow. */

import { toast } from "sonner"

import { clearAuth, getToken } from "@/lib/auth"
import i18n from "@/lib/i18n"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

/** Dispatched on window when any API call answers 401, so the AuthProvider
 * can clear state and open the login dialog instead of leaving raw errors. */
export const UNAUTHORIZED_EVENT = "repurposer:unauthorized"

/** Per-call toast control:
 * - omitted: errors toast the server's real `detail` via sonner, success is silent
 * - `false`: fully silent — the caller handles all feedback itself
 * - `string`: show this success message on 2xx (errors still auto-toast)
 * - `{ success, error }`: custom messages; `error` overrides the server detail
 */
export type ApiToastOption = false | string | { success?: string; error?: string }

function buildUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`
  return `${API_URL}${normalized}`
}

type ApiFetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown
  toast?: ApiToastOption
}

export async function apiFetch(
  path: string,
  options: ApiFetchOptions = {}
): Promise<Response> {
  const { toast: toastOption, ...init } = options
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`)
  }

  let body: BodyInit | undefined
  if (init.body instanceof FormData) {
    body = init.body
  } else if (init.body !== undefined) {
    body = JSON.stringify(init.body)
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json")
    }
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path), { ...init, headers, body })
  } catch (e) {
    // Network-level failure (server unreachable, CORS, DNS): there is no
    // response to parse, so toast here before rethrowing for the caller's
    // control flow.
    if (toastOption !== false && typeof window !== "undefined") {
      toast.error(i18n.t("common.networkError"))
    }
    throw e
  }
  if (response.status === 401 && typeof window !== "undefined") {
    clearAuth()
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  }

  if (toastOption !== false && typeof window !== "undefined") {
    if (response.ok) {
      const successMessage =
        typeof toastOption === "string" ? toastOption : toastOption?.success
      if (successMessage) toast.success(successMessage)
    } else if (response.status !== 401) {
      const customError =
        typeof toastOption === "object" ? toastOption.error : undefined
      if (customError) {
        toast.error(customError)
      } else {
        const errorBody = await response.clone().json().catch(() => null)
        toast.error(errorDetail(errorBody, i18n.t("common.requestFailed")))
      }
    }
  }
  return response
}

export async function apiGet(path: string, options: ApiFetchOptions = {}) {
  return apiFetch(path, { method: "GET", ...options })
}

export async function apiPost(
  path: string,
  body?: unknown,
  options: ApiFetchOptions = {}
) {
  return apiFetch(path, {
    method: "POST",
    body,
    ...options,
  })
}

export async function apiPut(
  path: string,
  body?: unknown,
  options: ApiFetchOptions = {}
) {
  return apiFetch(path, {
    method: "PUT",
    body,
    ...options,
  })
}

export async function apiDelete(path: string, options: ApiFetchOptions = {}) {
  return apiFetch(path, { method: "DELETE", ...options })
}

/** Extract a human-readable message from a FastAPI error body.
 *
 * `detail` is a string for HTTPException, but an array of
 * `{loc, msg, type}` objects for 422 validation errors — rendering the raw
 * value would show "[object Object]".
 */
export function errorDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === "string" && detail) return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d as { msg?: string } | null)?.msg)
      .filter((m): m is string => !!m)
    if (msgs.length > 0) return msgs.join("; ")
  }
  return fallback
}

/** Prefix a storage-relative URL (e.g. `/api/v1/outputs/...`) with the API origin.
 *
 * Leaves absolute URLs and empty values untouched.
 */
export function toAbsoluteUrl(
  url: string | null | undefined
): string | null | undefined {
  if (!url) return url
  if (url.startsWith("http://") || url.startsWith("https://")) return url
  return `${API_URL}${url.startsWith("/") ? url : `/${url}`}`
}

/** Download a URL as a file via fetch → blob → object URL.
 *
 * Works cross-origin (object-storage public URLs): unlike `<a download>` on a
 * remote URL — which browsers ignore — a blob object URL is same-origin, so
 * the filename is honored. API-relative URLs carry the bearer token via
 * apiFetch; absolute URLs go through plain fetch (no auth header leaked to
 * the storage host).
 */
export async function downloadFile(
  url: string | null | undefined,
  filename: string
): Promise<void> {
  const absolute = toAbsoluteUrl(url)
  if (!absolute) return
  const resp = absolute.startsWith(API_URL)
    ? await apiFetch(absolute.slice(API_URL.length))
    : await fetch(absolute)
  if (!resp.ok) throw new Error(`Download failed: ${resp.status}`)
  const blob = await resp.blob()
  const objectUrl = URL.createObjectURL(blob)
  try {
    const a = document.createElement("a")
    a.href = objectUrl
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    // Delay revocation so the browser has started consuming the blob.
    setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000)
  }
}

