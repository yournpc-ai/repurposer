import { createFileRoute, useLocation } from "@tanstack/react-router"
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
  const location = useLocation()
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
      const replaceable = brief || (mentions.length === 0 && (draft === "" || draft === lastPrefillRef.current))
      if (replaceable) editor.clear({ preserveSkill: true })
      const insertion = replaceable ? text : `\n\n${text}`
      if (brief) {
        lastPrefillRef.current = editor.insertBrief(text).trim()
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

  // Prefill prompt, mention, or saved skill when arriving from /presets or /assets.
  const navState = location.state as
    | {
        prefillPrompt?: string
        prefillMention?: ChatMention
        prefillSkillVersionId?: string
      }
    | undefined
  const presetPrefill = navState?.prefillPrompt
  const mentionPrefill = navState?.prefillMention
  const skillVersionPrefill = navState?.prefillSkillVersionId
  const consumedPresetRef = useRef<string | null>(null)
  useEffect(() => {
    if (!presetPrefill || consumedPresetRef.current === presetPrefill) return
    const editor = editorRef.current
    if (!editor) return
    consumedPresetRef.current = presetPrefill
    editor.clear({ preserveSkill: true })
    editor.insertText(presetPrefill + " ")
    editor.focus()
  }, [presetPrefill])

  const consumedMentionRef = useRef<string | null>(null)
  useEffect(() => {
    if (!mentionPrefill) return
    const key = `${mentionPrefill.type}:${mentionPrefill.id}`
    if (consumedMentionRef.current === key) return
    const editor = editorRef.current
    if (!editor) return
    consumedMentionRef.current = key
    editor.clear({ preserveSkill: true })
    editor.insertMention(mentionPrefill)
    editor.insertText(" ")
    editor.focus()
  }, [mentionPrefill])

  const consumedSkillRef = useRef<string | null>(null)
  useEffect(() => {
    if (!skillVersionPrefill || skillOptions.length === 0) return
    if (consumedSkillRef.current === skillVersionPrefill) return
    const match = skillOptions.find(
      (option) =>
        option.reference.kind === "external" &&
        option.reference.skill_version_id === skillVersionPrefill,
    )
    if (!match) return
    consumedSkillRef.current = skillVersionPrefill
    setSelectedSkill(match)
    editorRef.current?.focus()
  }, [skillVersionPrefill, skillOptions])

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
