/** Thin API client with a default bearer token for the no-login MVP.
 *
 * The backend resolves the bearer token to the seeded default user. When real
 * authentication is added, this module is the only place that needs to swap
 * "default" for an actual JWT from a login flow.
 */

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
const DEFAULT_TOKEN = "default"

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
  if (!headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${DEFAULT_TOKEN}`)
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
