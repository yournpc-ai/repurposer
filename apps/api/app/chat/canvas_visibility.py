"""环境谓词 (ADR-118 §6 真值表 · api 半座): canvas_visible = 画布此刻在屏
= canvas_available ∧ world_live。与客户端谓词同义单源 —— 互指:
apps/web/src/lib/canvasVisibility.ts（锚卡渲染 ⟺ !canvas_visible，渲染时
刻状态）。

- ``canvas_available`` = 视口可承载画布（客户端能力位，随每条 chat 请
  求送达并盖章到会话行——prepare_chat_turn 的 ui_language 同律座）。
  None = 客户端未上报（旧客户端 / 无 sendChat 回合）：未知不是 false，
  谓词传播 None，Environment 行缺席。
- ``world_live`` 的服务端读数 = hasRuns ∨ pending-plan。客户端谓词另有
  一个 plan-ready 项（hasRuns || (!isMobile && planReady)）——对锚卡渲染
  它是死重：锚卡只在终态收据下渲染，而收据存在 ⟹ hasRuns=true，两端
  谓词在一切可渲染时刻同义；pending-plan 是 plan-ready 的安全过近似。

双键 = LLM 唯一合法环境源（禁从用户语言/设备特征推断环境），这里只有
谓词与事实行。交付正文不根据环境行介绍界面入口或输出内部 ID；产物卡
由客户端独立渲染。
"""

from __future__ import annotations


def canvas_visible(canvas_available: bool | None, world_live: bool) -> bool | None:
    """渲染时刻谓词的服务端半边。None 传播——能力位未上报时可见性未知，
    不把未知伪报成 false。"""
    if canvas_available is None:
        return None
    return canvas_available and world_live


def environment_line(canvas_available: bool | None, world_live: bool) -> str | None:
    """The context-assembly fact line (结构化双键进 context 装配，不是
    prompt 散文提示)。None = 未知 → 行缺席（surface_line 的
    None-renders-nothing 先例）；此行不承担交付言语指令。"""
    visible = canvas_visible(canvas_available, world_live)
    if visible is None:
        return None
    return (
        f"Environment: canvas_available={str(canvas_available).lower()} "
        f"canvas_visible={str(visible).lower()}"
    )
