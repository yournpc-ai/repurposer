import { describe, expect, it } from "vitest"

import en from "./locales/en"
import zh from "./locales/zh"

type LeafMap = Record<string, string>

function flattenLeaves(obj: unknown, prefix = "", out: LeafMap = {}): LeafMap {
  if (typeof obj === "string") {
    out[prefix] = obj
    return out
  }
  if (Array.isArray(obj)) {
    obj.forEach((item, index) => {
      flattenLeaves(item, `${prefix}[${index}]`, out)
    })
    return out
  }
  if (obj && typeof obj === "object") {
    for (const [key, value] of Object.entries(obj)) {
      const next = prefix ? `${prefix}.${key}` : key
      flattenLeaves(value, next, out)
    }
  }
  return out
}

function placeholdersOf(text: string): string[] {
  const matches = [...text.matchAll(/\{\{\s*([\w.]+)\s*\}\}/g)].map((m) => m[1])
  return [...new Set(matches)].sort()
}

describe("i18n EN <-> ZH dictionary parity", () => {
  const enLeaves = flattenLeaves(en)
  const zhLeaves = flattenLeaves(zh)

  it("has identical leaf key sets between en.ts and zh.ts", () => {
    const enKeys = Object.keys(enLeaves).sort()
    const zhKeys = Object.keys(zhLeaves).sort()
    const missingInZh = enKeys.filter((k) => !(k in zhLeaves))
    const extraInZh = zhKeys.filter((k) => !(k in enLeaves))
    expect(missingInZh, "Keys present in en.ts but missing in zh.ts").toEqual([])
    expect(extraInZh, "Keys present in zh.ts but missing in en.ts").toEqual([])
    expect(enKeys.length).toBeGreaterThan(500)
  })

  it("preserves identical {{placeholder}} interpolation variables on every key", () => {
    const mismatches: Array<{ key: string; en: string[]; zh: string[] }> = []
    for (const key of Object.keys(enLeaves)) {
      const enVars = placeholdersOf(enLeaves[key] ?? "")
      const zhVars = placeholdersOf(zhLeaves[key] ?? "")
      if (JSON.stringify(enVars) !== JSON.stringify(zhVars)) {
        mismatches.push({ key, en: enVars, zh: zhVars })
      }
    }
    expect(mismatches).toEqual([])
  })

  it("contains no unexpected empty translation strings in either locale", () => {
    const allowedEmpty = new Set(["landing.heroTitle2"])
    const emptyEn = Object.entries(enLeaves)
      .filter(([k, v]) => !allowedEmpty.has(k) && v.trim().length === 0)
      .map(([k]) => k)
    const emptyZh = Object.entries(zhLeaves)
      .filter(([k, v]) => !allowedEmpty.has(k) && v.trim().length === 0)
      .map(([k]) => k)
    expect(emptyEn).toEqual([])
    expect(emptyZh).toEqual([])
  })
})
