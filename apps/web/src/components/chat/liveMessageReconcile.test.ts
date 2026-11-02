import { describe, expect, it } from "vitest"

import type { OverlayMessage } from "./timeline/types"
import {
  buildRecoveredActivityRow,
  buildRecoveredProseMessage,
  insertRecoveredMessage,
  isCurrentRunAttemptDelivery,
  isFreshPolledRow,
  isTurnOwner,
  observedMessageSeq,
  prependMissingHistory,
  reconcilePersistedFailure,
  releaseTurnOwner,
  runReviewerLanded,
  shouldAdmitPolledTrigger,
  stampServerMessageId,
} from "./liveMessageReconcile"

function message(
  id: string,
  seq?: number,
  overrides: Partial<OverlayMessage> = {},
): OverlayMessage {
  return {
    id,
    role: "assistant",
    content: id,
    ...(seq == null ? {} : { seq }),
    ...overrides,
  }
}

describe("run review poll admission", () => {
  it("does not revive an activity from before the observed tail", () => {
    expect(isFreshPolledRow(6, 14)).toBe(false)
    expect(isFreshPolledRow(6, null)).toBe(false)
    expect(isFreshPolledRow(null, 14)).toBe(false)
  })

  it("admits a newly landed activity on the next poll", () => {
    expect(isFreshPolledRow(15, 14)).toBe(true)
  })

  it("keeps the observation watermark ahead of rendered rows", () => {
    expect(observedMessageSeq(20, [message("old", 4), message("new", 14)])).toBe(20)
    expect(observedMessageSeq(null, [message("old", 4), message("local")])).toBe(4)
  })

  it("scopes run review speech to its own run without backfilling generic watches", () => {
    expect(
      shouldAdmitPolledTrigger({ fresh: false, reviewRunId: null, rowRunId: "run-1" }),
    ).toBe(false)
    expect(
      shouldAdmitPolledTrigger({ fresh: false, reviewRunId: "run-1", rowRunId: "run-1" }),
    ).toBe(true)
    expect(
      shouldAdmitPolledTrigger({ fresh: true, reviewRunId: "run-1", rowRunId: "run-2" }),
    ).toBe(false)
  })
})

describe("same-run recovery delivery identity", () => {
  const failed = message("failed-delivery", 10, {
    runId: "run-1",
    runDelivery: true,
    runDeliveryRef: "run-1",
    suggestions: [],
  })
  const retry = message("retry-delivery", 20, {
    runId: "run-1",
    runDelivery: true,
    runDeliveryRef: "run-1:upload-retry-1",
    suggestions: [],
  })

  it("the first failure does not seal retry_upload's new attempt", () => {
    expect(runReviewerLanded([failed], "run-1", 0)).toBe(true)
    expect(runReviewerLanded([failed], "run-1", 1)).toBe(false)
    expect(isCurrentRunAttemptDelivery(failed, "run-1", 1)).toBe(false)
    expect(runReviewerLanded([failed, retry], "run-1", 1)).toBe(true)
  })

  it("a live row waits for its real drain while hydrated QA is already settled", () => {
    const live = { ...retry, suggestions: undefined }
    expect(runReviewerLanded([live], "run-1", 1)).toBe(false)
    expect(runReviewerLanded([{ ...live, hydrated: true }], "run-1", 1)).toBe(true)
    expect(runReviewerLanded([{ ...live, runId: "run-2", hydrated: true }], "run-1", 1)).toBe(false)
  })
})

describe("polled activity identity", () => {
  const beat = {
    activity_id: "activity-1",
    kind: "read" as const,
    status: "completed" as const,
    key: "chat.activity.readDone",
  }

  it("ordinary recovered activity keeps turn identity and registers its host", () => {
    const recovered = buildRecoveredActivityRow({
      id: "row-1",
      seq: 15,
      createdAt: "2026-10-30T00:00:00Z",
      turnId: "turn-1",
      beat,
      material: false,
    })
    expect(recovered.registerHost).toBe(true)
    expect(recovered.message).toMatchObject({
      id: "row-1",
      turnId: "turn-1",
      independentKind: undefined,
      activity: { ...beat, at: "2026-10-30T00:00:00Z" },
    })
  })

  it("material recovery stays independent and never registers as a turn work host", () => {
    const recovered = buildRecoveredActivityRow({
      id: "material-1",
      turnId: "turn-1",
      beat,
      material: true,
    })
    expect(recovered.registerHost).toBe(false)
    expect(recovered.message.turnId).toBe("turn-1")
    expect(recovered.message.independentKind).toBe("material")
  })

  it("legacy recovered rows keep an explicit identity-unknown fallback", () => {
    const recovered = buildRecoveredActivityRow({
      id: "legacy-1",
      turnId: null,
      beat,
      material: false,
    })
    expect(recovered.message.turnId).toBeUndefined()
  })
})

