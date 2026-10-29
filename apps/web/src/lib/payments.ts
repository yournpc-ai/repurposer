import { apiFetch } from "@/lib/api"

export interface CreditPackage {
  key: string
  credits: number
  amount_minor: number
  currency: string
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

export async function fetchCreditPackages(): Promise<CreditPackage[]> {
  const res = await apiFetch("/api/v1/payments/packages")
  if (!res.ok) return []
  return ((await res.json()) as { items: CreditPackage[] }).items
}

export async function createCheckoutSession(
  packageKey: string,
): Promise<{ order_id: string; checkout_url: string } | null> {
  const res = await apiFetch("/api/v1/payments/checkout-sessions", {
    method: "POST",
    body: { package_key: packageKey },
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
