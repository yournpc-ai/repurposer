/** 工作区布局偏好 (ADR-123): users.settings `workspace_layout` 的客户端
 * 镜像。服务端是跨设备真值源，但首条 chat 消息挂载即发出并给会话盖
 * `canvas_available` 章（last-wins）——设置必须在首帧/首章同步可读，
 * 故本地镜像（localStorage，主题先例）；GeneralSection 挂载时以 server
 * 值回写镜像（server wins）。
 *
 * SSR 律：localStorage 只在 effect / 事件处理器读——hook 初值恒
 * `"auto"`（SSR 与首渲一致），挂载 effect 矫正（use-mobile 同族先例）。
 * 画布 reveal 依赖网络帧，矫正远早于它，无闪烁。 */

import { useEffect, useState } from "react"

import type { WorkspaceLayout } from "@/lib/canvasVisibility"

const MIRROR_KEY = "repurposer-workspace-layout"
const CHANGE_EVENT = "repurposer:workspace-layout"

function readMirror(): WorkspaceLayout {
  return window.localStorage.getItem(MIRROR_KEY) === "chat" ? "chat" : "auto"
}

/** The mirror's one write seat: the settings dialog's successful PUT (and
 * its server-value resync on mount) writes here and notifies this tab's
 * hooks. */
export function writeWorkspaceLayoutMirror(value: WorkspaceLayout) {
  try {
    window.localStorage.setItem(MIRROR_KEY, value)
  } catch {
    /* storage denied — session-only then */
  }
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

export function useWorkspaceLayout(): WorkspaceLayout {
  const [layout, setLayout] = useState<WorkspaceLayout>("auto")
  useEffect(() => {
    setLayout(readMirror())
    const onChange = () => setLayout(readMirror())
    window.addEventListener(CHANGE_EVENT, onChange)
    return () => window.removeEventListener(CHANGE_EVENT, onChange)
  }, [])
  return layout
}
