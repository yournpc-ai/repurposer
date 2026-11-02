import { apiFetch } from "@/lib/api"

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
}

export async function createCheckoutSession(
  request: CheckoutRequest,
): Promise<{ order_id: string; checkout_url: string } | null> {
  const res = await apiFetch("/api/v1/payments/checkout-sessions", {
    method: "POST",
    body: { amount_minor: request.amountMinor },
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
