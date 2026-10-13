/** 消息 copy (flora-parity-ui D4②): 纯客户端剪贴板 —— 零网络、零
 * toast（静默档: 成功 = 图标一拍翻 ✓，失败同样安静，剪贴板被拒不是
 * 对话的事实）。writer 注入 = vitest 纯套件缝（生产传
 * navigator.clipboard.writeText）。 */

export type ClipboardWriter = (text: string) => Promise<void>

/** Returns whether the text landed on the clipboard — the caller's only
 * feedback channel is the local icon beat, never a toast. */
export async function copyMessageText(
  text: string,
  write: ClipboardWriter,
): Promise<boolean> {
  try {
    await write(text)
    return true
  } catch {
    return false
  }
}
