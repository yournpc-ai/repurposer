/** Checkpoint segmentation machine (ADR-085/ADR-104 一键一段 + ADR-108
 * 出生钉位/数组位置律) — the ONE segment machine both turn paths ride
 * (sendChat and the answer stream's settleAnswerTurn): a turn can open with
 * expectation prose and checkpoint mid-turn (a pick resuming into a design
 * beat), and without this machine the pre-read speech and the final reply
 * merge into ONE bubble born before the read's activity rows — the live
 * order then contradicts the persisted order.
 *
 * The law:
 * - 归属在输入事件边界钉死 (P1): every pushed chunk carries its owning row
 *   id from the moment it arrives — the release queue and the typewriter's
 *   buffer stay character-aligned (FIFO in, FIFO out), so the typewriter's
 *   DISPLAY progress never decides which segment a fragment belongs to.
 *   A delta always belongs to the main segment; checkpoint text always
 *   belongs to its own segment; interleaved activity rows and late deltas
 *   can never be swallowed by a settle.
 * - 出生钉位: a speech row's array position is pinned at its first WIRE
 *   fact (delta receipt / checkpoint frame / envelope push), never at the
 *   typewriter's first released fragment — a throttled (hidden-tab) timer
 *   must never let a synchronously-appended activity row claim the
 *   position first.
 * - Path A (the iteration-0 seat): prose that already streamed into the
 *   main bubble settles IN PLACE — the row rekeys to `${baseId}#cpN`
 *   SYNCHRONOUSLY at the checkpoint frame's arrival (its position and
 *   birthKey never move), its still-queued chars are re-attributed to the
 *   checkpoint id, and the frame's authoritative text is written when
 *   those chars finish typing. The main-bubble identity resets to a fresh
 *   segment at the same instant, so the read's activity rows sit BETWEEN
 *   the two speeches by array position.
 * - Path B (checkpoint-only segment): the row pins at the frame's arrival
 *   and the text paces in through the SAME typewriter (never a blob).
 * - The settled main bubble's facts (`previewText` / `streamedAny`) track
 *   ONLY the trailing segment's RELEASED text (typed, not received — the
 *   envelope's suffix pacing must never skip text the user has not seen);
 *   checkpoint text never joins the suffix-pacing reference.
 * - Segment final writes (settle / streaming=false) ride zero-length
 *   markers IN the release queue — they fire exactly when the segment's
 *   own chars finish, never gated on later segments' text, and never left
 *   pending past a flush (abort leaves no late mutation).
 */

import type { OverlayMessage } from "@/components/chat/historyReplay"
import { createTypewriter } from "@/lib/typewriter"

export interface SpeechSegmentsDeps {
  /** The main bubble's id for this turn (streamId / previewId). */
  baseId: string
  /** setMessages-shaped row writer. */
  apply: (fn: (prev: OverlayMessage[]) => OverlayMessage[]) => void
  setProseActive: (active: boolean) => void
  /** First NON-WHITESPACE character actually released into a row. This is a
   * display-lifecycle signal, not a receipt signal: delta arrival, empty
   * deltas, keepalives and buffered-but-unseen text never fire it. The chat
   * work segment seals here; character ownership remains pinned at push. */
  onVisible?: (rowId: string, atMs: number) => void
  /** Test seam: the real seat is createTypewriter; a synchronous fake
   * keeps the suite timer-free. */
  typewriterFactory?: typeof createTypewriter
}

export interface SpeechSegments {
  onDelta: (delta: string) => void
  onCheckpoint: (text: string, at?: string) => void
  /** Envelope-time pacing channel (the zero-delta / unseen-tail law): a
   * push rides the SAME typewriter into the main segment, pinning its row
   * at push time. */
  push: (text: string) => void
  /** The envelope's one await: every buffered char released (segment
   * final writes included — they fire as the buffer empties). */
  drain: () => Promise<void>
  /** Release everything and stop the clock (the failure/abort path). */
  flush: () => void
  /** The settled main bubble's typed prefix (the suffix-pacing reference). */
  readonly previewText: string
  /** Whether the settled main bubble carries streamed prose (echoCarried). */
  readonly streamedAny: boolean
}

/** A turn's rollback drops the preview AND its checkpoint segments. */
export function isSpeechSegmentRow(id: string, baseId: string): boolean {
  return id === baseId || id.startsWith(`${baseId}#cp`)
}

/** One queued release: `remaining` chars of the typewriter's buffer belong
 * to `rowId`; `onDone` fires when the entry is fully released (a
 * zero-length entry is a pure marker — it fires the moment every earlier
 * entry has been released). */
interface ReleaseEntry {
  rowId: string
  remaining: number
  onDone?: () => void
}

