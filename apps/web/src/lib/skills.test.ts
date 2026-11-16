import { describe, expect, it } from "vitest"

import {
  filterSkillOptions,
  localBuiltinSkillOptions,
  skillDisplayName,
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

  it("searches localized task names and keeps exact no-network references", () => {
    const builtins = localBuiltinSkillOptions()
    expect(builtins.map((option) => option.reference)).toEqual([
      { kind: "builtin", skill_id: "launch-film", version: "1.4.0" },
      { kind: "builtin", skill_id: "talking-head-video", version: "1.0.0" },
      { kind: "builtin", skill_id: "text-animation", version: "1.0.0" },
      { kind: "builtin", skill_id: "knowledge-explainer", version: "1.0.0" },
    ])
    const names: Record<string, string> = {
      "skills.builtin.launch-film.name": "网站发布视频",
      "skills.builtin.promo-video.name": "产品推广视频制作",
      "skills.builtin.talking-head-video.name": "口播动效视频制作",
      "skills.builtin.text-animation.name": "文字动画视频制作",
      "skills.builtin.knowledge-explainer.name": "知识讲解视频制作",
      "skills.builtin.text-animation.shortName": "文字动画",
    }
    const t = (key: string) => names[key] ?? key
    expect(skillDisplayName(builtins[2], t)).toBe("文字动画视频制作")
    expect(skillDisplayName(builtins[2], t, "short")).toBe("文字动画")
    expect(filterSkillOptions(builtins, "文字动画", (option) => skillDisplayName(option, t)))
      .toEqual([builtins[2]])
    expect(filterSkillOptions(builtins, "口播", (option) => skillDisplayName(option, t)))
      .toEqual([builtins[1]])
  })
})

describe("history Skill reference replay", () => {
  it("matches exact versions and keeps an honest fallback after disappearance", () => {
    const old = optionsForReplay("version-old", 1)
    const current = optionsForReplay("version-current", 2)
    expect(skillOptionForReference(old.reference, [old, current])).toEqual(old)
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
