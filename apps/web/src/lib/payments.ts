import { apiFetch } from "@/lib/api"
import type { CreditTopupRequest } from "@/lib/credits"

export interface CreditPackage {
  key: string
  credits: number
  amount_minor: number
  currency: string
}

export interface CustomTopupPolicy {
  currency: string
  min_amount_minor: number
  max_amount_minor: number
  credits_per_major: number
}

export interface CreditPackageCatalog {
  items: CreditPackage[]
  custom: CustomTopupPolicy
}

export interface PaymentOrder {
  id: string
  package_key: string
  status: "pending" | "paid" | "expired" | "failed" | string
  credits: number
  amount_minor: number
  currency: string
  paid_at: string | null
  credited_at: string | null
  created_at: string
}

export async function fetchCreditPackages(): Promise<CreditPackageCatalog> {
  const res = await apiFetch("/api/v1/payments/packages", { toast: false })
  if (!res.ok) throw new Error("credit_packages_unavailable")
  return (await res.json()) as CreditPackageCatalog
}

export interface CheckoutRequest {
  amountMinor: number
  returnPath?: string
}

export async function createCheckoutSession(
  request: CheckoutRequest,
): Promise<{ order_id: string; checkout_url: string } | null> {
  const body: { amount_minor: number; return_path?: string } = {
    amount_minor: request.amountMinor,
  }
  if (request.returnPath) {
    body.return_path = request.returnPath
  }
  const res = await apiFetch("/api/v1/payments/checkout-sessions", {
    method: "POST",
    body,
  })
  if (!res.ok) return null
  return (await res.json()) as { order_id: string; checkout_url: string }
}

/** Polling stays silent: a transient read failure keeps the last honest state. */
export async function fetchPaymentOrder(orderId: string): Promise<PaymentOrder | null> {
  const res = await apiFetch(`/api/v1/payments/orders/${orderId}`, { toast: false })
  if (!res.ok) return null
  return (await res.json()) as PaymentOrder
}

export function formatMoney(amountMinor: number, currency: string, lang: string): string {
  return new Intl.NumberFormat(lang, {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(amountMinor / 100)
}

export function formatCurrencySymbol(currency: string, lang: string): string {
  return (
    new Intl.NumberFormat(lang, {
      style: "currency",
      currency: currency.toUpperCase(),
    })
      .formatToParts(0)
      .find((part) => part.type === "currency")?.value ?? currency.toUpperCase()
  )
}

export function formatAmountInput(amountMinor: number): string {
  return (amountMinor / 100).toFixed(2)
}

/** Parse decimal major units without routing a float through a money order. */
export function parseAmountMinor(value: string): number | null {
  const normalized = value.trim().replace(",", ".")
  if (!/^\d+(?:\.\d{0,2})?$/.test(normalized)) return null
  const [whole, fraction = ""] = normalized.split(".")
  const amountMinor =
    Number(whole) * 100 + Number((fraction + "00").slice(0, 2))
  return Number.isSafeInteger(amountMinor) ? amountMinor : null
}

/** Build a clean in-app return path preserving current route & query (e.g. ?c=convId),
 * stripping any stale checkout query parameters. */
export function buildCheckoutReturnPath(
  pathname: string,
  search: string,
  surface: "inline" | "settings",
): string {
  const params = new URLSearchParams(search)
  params.delete("checkout")
  params.delete("order_id")
  params.delete("checkout_surface")
  if (surface === "settings") {
    params.set("checkout_surface", "settings")
  }
  const cleanPath = pathname.startsWith("/") ? pathname : "/home"
  const qs = params.toString()
  return qs ? `${cleanPath}?${qs}` : cleanPath
}

/** Pick the initial selection for the top-up dialog: defaults to the first preset,
 * or covers a spend-point shortfall with the smallest sufficient preset (or custom amount). */
export function pickInitialTopup(
  catalog: CreditPackageCatalog,
  shortfall: CreditTopupRequest | null,
): { selectedKey: string | null; amountInput: string } {
  const defaultPkg = catalog.items[0] ?? null
  const fallback = {
    selectedKey: defaultPkg?.key ?? null,
    amountInput: defaultPkg ? formatAmountInput(defaultPkg.amount_minor) : "",
  }
  if (!shortfall) return fallback
  const deficit = Math.max(0, shortfall.required - shortfall.balance)
  if (deficit <= 0) return fallback

  const coveringPreset = [...catalog.items]
    .sort((a, b) => a.credits - b.credits)
    .find((pkg) => pkg.credits >= deficit)
  if (coveringPreset) {
    return {
      selectedKey: coveringPreset.key,
      amountInput: formatAmountInput(coveringPreset.amount_minor),
    }
  }

  const { custom } = catalog
  if (!custom || custom.credits_per_major <= 0) return fallback
  const neededMinor = Math.ceil((deficit * 100) / custom.credits_per_major)
  const clamped = Math.min(
    custom.max_amount_minor,
    Math.max(custom.min_amount_minor, neededMinor),
  )
  return {
    selectedKey: null,
    amountInput: formatAmountInput(clamped),
  }
}
