/** 环境谓词 (ADR-118 §6 真值表 · web 半座): canvasVisible = 画布此刻在屏
 * ——渲染时刻状态，非历史快照。单源律: 项目路由的画布显隐判定与 chat
 * 锚卡共用此谓词；任何组件不得再以视口宽度 / 设备名自行推断环境（禁设
 * 备名硬编码）。双键的另一半（canvas_available / canvas_visible 进
 * context 装配）在服务端装配层——互指 api 半座
 * apps/api/app/chat/canvas_visibility.py（谓词同义；能力位随每条 chat
 * 请求送达 = ChatTurnBody.canvas_available）；这里只有渲染分支。 */

export interface CanvasEnvironment {
  /** 视口可承载画布（≥768px 事实 —— canvas_available 的客户端读数，
   * 由 use-mobile 的断点供给；谓词本身永不命名设备）。 */
  canvasAvailable: boolean
  /** 世界已揭幕（路由既有 worldLive 驱动：hasRuns || plan-ready，
   * ADR-111 的 reveal 律不变）。 */
  worldLive: boolean
}

/** canvas_visible = 可承载 ∧ 已揭幕。真值表两钉：桌面 true/true → 零锚
 * 卡零承接句；移动 false/false → 锚卡渲染 + 承接句。移动是世界已揭幕
 * （false/true）同样无画布 —— 画布在 768px 以下永不挂载。 */
export function canvasVisible(env: CanvasEnvironment): boolean {
  return env.canvasAvailable && env.worldLive
}

/** 锚卡渲染谓词 —— 渲染 ⟺ !canvas_visible（同一次 run 双端唯一的分支
 * 点；锚卡 = 终态收据帧，静态、零订阅）。 */
export function anchorCardsVisible(env: CanvasEnvironment): boolean {
  return !canvasVisible(env)
}
