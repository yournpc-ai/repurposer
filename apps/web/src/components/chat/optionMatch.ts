/** Deterministic option mapping — the client mirror of the server's
 * `_match_option` (`apps/api/app/chat/service.py`), kept field-aligned hit
 * for hit: a typed letter (positional), a 1-based number, a verbatim
 * label, or the raw option id maps to that option; anything else is
 * deliberately NOT a match (semantic mapping belongs to the judged
 * settlement, zero heuristics here).
 *
 * The dock's pencil row runs this BEFORE posting: a number/letter/label
 * hit settles as the OPTION (kind="option" — the same settlement the chat
 * input's autoResume always produced), everything else rides the freeform
 * answer. Positional matching (never the raw id) is what keeps slug ids
 * like "tech_innovation" answerable by "a" / "1". */
export function matchOptionByText<T extends { id: string; label: string }>(
  text: string,
  options: readonly T[],
): T | null {
  // Same strip set as the server's rstrip — trailing sentence punctuation
  // never defeats a hit ("2." picks option 2).
  const normalized = text
    .trim()
    .toLowerCase()
    .replace(/[.。,，、!！?？:：)）\]]+$/, "")
  if (!normalized) return null
  for (let index = 0; index < options.length; index++) {
    const option = options[index]
    if (normalized === option.id.trim().toLowerCase()) return option
    if (normalized === String.fromCharCode("a".charCodeAt(0) + index)) return option
    if (normalized === String(index + 1)) return option
    if (normalized === option.label.trim().toLowerCase()) return option
  }
  return null
}
