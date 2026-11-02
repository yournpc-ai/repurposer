import { describe, expect, it } from "vitest"

import {
  deliveryOutputReveal,
  presentationAckReady,
  revealOpen,
  shouldAcknowledgePresentation,
  shouldAnimateEntrance,
} from "./reveal"
import type { VideoStoryboardBlock } from "./types"

describe("revealOpen", () => {
  it("requires both domain readiness and the actual preceding display boundary", () => {
    expect(revealOpen({ ready: false, priorDrained: false })).toBe(false)
    expect(revealOpen({ ready: true, priorDrained: false })).toBe(false)
    expect(revealOpen({ ready: false, priorDrained: true })).toBe(false)
    expect(revealOpen({ ready: true, priorDrained: true })).toBe(true)
  })
})

describe("delivery-local Output reveal", () => {
  it("uses only the delivery's actual display facts", () => {
    expect(deliveryOutputReveal({})).toEqual({ priorDrained: false, history: false })
    expect(deliveryOutputReveal({ clientVisibleAtMs: 100 })).toEqual({
      priorDrained: true,
      history: false,
    })
    expect(deliveryOutputReveal({ proseDrainedAtMs: 120 })).toEqual({
      priorDrained: true,
      history: false,
    })
  })

  it("hydrated delivery history opens statically without an entrance replay", () => {
    expect(deliveryOutputReveal({ hydrated: true })).toEqual({
      priorDrained: true,
      history: true,
    })
    expect(shouldAnimateEntrance(true)).toBe(false)
  })
})

describe("history entrance hydration", () => {
  it("live first entrance keeps its animation decision", () => {
    expect(shouldAnimateEntrance()).toBe(true)
    expect(shouldAnimateEntrance(false)).toBe(true)
  })

  it("hydrated history never replays entrance, independent of readiness", () => {
    expect(shouldAnimateEntrance(true)).toBe(false)
    expect(revealOpen({ ready: true, priorDrained: true })).toBe(true)
  })
})

describe("storyboard presentation ACK recovery", () => {
  const block: VideoStoryboardBlock = {
    kind: "video_storyboard",
    presented_message_id: "plan-1",
    composition_id: "composition-1",
    composition_version_id: "version-1",
    version: 1,
    content_digest: "digest-1",
  }
  const recovery = {
    authorized_revision_message_id: "revision-1",
    presented_message_id: "plan-1",
    composition_version_id: "version-1",
    content_digest: "digest-1",
    presentation_complete: false,
  }

  it("a live first presentation still requires DTO, prose drain and playable previews", () => {
    const allowed = shouldAcknowledgePresentation({
      history: false,
      pendingPlanMessageId: null,
      recovery: null,
      messageId: "local-preview",
      block,
    })
    expect(allowed).toBe(true)
    expect(presentationAckReady({
      allowed,
      dtoReady: true,
      prosePresented: false,
      previewsReady: true,
    })).toBe(false)
    expect(presentationAckReady({
      allowed,
      dtoReady: true,
      prosePresented: true,
      previewsReady: false,
    })).toBe(false)
    expect(presentationAckReady({
      allowed,
      dtoReady: true,
      prosePresented: true,
      previewsReady: true,
    })).toBe(true)
  })

  it("ordinary static history never ACKs even when every display gate is ready", () => {
    const allowed = shouldAcknowledgePresentation({
      history: true,
      pendingPlanMessageId: null,
      recovery: null,
      messageId: "old-message-echo",
      block,
    })
    expect(allowed).toBe(false)
    expect(presentationAckReady({
      allowed,
      dtoReady: true,
      prosePresented: true,
      previewsReady: true,
    })).toBe(false)
  })

  it("the exact pending authorized receipt is the only historical recovery path", () => {
    expect(shouldAcknowledgePresentation({
      history: true,
      pendingPlanMessageId: "plan-1",
      recovery,
      messageId: "plan-1-echo",
      block,
    })).toBe(true)
  })

  it("answered, rejected or non-pending plans cannot inherit recovery", () => {
    for (const pendingPlanMessageId of [null, "another-plan"]) {
      expect(shouldAcknowledgePresentation({
        history: true,
        pendingPlanMessageId,
        recovery,
        messageId: "plan-1-echo",
        block,
      })).toBe(false)
    }
  })

  it("a completion receipt on either source suppresses another ACK", () => {
    expect(shouldAcknowledgePresentation({
      history: true,
      pendingPlanMessageId: "plan-1",
      recovery: { ...recovery, presentation_complete: true },
      messageId: "plan-1-echo",
      block,
    })).toBe(false)
    expect(shouldAcknowledgePresentation({
      history: false,
      pendingPlanMessageId: null,
      recovery: null,
      messageId: "local-preview",
      block: { ...block, presentation_complete: true },
    })).toBe(false)
  })

  it("message, version or digest drift cannot inherit authorization", () => {
    const mismatches = [
      { recovery: { ...recovery, presented_message_id: "other-message" }, block },
      { recovery: { ...recovery, authorized_revision_message_id: null }, block },
      { recovery, block: { ...block, presented_message_id: "other-message" } },
      { recovery: { ...recovery, composition_version_id: "version-2" }, block },
      { recovery: { ...recovery, content_digest: "digest-2" }, block },
      { recovery: { ...recovery, content_digest: null }, block },
      { recovery, block: { ...block, content_digest: undefined } },
    ]
    for (const mismatch of mismatches) {
      expect(shouldAcknowledgePresentation({
        history: true,
        pendingPlanMessageId: "plan-1",
        messageId: "plan-1-echo",
        ...mismatch,
      })).toBe(false)
    }
  })
})
