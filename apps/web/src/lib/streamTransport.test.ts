/** Chat creation must survive a lost SSE receipt without repeating the user's
 * action. Only a post-open transport failure earns read-only archive recovery;
 * pre-open, terminal, abort, and frame-processing failures keep their existing
 * semantics. */

import { describe, expect, it } from "vitest"

import { normalizeStreamError, StreamTransportError } from "./streamTransport"

describe("normalizeStreamError", () => {
  it("marks a post-open body-reader TypeError as recoverable transport loss", () => {
    const cause = new TypeError("network error")
    const error = normalizeStreamError(cause, true)

    expect(error).toBeInstanceOf(StreamTransportError)
    expect(error).toBeInstanceOf(TypeError)
    expect((error as Error).message).toBe("network error")
    expect((error as Error).cause).toBe(cause)
  })

  it("leaves a pre-open TypeError unmarked because acceptance is unproven", () => {
    const cause = new TypeError("Failed to fetch")
    expect(normalizeStreamError(cause, false)).toBe(cause)
  })

  it("keeps a frame callback TypeError on the application failure path", () => {
    const cause = new TypeError("Cannot read properties of undefined")
    expect(normalizeStreamError(cause, true, true)).toBe(cause)
  })

  it("does not wrap an already classified transport failure twice", () => {
    const cause = new StreamTransportError(new TypeError("network error"))
    expect(normalizeStreamError(cause, true)).toBe(cause)
  })

  it.each([
    new Error("stream closed"),
    new SyntaxError("Unexpected token"),
  ])("keeps non-transport failures on their own path: %s", (error) => {
    expect(normalizeStreamError(error, true)).toBe(error)
  })
})

