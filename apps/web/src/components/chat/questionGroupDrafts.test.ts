// @vitest-environment jsdom
import { beforeEach, expect, it } from "vitest"
import { loadQuestionGroupDrafts, saveQuestionGroupDrafts } from "./questionGroupDrafts"

beforeEach(() => window.sessionStorage.clear())

it("restores question.id + group_digest drafts after a refresh", () => {
  const key = "question-1:digest-1"
  saveQuestionGroupDrafts("project-1", {
    [key]: [
      { slot: "purpose", kind: "option", option_id: "website" },
      { slot: "target_seconds", kind: "freeform", text: "60" },
    ],
  })
  expect(loadQuestionGroupDrafts("project-1")).toEqual({
    [key]: [
      { slot: "purpose", kind: "option", option_id: "website" },
      { slot: "target_seconds", kind: "freeform", text: "60" },
    ],
  })
  expect(loadQuestionGroupDrafts("project-2")).toEqual({})
  saveQuestionGroupDrafts("project-1", {})
  expect(loadQuestionGroupDrafts("project-1")).toEqual({})
})
