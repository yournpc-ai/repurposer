/** A post-open SSE transport failure. The request may already have committed
 * server-side, so callers can recover through read-only archive reads instead
 * of repeating the user action. Pre-open failures stay unmarked: acceptance is
 * not yet proven. */
export class StreamTransportError extends TypeError {
  constructor(cause: TypeError) {
    super(cause.message, { cause })
    this.name = "StreamTransportError"
  }
}

/** fetch-event-source reports body-reader disconnects as TypeError. A frame
 * callback can also throw TypeError; frameFailed keeps that application error
 * on its own path instead of mislabeling it as a network disconnect. */
export function normalizeStreamError(
  error: unknown,
  streamOpened: boolean,
  frameFailed = false,
): unknown {
  if (
    !streamOpened ||
    frameFailed ||
    error instanceof StreamTransportError ||
    !(error instanceof TypeError)
  ) {
    return error
  }
  return new StreamTransportError(error)
}

