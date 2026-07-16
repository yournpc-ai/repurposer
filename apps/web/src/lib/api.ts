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

