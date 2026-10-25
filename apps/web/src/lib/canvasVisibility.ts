/** 环境谓词 (ADR-118 §6 真值表 · web 半座): canvasVisible = 画布此刻在屏
 * ——渲染时刻状态，非历史快照。单源律: 项目路由的画布显隐判定与 chat
 * 锚卡共用此谓词；任何组件不得再以视口宽度 / 设备名 / 设置项自行推断
 * 环境（禁设备名硬编码）。双键的另一半（canvas_available /
 * canvas_visible 进 context 装配）在服务端装配层——互指 api 半座
 * apps/api/app/chat/canvas_visibility.py（谓词同义；能力位随每条 chat
 * 请求送达 = ChatTurnBody.canvas_available）；这里只有渲染分支。 */

/** 用户的工作区布局偏好（ADR-123 —— users.settings `workspace_layout`，
 * 全栈同名）。 */
export type WorkspaceLayout = "auto" | "chat"

/** 能力位合成座 (ADR-123 —— canvas_available 的唯一组成处): 视口可承载
 * ∧ 用户未钉纯对话。chat 档只能把画布关掉，永不反向强制（<iPad 无画布
 * 是架构禁令，强制档在移动端是虚假承诺）。 */
export function canvasCapableFor(
  isMobile: boolean,
  workspaceLayout: WorkspaceLayout,
): boolean {
  return !isMobile && workspaceLayout !== "chat"
}

export interface CanvasEnvironment {
  /** 视口可承载画布且用户未钉纯对话（canvas_available 的客户端读数——
   * 由 canvasCapableFor 唯一合成；谓词本身永不命名设备）。 */
  canvasAvailable: boolean
  /** 世界已揭幕（路由既有 worldLive 驱动：hasRuns || plan-ready，
   * ADR-111 的 reveal 律不变）。 */
  worldLive: boolean
}

/** canvas_visible = 可承载 ∧ 已揭幕。真值表两钉：桌面 true/true → 零锚
 * 卡；移动 false/false → 锚卡渲染。交付正文在各分支都不增加界面引导。
 * 移动是世界已揭幕（false/true）同样无画布 —— 画布在 768px 以下永不挂载。 */
export function canvasVisible(env: CanvasEnvironment): boolean {
  return env.canvasAvailable && env.worldLive
}

/** 锚卡渲染谓词 —— 渲染 ⟺ !canvas_visible（同一次 run 双端唯一的分支
 * 点；锚卡 = 终态收据帧，静态、零订阅）。 */
export function anchorCardsVisible(env: CanvasEnvironment): boolean {
  return !canvasVisible(env)
}
