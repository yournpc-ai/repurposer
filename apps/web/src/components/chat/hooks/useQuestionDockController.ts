/** QuestionDock state & sessionStorage draft controller extracted from AgentThread. */
import { useCallback, useEffect, useRef, useState } from "react"

import {
  loadQuestionGroupDrafts,
  saveQuestionGroupDrafts,
} from "../questionGroupDrafts"
import type { BriefAnswerItem, QuestionMessage } from "../timeline/types"

export function useQuestionDockController(projectId: string) {
  const [pendingQuestion, setPendingQuestion] = useState<QuestionMessage | null>(null)
  const [questionGroupDrafts, setQuestionGroupDrafts] = useState<
    Record<string, BriefAnswerItem[]>
  >({})
  const hydrationRef = useRef({ projectId: "", skipSave: true })

  const groupDraftKey = useCallback(
    (question: QuestionMessage) =>
      `${question.id}:${question.question?.group_digest ?? ""}`,
    [],
  )

  const groupDraftAnswers = useCallback(
    (question: QuestionMessage) =>
      (questionGroupDrafts[groupDraftKey(question)] ?? []).filter((answer) =>
        question.question?.items?.some((item) => item.slot === answer.slot),
      ),
    [groupDraftKey, questionGroupDrafts],
  )

  const setGroupDraftAnswers = useCallback(
    (question: QuestionMessage, answers: BriefAnswerItem[]) => {
      const key = groupDraftKey(question)
      setQuestionGroupDrafts((previous) => ({ ...previous, [key]: answers }))
    },
    [groupDraftKey],
  )

  const clearGroupDraftByDigest = useCallback((groupDigest: string | null | undefined) => {
    if (!groupDigest) return
    setQuestionGroupDrafts((previous) =>
      Object.fromEntries(
        Object.entries(previous).filter(([key]) => !key.endsWith(`:${groupDigest}`)),
      ),
    )
  }, [])

  useEffect(() => {
    hydrationRef.current = { projectId, skipSave: true }
    setQuestionGroupDrafts(loadQuestionGroupDrafts(projectId))
  }, [projectId])

  useEffect(() => {
    const hydration = hydrationRef.current
    if (hydration.projectId !== projectId) return
    if (hydration.skipSave) {
      hydration.skipSave = false
      return
    }
    saveQuestionGroupDrafts(projectId, questionGroupDrafts)
  }, [projectId, questionGroupDrafts])

  useEffect(() => {
    const digest = pendingQuestion?.question?.group_digest
    if (!pendingQuestion || !digest || !pendingQuestion.question?.items?.length) return
    const targetKey = groupDraftKey(pendingQuestion)
    setQuestionGroupDrafts((previous) => {
      if (previous[targetKey]) return previous
      const sourceKey = Object.keys(previous).find(
        (key) => key.endsWith(`:${digest}`) && key !== targetKey,
      )
      if (!sourceKey) return previous
      const next = { ...previous, [targetKey]: previous[sourceKey] }
      delete next[sourceKey]
      return next
    })
  }, [groupDraftKey, pendingQuestion?.id, pendingQuestion?.question?.group_digest])

  return {
    pendingQuestion,
    setPendingQuestion,
    groupDraftKey,
    groupDraftAnswers,
    setGroupDraftAnswers,
    clearGroupDraftByDigest,
  }
}
