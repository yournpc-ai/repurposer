import type { OverlayMessage } from "./types"

/** Register a real server id without promoting the local React/typewriter
 * key. If the slow archive twin arrived first, retire only that projection;
 * an archived QA row and its assistant echo are distinct visible facts. */
export function stampServerMessageId(
  prev: OverlayMessage[],
  localId: string,
  serverMessageId: string,
): OverlayMessage[] {
  const local = prev.find((message) => message.id === localId)
  if (!local) return prev
  const aliases = [...new Set([
    ...(local.serverIdAliases ?? []),
    ...(local.serverMessageId ? [local.serverMessageId] : []),
    serverMessageId,
  ])]
  const archivedTwin = (id: string) => aliases.some(
    (alias) => id === alias || id === `${alias}-echo`,
  )
  return prev
    .filter((message) =>
      message.id === localId || message.qa != null || !archivedTwin(message.id),
    )
    .map((message) =>
      message.id === localId
        ? { ...message, serverMessageId, serverIdAliases: aliases }
        : message,
    )
}

/** Mount replay fills only missing real identities. Existing optimistic rows
 * keep their birthKey, array position, typing state and visible prefix. */
export function prependMissingHistory(
  prev: OverlayMessage[],
  history: OverlayMessage[],
): OverlayMessage[] {
  const known = new Set(prev.map((message) => message.id))
  const aliases = new Set(
    prev.flatMap((message) => [
      ...(message.serverMessageId ? [message.serverMessageId] : []),
      ...(message.serverIdAliases ?? []),
    ]),
  )
  const missing = history.filter((message) => {
    if (known.has(message.id)) return false
    // A QA archive has the persisted question id while its echo uses -echo.
    // Never let the echo alias swallow the independent QA projection.
    if (message.qa) return true
    const serverId = message.id.endsWith("-echo") ? message.id.slice(0, -5) : message.id
    return !aliases.has(serverId)
  })
  return missing.length > 0 ? [...missing, ...prev] : prev
}
