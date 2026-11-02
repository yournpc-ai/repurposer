"use client"

import { useTranslation } from "react-i18next"

import type { SkillOption } from "@/lib/skills"
import { cn } from "@/lib/utils"

/** Shared by the React history chip and MentionEditor's DOM-owned inline chip. */
export const SKILL_CHIP_CLASS_NAME =
  "mx-0.5 inline-flex max-w-full items-center gap-1 rounded-md bg-success-subtle px-1.5 py-0.5 text-success"

export function skillChipLabel(option: SkillOption, externalLabel: string): string {
  const name = option.name || externalLabel
  const version = option.version_number != null ? ` v${option.version_number}` : ""
  return `/${name}${version}`
}

/** The visible inline Skill binding. Green `/name` distinguishes it from
 * neutral @mentions; both are deleted with ordinary text-editing gestures. */
export function SkillChip({
  option,
  className,
}: {
  option: SkillOption
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <span className={cn(SKILL_CHIP_CLASS_NAME, "text-xs", className)}>
      <span className="max-w-56 truncate">
        {skillChipLabel(option, t("skills.external"))}
      </span>
    </span>
  )
}
