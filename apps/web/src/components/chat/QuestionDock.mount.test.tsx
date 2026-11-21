// @vitest-environment jsdom
import { useState } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { QuestionDock } from "./QuestionDock"
import { dockWorthyQuestion } from "./AgentThread"
import type { BriefAnswerItem, BriefQuestionItem, QuestionMessage } from "./timeline/types"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

afterEach(cleanup)

const values = [
  ["purpose", "website"],
  ["target_seconds", "60"],
  ["narrative_mode", "mission_tech"],
  ["narration_language", "en"],
  ["subtitle_languages", "en"],
  ["aspect", "16:9"],
] as const

const items: BriefQuestionItem[] = values.map(([slot, optionId], index) => ({
  slot,
  question: `Question ${index}`,
  options: [{ id: optionId, label: `Choose ${optionId}`, value: optionId }],
  required: true,
  allow_freeform: true,
}))

function Harness({ onSubmit, fields = items }: { onSubmit: (answers: BriefAnswerItem[]) => void; fields?: BriefQuestionItem[] }) {
  const [answers, setAnswers] = useState<BriefAnswerItem[]>([])
  return (
    <QuestionDock
      kind="question"
      plain
      question="Production setup"
      options={[]}
      items={fields}
      groupDigest="digest-1"
      groupAnswers={answers}
      onGroupAnswersChange={setAnswers}
      onGroupSubmit={onSubmit}
      onAnswer={vi.fn()}
      answering={false}
    />
  )
}

it("pages one question at a time and submits all answers once", () => {
  const onSubmit = vi.fn()
  render(<Harness onSubmit={onSubmit} />)

  expect(screen.getByText("Question 0")).toBeTruthy()
  expect(screen.queryByText("Question 1")).toBeNull()
  fireEvent.click(screen.getByText("Choose website"))

  expect(screen.getByText("Question 1")).toBeTruthy()
  expect(screen.queryByText("Question 0")).toBeNull()
  expect(screen.queryByText("Question 2")).toBeNull()
  fireEvent.click(screen.getByText("Choose 60"))

  fireEvent.click(screen.getByText("Choose mission_tech"))
  fireEvent.click(screen.getByText("Choose en"))
  fireEvent.click(screen.getByText("Choose en"))
  fireEvent.click(screen.getByText("Choose 16:9"))
  expect(onSubmit).not.toHaveBeenCalled()

  fireEvent.click(screen.getByText("questionDock.previous"))
  const selected = screen.getByRole("button", { name: /Choose en/ })
  expect(selected.getAttribute("aria-pressed")).toBe("true")
  const card = selected.closest(".ui-crdc")
  expect(card).not.toBeNull()
  expect(card?.hasAttribute("data-selected")).toBe(true)
  expect(card?.parentElement?.querySelectorAll(".ui-crdc[data-selected]")).toHaveLength(1)
  expect(selected.querySelector("svg")).not.toBeNull()
  fireEvent.click(screen.getByText("questionDock.next"))
  fireEvent.click(screen.getByText("questionDock.submit"))

  expect(onSubmit).toHaveBeenCalledTimes(1)
  const answers = onSubmit.mock.calls[0][0]
  expect(answers).toHaveLength(6)
  expect(answers).toEqual(expect.arrayContaining([
    { slot: "purpose", kind: "option", option_id: "website" },
    { slot: "target_seconds", kind: "option", option_id: "60" },
    { slot: "aspect", kind: "option", option_id: "16:9" },
  ]))
})

it("keeps the legacy single-question form", () => {
  const onAnswer = vi.fn()
  render(
    <QuestionDock
      kind="question"
      question="One question"
      options={[{ id: "1", label: "One" }]}
      onAnswer={onAnswer}
      answering={false}
    />,
  )
  fireEvent.click(screen.getByText("One"))
  expect(onAnswer).toHaveBeenCalledWith("1")
})


it("revives a grouped pending question instead of filtering it as plain text", () => {
  const pending = {
    id: "group-pending",
    content: "",
    answer: null,
    workflow_run_id: null,
    question: { kind: "question", options: [], items },
  } as QuestionMessage
  expect(dockWorthyQuestion(pending)).toBe(pending)
})

it("keeps legacy option docking and rejects options-empty plain text", () => {
  const legacy = {
    id: "legacy-pending",
    content: "",
    answer: null,
    workflow_run_id: null,
    question: { kind: "question", options: [{ id: "1", label: "One" }] },
  } as QuestionMessage
  const plainText = {
    id: "plain-text",
    content: "",
    answer: null,
    workflow_run_id: null,
    question: { kind: "question", options: [], items: [] },
  } as QuestionMessage
  expect(dockWorthyQuestion(legacy)).toBe(legacy)
  expect(dockWorthyQuestion(plainText)).toBeNull()
})


it("submits just the five questions, including a custom answer on the last page", () => {
  const fields = [
    { slot: "production_direction", title: "用途和表达方向", label: "面向创作者的产品演示" },
    { slot: "target_seconds", title: "希望多长？", label: "15 秒" },
    { slot: "narration_language", title: "旁白语言", label: "英文旁白" },
    { slot: "subtitle_languages", title: "字幕语言", label: "简体中文" },
    { slot: "aspect", title: "画面比例", label: "16:9 横版" },
  ].map(({ slot, title, label }) => ({
    slot, question: title,
    options: slot === "subtitle_languages"
      ? [{ id: "1", label, value: ["zh-CN"] }, { id: "2", label: "英文", value: ["en-US"] }]
      : [{ id: "1", label, value: label }],
  }))
  const onSubmit = vi.fn()
  render(<Harness fields={fields} onSubmit={onSubmit} />)

  fireEvent.change(screen.getByRole("textbox", { name: "用途和表达方向" }), {
    target: { value: "官网首屏，用案例说明证据如何追溯" },
  })
  fireEvent.click(screen.getByText("questionDock.next"))
  fireEvent.click(screen.getByText("15 秒"))
  fireEvent.click(screen.getByText("英文旁白"))
  expect(screen.getByRole("button", { name: /简体中文/ })).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: /英文/ }))
  expect(screen.getAllByRole("textbox")).toHaveLength(1)
  fireEvent.change(screen.getByRole("textbox", { name: "画面比例" }), { target: { value: "9:16" } })
  expect(onSubmit).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText("questionDock.submit"))

  expect(onSubmit).toHaveBeenCalledTimes(1)
  expect(onSubmit).toHaveBeenCalledWith([
    { slot: "production_direction", kind: "freeform", text: "官网首屏，用案例说明证据如何追溯" },
    { slot: "target_seconds", kind: "option", option_id: "1" },
    { slot: "narration_language", kind: "option", option_id: "1" },
    { slot: "subtitle_languages", kind: "option", option_id: "2" },
    { slot: "aspect", kind: "freeform", text: "9:16" },
  ])
})
