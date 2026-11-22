import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { ChatMention } from "@/lib/mentions"
import { fetchChatSkills, skillOptionForReference, type SkillOption } from "@/lib/skills"
import { consumeLandingCreate } from "@/lib/landingCreate"

import { Button } from "@/components/ui/button-clean"
import { HomeComposer } from "@/components/home/HomeComposer"
import type { MentionEditorHandle } from "@/components/mentions/MentionEditor"


export const Route = createFileRoute("/_app/home")({
  component: Home,
})

function Home() {
  const { t } = useTranslation()
  // The draft (prompt + mentions) is the editor's reported mirror — the DOM
  // owns the text; Home keeps it as the send payload and acts on the editor
  // through `editorRef`.
  const [prompt, setPrompt] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const [skillOptions, setSkillOptions] = useState<SkillOption[]>([])
  const [selectedSkill, setSelectedSkill] = useState<SkillOption | null>(null)
  const editorRef = useRef<MentionEditorHandle>(null)
  useEffect(() => {
    fetchChatSkills().then(({ items }) => setSkillOptions(items)).catch(() => {})
  }, [])

  const lastPrefillRef = useRef<string | null>(null)
  const handlePrefill = useCallback(
    (prefillKey: string, skill: SkillOption | null, { replaceDraft = false } = {}) => {
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
      handoff.skill ? skillOptionForReference(handoff.skill, skillOptions) : null,
    )
  }, [handlePrefill, skillOptions])

  return (
    <section className="ui-as-start">
      <h1 className="ui-as-start__title">{t("home.heroQuestion")}</h1>
      <div className="ui-as-start__composer">
        <HomeComposer prompt={prompt} mentions={mentions}
          onPromptChange={setPrompt} onMentionsChange={setMentions}
          selectedSkill={selectedSkill} onSkillChange={setSelectedSkill} editorRef={editorRef} />
      </div>
      <div className="mt-5 flex flex-wrap justify-center gap-2" data-tour="home-recipes">
        {examples.map((example) => (
          <Button key={example} variant="secondary"
            onClick={() => handlePrefill(`home.examples.${example}.prompt`, selectedSkill)}>
            {t(`home.examples.${example}.label`)}
          </Button>
        ))}
      </div>
    </section>
  )
}

const examples = ["overlay", "framing", "trim"] as const
