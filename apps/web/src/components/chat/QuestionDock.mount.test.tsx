// @vitest-environment jsdom
import { useState } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { QuestionDock } from "./QuestionDock"
import { dockWorthyQuestion } from "./ChatDock"
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
  options: [{ id: optionId, label: `Choose ${optionId}` }],
  required: true,
  allow_freeform: true,
}))

function Harness({ onSubmit }: { onSubmit: (answers: BriefAnswerItem[]) => void }) {
  const [answers, setAnswers] = useState<BriefAnswerItem[]>([])
  return (
    <QuestionDock
      kind="question"
      plain
      question="Production setup"
      options={[]}
      items={items}
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
  expect(selected.className).toContain("bg-primary/10")
  expect(selected.className).toContain("text-primary")
  expect(selected.className).toContain("border-primary/25")
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
