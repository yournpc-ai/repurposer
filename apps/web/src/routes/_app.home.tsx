import { createFileRoute } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import type { ChatMention } from "@/lib/mentions"
import { fetchChatSkills, skillOptionForReference, type SkillOption } from "@/lib/skills"
import { consumeLandingCreate } from "@/lib/landingCreate"

import { DemoGallery } from "@/components/home/DemoGallery"
import { HomeComposer } from "@/components/home/HomeComposer"
import type { MentionEditorHandle } from "@/components/mentions/MentionEditor"

export const Route = createFileRoute("/_app/home")({
  component: Home,
})

function Home() {
  const { t } = useTranslation()
  const scrollRef = useRef<HTMLDivElement>(null)
  // The draft (prompt + mentions) is the editor's reported mirror — the DOM
  // owns the text; Home keeps it as the send payload and acts on the editor
  // through `editorRef`.
  const [prompt, setPrompt] = useState("")
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const [skillOptions, setSkillOptions] = useState<SkillOption[]>([])
  const [selectedSkill, setSelectedSkill] = useState<SkillOption | null>(null)
  const editorRef = useRef<MentionEditorHandle>(null)
  useEffect(() => {
    fetchChatSkills()
      .then(({ items }) => setSkillOptions(items))
      .catch(() => {})
  }, [])

  const lastPrefillRef = useRef<string | null>(null)
  const handlePrefill = useCallback(
    (prefillKey: string, skill: SkillOption | null, brief = false) => {
      const editor = editorRef.current
      if (!editor) return
      const text = t(prefillKey)
      const draft = prompt.trim()
      const replaceable = mentions.length === 0 && (draft === "" || draft === lastPrefillRef.current)
      if (replaceable) editor.clear({ preserveSkill: true })
      const insertion = replaceable ? text : `\n\n${text}`
      if (brief) {
        const result = editor.insertBrief(insertion)
        lastPrefillRef.current = replaceable ? result.trim() : null
      } else {
        editor.insertText(insertion)
        lastPrefillRef.current = replaceable ? text.trim() : null
        editor.focus()
      }
      setSelectedSkill(skill)
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
    <div ref={scrollRef} className="h-full overflow-y-auto">
      <section className="ui-as-start">
        <h1 className="ui-as-start__title">{t("home.heroQuestion")}</h1>
        <div className="ui-as-start__composer">
          <HomeComposer
            prompt={prompt}
            mentions={mentions}
            onPromptChange={setPrompt}
            onMentionsChange={setMentions}
            selectedSkill={selectedSkill}
            onSkillChange={setSelectedSkill}
            editorRef={editorRef}
          />
        </div>
      </section>
      <DemoGallery
        scrollRef={scrollRef}
        onPrefill={(key, reference) => {
          handlePrefill(key, reference ? skillOptionForReference(reference, skillOptions) : null, true)
          scrollRef.current?.scrollTo({ top: 0, behavior: "instant" })
        }}
      />
    </div>
  )
}
