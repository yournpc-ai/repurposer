import { describe, expect, it } from "vitest"

import {
  filterSkillOptions,
  skillTriggerQuery,
  skillOptionForReference,
  type SkillOption,
} from "./skills"

describe("skill slash trigger", () => {
  it.each([
    ["/", ""],
    ["/launch", "launch"],
    ["Use /launch", "launch"],
    ["Use /marker-2", "marker-2"],
    ["First line\n/分镜", "分镜"],
  ])("reads the cursor-scoped command in %s", (text, query) => {
    expect(skillTriggerQuery(text)).toBe(query)
  })

  it.each([
    "https://example.com/skill",
    "https://example.com",
    "src/components/SkillPicker",
    "/usr/local/bin",
    "path /usr/local",
    "name/skill",
    "/launch film",
  ])("does not trigger for ordinary text or paths: %s", (text) => {
    expect(skillTriggerQuery(text)).toBeNull()
  })
})

describe("skill option filtering", () => {
  const options: SkillOption[] = [
    {
      reference: { kind: "builtin", skill_id: "launch-film", version: "1" },
      skill_id: "launch-film",
      name: "Launch film",
      description: "A website introduction",
      capabilities: ["storyboard"],
    },
    {
      reference: { kind: "external", skill_version_id: "version-1" },
      skill_id: "shotcraft",
      name: "Marker title",
      description: "Draw attention",
      capabilities: ["underline"],
    },
  ]

  it("matches DTO display names and declared metadata", () => {
    expect(filterSkillOptions(options, "website")).toEqual([options[0]])
    expect(filterSkillOptions(options, "underline")).toEqual([options[1]])
    expect(filterSkillOptions(options, "")).toEqual(options)
  })
})

describe("history Skill reference replay", () => {
  it("matches exact versions and keeps an honest fallback after disappearance", () => {
    const old = optionsForReplay("version-old", 1)
    const current = optionsForReplay("version-current", 2)
    expect(skillOptionForReference(old.reference, [current])).toEqual(old)
    const missing = skillOptionForReference(old.reference, [])
    expect(missing.reference).toEqual(old.reference)
    expect(missing.capabilities).toEqual([])
  })
})

function optionsForReplay(versionId: string, version: number): SkillOption {
  return {
    reference: { kind: "external", skill_version_id: versionId },
    skill_id: "shotcraft",
    name: "Shotcraft",
    description: "",
    capabilities: [],
    version_number: version,
  }
}
