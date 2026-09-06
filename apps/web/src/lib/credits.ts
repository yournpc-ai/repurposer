/** The credits surface's shared wire types (ADR-055, docs/BILLING.md). */

/** The structured 422 payload of a USER-level shortfall (API.md §4,
 * BILLING §7): `{detail: {code, balance, required}}`. Strictly two
 * vocabularies with the provider's 402 — "the AI service is out of quota"
 * lives in its own server-side dictionary and never shares this shape. */
export interface CreditsInsufficientDetail {
  code: "credits.insufficient"
  balance: number
  required: number
}

/** Narrow a parsed error `detail` (a 422 response body, or a
 * StreamTurnError's raw detail) to the structured shortfall — null for
 * anything else (plain-string details, validation arrays, other codes). */
export function asCreditsInsufficient(
  detail: unknown,
): CreditsInsufficientDetail | null {
  if (
    detail !== null &&
    typeof detail === "object" &&
    (detail as { code?: unknown }).code === "credits.insufficient" &&
    typeof (detail as { balance?: unknown }).balance === "number" &&
    typeof (detail as { required?: unknown }).required === "number"
  ) {
    return detail as CreditsInsufficientDetail
  }
  return null
}