describe("stream ownership across Stop and a successor turn", () => {
  it("lets only the current owner adopt and clear the turn", () => {
    const stopped = { localId: "stopped", serverId: null }
    const successor = { localId: "successor", serverId: null }
    const current = successor
    expect(isTurnOwner(current, stopped)).toBe(false)
    expect(isTurnOwner(current, successor)).toBe(true)
    expect(releaseTurnOwner(current, stopped)).toBe(successor)
    expect(releaseTurnOwner(current, successor)).toBeNull()
  })
})

describe("persisted early failure", () => {
  it("reconciles the exact optimistic user row without changing its id", () => {
    const other = message("other", 10)
    const result = reconcilePersistedFailure(
      [other, message("rollback-1", undefined, { role: "user", turnId: "rollback-1" })],
      "rollback-1",
      "server-turn-1",
    )
    expect(result[0]).toBe(other)
    expect(result[1]).toMatchObject({
      id: "rollback-1",
      role: "user",
      turnId: "server-turn-1",
    })
  })

  it("does not infer a user row from its position", () => {
    const previous = [message("user-1", undefined, { role: "user" })]
    const result = reconcilePersistedFailure(previous, "missing", "server-turn-1")
    expect(result[0]).toBe(previous[0])
    expect(result[0].turnId).toBeUndefined()
  })
})

describe("recovered prose placement", () => {
  it("keeps persisted storyboard references on the typewriter-born recovery row", () => {
    const blocks = [{
      kind: "video_storyboard" as const,
      composition_id: "composition-1",
      composition_version_id: "version-1",
      version: 1,
    }]
    const row = buildRecoveredProseMessage({
      id: "recovered-1",
      seq: 15,
      createdAt: "2026-10-30T00:00:00Z",
      turnId: "turn-1",
      blocks,
      runDelivery: false,
    })
    expect(row).toMatchObject({
      id: "recovered-1",
      content: "",
      streaming: true,
      turnId: "turn-1",
      blocks,
    })
  })

  it("keeps the recovered delivery's own Output refs", () => {
    const row = buildRecoveredProseMessage({
      id: "delivery-b",
      runId: "run-1",
      runDelivery: true,
      outputRefs: ["output-b"],
    })
    expect(row).toMatchObject({
      id: "delivery-b",
      runId: "run-1",
      runDelivery: true,
      outputRefs: ["output-b"],
    })
  })

  it("places a scoped late delivery before an already visible later server row", () => {
    const result = insertRecoveredMessage(
      [message("start", 14), message("later", 16)],
      message("trigger", 12),
      { fresh: false },
    )
    expect(result.map((row) => row.id)).toEqual(["trigger", "start", "later"])
  })

  it("places a backfill before the optimistic suffix, not after the user's newer row", () => {
    const result = insertRecoveredMessage(
      [message("start", 10), message("local-user", undefined, { role: "user" })],
      message("trigger", 12),
      { fresh: false },
    )
    expect(result.map((row) => row.id)).toEqual(["start", "trigger", "local-user"])
  })

  it("keeps a fresh delivery at the live edge while preserving typewriter state", () => {
    const local = message("local-user", undefined, { role: "user" })
    const result = insertRecoveredMessage(
      [message("start", 14), local],
      message("delivery", 15, { streaming: true }),
      { fresh: true },
    )
    expect(result.map((row) => row.id)).toEqual(["start", "local-user", "delivery"])
    expect(result[1]).toBe(local)
    expect(result[2].streaming).toBe(true)
  })

  it("uses seq rather than arrival order when a newer row won the race", () => {
    const result = insertRecoveredMessage(
      [message("start", 14), message("next", 16)],
      message("delivery", 15),
      { fresh: true },
    )
    expect(result.map((row) => row.id)).toEqual(["start", "delivery", "next"])
  })

  it("deduplicates a row already recovered by another channel", () => {
    const previous = [message("delivery", 15, { streaming: true })]
    expect(
      insertRecoveredMessage(previous, message("delivery", 15), { fresh: true }),
    ).toBe(previous)
  })
})

