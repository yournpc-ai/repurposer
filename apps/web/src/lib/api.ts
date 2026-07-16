/** Thin API client with bearer token from the auth flow. */

import { getToken } from "@/lib/auth"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

function buildUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`
  return `${API_URL}${normalized}`
}

type ApiFetchOptions = Omit<RequestInit, "body"> & { body?: unknown }

export async function apiFetch(
  path: string,
  options: ApiFetchOptions = {}
): Promise<Response> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`)
  }

  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    body = JSON.stringify(options.body)
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json")
    }
  }

  return fetch(buildUrl(path), { ...options, headers, body })
}

export async function apiGet(path: string, options: RequestInit = {}) {
  return apiFetch(path, { method: "GET", ...options })
}

export async function apiPost(
  path: string,
  body?: unknown,
  options: RequestInit = {}
) {
  return apiFetch(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
    ...options,
  })
}

export async function apiPut(
  path: string,
  body?: unknown,
  options: RequestInit = {}
) {
  return apiFetch(path, {
    method: "PUT",
    body: body ? JSON.stringify(body) : undefined,
    ...options,
  })
}

export async function apiDelete(path: string, options: RequestInit = {}) {
  return apiFetch(path, { method: "DELETE", ...options })
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

