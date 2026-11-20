import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { apiFetch } from "@/lib/api"
import type { ChatMention } from "@/lib/mentions"
import { BUILTIN_SKILL_VERSIONS, fetchChatSkills, skillOptionForReference, type SkillOption } from "@/lib/skills"
import { consumeLandingCreate } from "@/lib/landingCreate"

import { HomeComposer } from "@/components/home/HomeComposer"
import type { PersonaPickerEntry } from "@/components/composer/PersonaPanel"
import type { MentionEditorHandle } from "@/components/mentions/MentionEditor"

type Persona = PersonaPickerEntry

export const Route = createFileRoute("/_app/home")({
  component: Home,
})

function Home() {
  const { t } = useTranslation()
  const [personas, setPersonas] = useState<Persona[]>([])
  // The draft (prompt + mentions) is the editor's reported mirror — the DOM
  // owns the text; Home keeps it as the send payload and acts on the editor
  // through `editorRef`.
  const [prompt, setPrompt] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const [skillOptions, setSkillOptions] = useState<SkillOption[]>([])
  const [selectedSkill, setSelectedSkill] = useState<SkillOption | null>(null)
  const editorRef = useRef<MentionEditorHandle>(null)
  useEffect(() => {
    Promise.all([
      apiFetch("/api/v1/personas").then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetchChatSkills().catch(() => ({ items: [] })),
    ]).then(([personaRows, skills]) => {
      setPersonas((personaRows as Persona[]) || [])
      setSkillOptions(skills.items)
    })
  }, [])

  const lastPrefillRef = useRef<string | null>(null)
  const handlePrefill = useCallback(
    (prefillKey: string, skill: SkillOption, { replaceDraft = false } = {}) => {
      const placeholder = t("recipes.shelf.urlPlaceholder")
      const text = t(prefillKey, { placeholder })
      const draft = prompt.trim()
      const replaceable =
        replaceDraft ||
        (mentions.length === 0 && (draft === "" || draft === lastPrefillRef.current))
      if (replaceable) {
        editorRef.current?.clear({ preserveSkill: true })
        editorRef.current?.insertText(text)
      } else {
        editorRef.current?.insertText(`\n\n${text}`)
      }
      lastPrefillRef.current = text.trim()
      setSelectedSkill(skill)
      editorRef.current?.selectText(placeholder)
      editorRef.current?.focus()
    },
    [t, prompt, mentions],
  )

  // A landing product card survives the login detour and resolves against the
  // live catalog here. Consumption is one-shot; it never sends the draft.
  useEffect(() => {
    if (skillOptions.length === 0) return
    const handoff = consumeLandingCreate()
    if (!handoff) return
    handlePrefill(
      handoff.promptKey,
      skillOptionForReference(handoff.skill, skillOptions),
    )
  }, [handlePrefill, skillOptions])

  return (
    <section className="ui-as-start">
      <h1 className="ui-as-start__title">{t("home.heroQuestion")}</h1>
      <div className="ui-as-start__composer">
        <HomeComposer personas={personas} prompt={prompt} mentions={mentions}
          onPromptChange={setPrompt} onMentionsChange={setMentions}
          selectedSkill={selectedSkill} onSkillChange={setSelectedSkill} editorRef={editorRef} />
      </div>
      <div className="mt-5 flex flex-wrap justify-center gap-2" data-tour="home-recipes">
        {examples.map(({ skillId, label, demo }) => (
          <button key={demo} type="button" className="rounded-full border px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
            onClick={() => handlePrefill(`recipes.shelf.demos.${demo}.prompt`,
              skillOptionForReference({ kind: "builtin", skill_id: skillId, version: BUILTIN_SKILL_VERSIONS[skillId] }, skillOptions),
              { replaceDraft: true })}>
            {t(`recipes.shelf.subs.${label}`)}
          </button>
        ))}
      </div>
    </section>
  )
}

const examples = [
  { skillId: "promo-video", label: "website-product", demo: "product-promo-oxvalue-product-evidence" },
  { skillId: "text-animation", label: "opinion-text", demo: "text-short-clear-rhythm" },
  { skillId: "knowledge-explainer", label: "concept-explainer", demo: "knowledge-explainer-clear-expression" },
] as const