describe("run terminal recovery journey", () => {
  it("ignores an old material row while landing the new delivery after the visible start", () => {
    const previous = [message("start", 14)]
    const oldActivity = message("old-web-page", 6, {
      content: "",
      activity: { activity_id: "read-6", kind: "read", status: "completed", key: "done" },
    })
    const afterOldActivity = isFreshPolledRow(oldActivity.seq, 14)
      ? insertRecoveredMessage(previous, oldActivity, { fresh: false })
      : previous
    expect(afterOldActivity).toBe(previous)
    const result = insertRecoveredMessage(
      afterOldActivity,
      message("delivery", 15, { streaming: true }),
      { fresh: isFreshPolledRow(15, 14) },
    )
    expect(result.map((row) => row.id)).toEqual(["start", "delivery"])
  })
})

describe("mount history replay", () => {
  it("prepends only archive ids absent from the live array", () => {
    const live = message("live", 2, { streaming: true })
    const result = prependMissingHistory(
      [live],
      [message("archive", 1), message("live", 2)],
    )
    expect(result.map((row) => row.id)).toEqual(["archive", "live"])
    expect(result[1]).toBe(live)
  })

  it("slow history plus a normal send keeps one user and one assistant with stable keys", () => {
    const user = message("local-user", undefined, {
      role: "user",
      content: "same request",
      serverMessageId: "server-user",
      serverIdAliases: ["server-user"],
    })
    const assistant = message("local-assistant", undefined, {
      content: "same answer",
      birthKey: "stream-birth",
      streaming: true,
      serverMessageId: "server-final",
      serverIdAliases: ["server-partial", "server-final"],
    })
    const result = prependMissingHistory(
      [user, assistant],
      [
        message("older", 1),
        message("server-user", 2, { role: "user", content: "same request" }),
        message("server-final", 3, { content: "same answer" }),
        message("server-partial", 3, { content: "same answer" }),
      ],
    )
    expect(result.map((row) => row.id)).toEqual(["older", "local-user", "local-assistant"])
    expect(result[1]).toBe(user)
    expect(result[2]).toBe(assistant)
    expect(result[2].birthKey ?? result[2].id).toBe("stream-birth")
    expect(result[2].streaming).toBe(true)
  })

  it("never dedupes identical prose with different real identities", () => {
    const local = message("local", undefined, { content: "identical" })
    const result = prependMissingHistory([local], [message("server", 1, { content: "identical" })])
    expect(result.map((row) => row.id)).toEqual(["server", "local"])
  })

  it("dedupes an echo alias without swallowing its QA archive", () => {
    const echo = message("local-echo", undefined, {
      serverMessageId: "question-1",
      serverIdAliases: ["question-1"],
    })
    const qa = message("question-1", 2, {
      content: "",
      qa: { question: "Q", answer: "A", muted: false },
    })
    const result = prependMissingHistory([echo], [message("question-1-echo", 1), qa])
    expect(result.map((row) => row.id)).toEqual(["question-1", "local-echo"])
  })

  it("a late final alias removes both partial and final archive twins in place", () => {
    const local = message("local-assistant", undefined, {
      birthKey: "stream-birth",
      streaming: true,
      serverMessageId: "server-partial",
      serverIdAliases: ["server-partial"],
    })
    const result = stampServerMessageId(
      [message("server-partial", 2), message("server-final", 3), local],
      "local-assistant",
      "server-final",
    )
    expect(result.map((row) => row.id)).toEqual(["local-assistant"])
    expect(result[0]).toMatchObject({
      id: "local-assistant",
      birthKey: "stream-birth",
      streaming: true,
      serverMessageId: "server-final",
      serverIdAliases: ["server-partial", "server-final"],
    })
  })
})