export function createSpeechSegments(deps: SpeechSegmentsDeps): SpeechSegments {
  const { baseId, apply, setProseActive } = deps
  let receivedAny = false
  let streamedAny = false
  let previewText = ""
  let checkpointCount = 0
  // Character-aligned with the typewriter's buffer: pushes append to both,
  // releases consume both — the invariant sum(remaining) === buffer length
  // holds at every event boundary.
  const releaseQueue: ReleaseEntry[] = []
  const visibleRows = new Set<string>()

  const markVisible = (rowId: string, text: string) => {
    if (!text.trim() || visibleRows.has(rowId)) return
    visibleRows.add(rowId)
    deps.onVisible?.(rowId, Date.now())
  }

  const ensureSpeechRow = (id: string, at?: string) => {
    apply((prev) =>
      prev.some((m) => m.id === id)
        ? prev
        : [
            ...prev,
            {
              id,
              // The render-key law (OverlayMessage): unique per BIRTH — the
              // Path-A rekey spreads it, so the promoted row never remounts.
              birthKey: crypto.randomUUID(),
              role: "assistant" as const,
              content: "",
              streaming: true,
              at: at ?? new Date().toISOString(),
            },
          ],
    )
  }

  const appendToRow = (id: string, text: string) => {
    apply((prev) =>
      prev.some((m) => m.id === id)
        ? prev.map((m) => (m.id === id ? { ...m, content: m.content + text } : m))
        : [
            // Defensive-only (every producer pins its row at the input
            // boundary first) — a release never reorders a birth.
            ...prev,
            {
              id,
              birthKey: crypto.randomUUID(),
              role: "assistant" as const,
              content: text,
              streaming: true,
              at: new Date().toISOString(),
            },
          ],
    )
  }

  /** Fire leading markers whose predecessors have all been released. Safe
   * at any time: a head marker means no earlier chars are still buffered. */
  const nudgeMarkers = () => {
    while (releaseQueue.length > 0 && releaseQueue[0].remaining === 0) {
      releaseQueue.shift()?.onDone?.()
    }
  }

  /** The typewriter's append seat: route every released fragment by the
   * queue (ownership was pinned at push time). Fragments may straddle
   * segment boundaries — split them char-exact. */
  const routeRelease = (fragment: string) => {
    let rest = fragment
    while (rest) {
      const head = releaseQueue[0]
      if (!head) {
        // Unreachable by the alignment invariant; fail open onto the main
        // segment rather than dropping speech.
        markVisible(baseId, rest)
        appendToRow(baseId, rest)
        previewText += rest
        streamedAny = true
        break
      }
      const take = Math.min(head.remaining, rest.length)
      const piece = rest.slice(0, take)
      rest = rest.slice(take)
      head.remaining -= take
      if (head.rowId === baseId) {
        // previewText / streamedAny are the SETTLED main bubble's TYPED
        // facts — checkpoint segments never flip them (echoCarried stays
        // truthful; the suffix pacer never skips unseen text).
        streamedAny = true
        previewText += piece
      }
      markVisible(head.rowId, piece)
      appendToRow(head.rowId, piece)
      if (head.remaining === 0) {
        releaseQueue.shift()
        head.onDone?.()
      }
    }
    nudgeMarkers()
  }

  const typewriter = (deps.typewriterFactory ?? createTypewriter)(
    routeRelease,
    setProseActive,
  )

  /** Queue `text` for `rowId` (ownership pinned HERE, at the input event)
   * and hand it to the typewriter in the same breath. */
  const pushChunk = (rowId: string, text: string, onDone?: () => void) => {
    releaseQueue.push({ rowId, remaining: text.length, onDone })
    typewriter.push(text)
  }

  const onCheckpoint = (text: string, at?: string) => {
    if (!text.trim()) return
    const cpId = `${baseId}#cp${++checkpointCount}`
    if (receivedAny) {
      // Path A — settle IN PLACE, synchronously: the row rekeys NOW (its
      // array position and birthKey never move), its unreleased chars are
      // re-attributed to the checkpoint id, and the frame's authoritative
      // text lands when those chars finish typing. The main identity
      // resets at the same instant — later deltas and activity rows can
      // never be swallowed by this settle.
      apply((prev) =>
        prev.map((m) =>
          m.id === baseId ? { ...m, id: cpId, at: at ?? m.at } : m,
        ),
      )
      for (const entry of releaseQueue) {
        if (entry.rowId === baseId) entry.rowId = cpId
      }
      // Path A preserves the row's display identity as well as birthKey:
      // text already visible before the rekey must NOT fire a second
      // first-visible signal after later activity rows have joined.
      if (visibleRows.delete(baseId)) visibleRows.add(cpId)
      releaseQueue.push({
        rowId: cpId,
        remaining: 0,
        onDone: () =>
          apply((prev) =>
            prev.map((m) =>
              m.id === cpId
                ? {
                    ...m,
                    content: text,
                    streaming: false,
                    proseDrainedAtMs: Date.now(),
                  }
                : m,
            ),
          ),
      })
      previewText = ""
      streamedAny = false
      receivedAny = false
      nudgeMarkers()
      return
    }
    // Path B — pin the row NOW (出生钉位), pace the text into it through
    // the same typewriter; the settle markers ride the same queue, so a
    // main-segment delta arriving mid-typing routes to its OWN row.
    ensureSpeechRow(cpId, at)
    releaseQueue.push({
      rowId: baseId,
      remaining: 0,
      onDone: () =>
        apply((prev) =>
          prev.map((m) =>
            m.id === baseId && m.content ? { ...m, streaming: false } : m,
          ),
        ),
    })
    pushChunk(cpId, text, () =>
      apply((prev) =>
        prev.map((m) =>
          m.id === cpId
            ? { ...m, streaming: false, proseDrainedAtMs: Date.now() }
            : m,
        ),
      ),
    )
    nudgeMarkers()
  }

  return {
    onDelta: (delta: string) => {
      // An empty delta is transport noise, not a reply birth and never a
      // work-segment closing signal.
      if (!delta) return
      // A delta's owner is ALWAYS the main segment — pinned at receipt,
      // regardless of what the typewriter is still displaying.
      receivedAny = true
      ensureSpeechRow(baseId)
      pushChunk(baseId, delta)
    },
    onCheckpoint,
    push: (text: string) => {
      if (!text) return
      ensureSpeechRow(baseId)
      pushChunk(baseId, text)
    },
    drain: () => typewriter.drain(),
    flush: () => typewriter.flush(),
    get previewText() {
      return previewText
    },
    get streamedAny() {
      return streamedAny
    },
  }
}
