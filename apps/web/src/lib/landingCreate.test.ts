import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { consumeLandingCreate, stageLandingCreate } from "./landingCreate"

const values = new Map<string, string>()
const sessionStorage = {
  getItem: (key: string) => values.get(key) ?? null,
  setItem: (key: string, value: string) => void values.set(key, value),
  removeItem: (key: string) => void values.delete(key),
}

describe("landing create handoff", () => {
  beforeEach(() => {
    values.clear()
    vi.stubGlobal("window", { sessionStorage })
  })

  afterEach(() => vi.unstubAllGlobals())

  it("preserves the exact Skill and prompt once", () => {
    const handoff = {
      skill: {
        kind: "builtin",
        skill_id: "knowledge-explainer",
        version: "1.0.0",
      },
      promptKey: "landing.gallery.items.knowledge-explainer.prompt",
    } as const

    stageLandingCreate(handoff)
    expect(consumeLandingCreate()).toEqual(handoff)
    expect(consumeLandingCreate()).toBeNull()
  })

  it("rejects a handoff that is not a landing Skill prefill", () => {
    values.set(
      "repurposer:landing-create",
      JSON.stringify({
        skill: { kind: "external", skill_version_id: "external-version" },
        promptKey: "recipes.shelf.demos.text-short-genesis.prompt",
      }),
    )
    expect(consumeLandingCreate()).toBeNull()
  })
})
