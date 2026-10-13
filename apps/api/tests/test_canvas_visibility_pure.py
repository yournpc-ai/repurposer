"""Pure tests for 环境双键装配 (ADR-118 §6 — flora-parity-ui ③ 锚卡的 API
装配半边; 客户端谓词互指 apps/web/src/lib/canvasVisibility.ts).

Gated here (no DB / no LLM / no HTTP — the _StubDb pattern):

- **canvas_visible**: the truth table + None propagation — unknown ≠ false
  (the capability bit unreported reads as UNKNOWN, and the handoff gate
  stays closed on unknown: never fabricate a pointer at a product row that
  might not exist).
- **environment_line**: the structured context fact's wording / absence
  (None-renders-nothing, the surface_line precedent).
- **build_context**: the Environment line rides directly under the Project
  line; world_live = hasRuns ∨ pending-plan (与客户端谓词同义 — the
  plan-ready term is dead weight for the delivery gate: anchor cards render
  only under a terminal receipt, and a receipt exists ⟹ hasRuns=true);
  the line is omitted when the capability is unreported.
- **承接句谓词分支真值表** (the prompt-law gate's code-side pin — the law's
  seat is prompts/chat/trigger_system.j2): desktop (available=true, world
  live) → canvas_visible=true → 零承接句零锚卡; mobile (false) →
  canvas_visible=false → 承接句 + 锚卡渲染。
"""

from uuid import uuid4

import pytest

from app.chat.canvas_visibility import canvas_visible, environment_line
from app.chat.context import build_context
from app.models.tables import (
    Asset,
    ExplorationRow,
    GraphNode,
    Journey,
    Message,
    Output,
    Project,
    WorkflowRun,
)

_PROJECT_ID = uuid4()


# ---- the stub db (test_memory_narrow_pure pattern — serves every entity
# build_context queries off lists; where criteria stay unevaluated) --------


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _StubDb:
    def __init__(self, *, runs=()):
        self.runs = list(runs)

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        rows = {
            Asset: [],
            Output: [],
            GraphNode: [],
            ExplorationRow: [],
            Journey: [],
            WorkflowRun: self.runs,
        }.get(entity, [])
        return _StubResult(list(rows))


def _project() -> Project:
    return Project(id=_PROJECT_ID, title="Demo", language="en")


def _run() -> WorkflowRun:
    return WorkflowRun(id=uuid4(), project_id=_PROJECT_ID, status="completed")


def _pending_plan() -> Message:
    return Message(question={"kind": "task_book"}, answer=None)


# ---- canvas_visible: the truth table --------------------------------------


class TestCanvasVisibleTruthTable:
    def test_desktop_world_live_is_visible(self) -> None:
        # 桌面钉 (true/true): 零锚卡零承接句。
        assert canvas_visible(True, True) is True

    def test_mobile_is_never_visible(self) -> None:
        # 移动钉 (false/*): 锚卡渲染 + 承接句门开 — world_live 救不回
        # 能力位（768px 以下画布永不挂载）。
        assert canvas_visible(False, True) is False
        assert canvas_visible(False, False) is False

    def test_desktop_pre_reveal_is_not_visible(self) -> None:
        # 桌面 pre-reveal (true/false): 画布未揭幕 — 谓词诚实读 false
        # （此状态无终态收据,锚卡本无可渲染之物）。
        assert canvas_visible(True, False) is False

    def test_unknown_capability_propagates_none(self) -> None:
        # None 传播 — 未知不是 false: 承接句门对未知恒闭 (永不编造)。
        assert canvas_visible(None, True) is None
        assert canvas_visible(None, False) is None


# ---- environment_line: the structured context fact -------------------------


class TestEnvironmentLine:
    def test_wording(self) -> None:
        assert (
            environment_line(True, True)
            == "Environment: canvas_available=true canvas_visible=true"
        )
        assert (
            environment_line(False, True)
            == "Environment: canvas_available=false canvas_visible=false"
        )
        assert (
            environment_line(True, False)
            == "Environment: canvas_available=true canvas_visible=false"
        )

    def test_unknown_renders_nothing(self) -> None:
        assert environment_line(None, True) is None
        assert environment_line(None, False) is None


# ---- build_context: the assembly seat --------------------------------------


class TestBuildContextEnvironment:
    @pytest.mark.asyncio
    async def test_desktop_delivery_line(self) -> None:
        """桌面钉: available=true + 已有 run (world live) → visible=true
        → 承接句门闭 (trigger_system.j2 的 DELIVERY HANDOFF 法条)。"""
        ctx = await build_context(
            _StubDb(runs=[_run()]), _project(), [], [], None,
            canvas_available=True,
        )
        lines = ctx["text"].split("\n")
        assert lines[1] == "Environment: canvas_available=true canvas_visible=true"

    @pytest.mark.asyncio
    async def test_mobile_delivery_line(self) -> None:
        """移动钉: available=false → visible=false → 承接句门开 + 锚卡渲染
        (⟺ !canvas_visible)。"""
        ctx = await build_context(
            _StubDb(runs=[_run()]), _project(), [], [], None,
            canvas_available=False,
        )
        lines = ctx["text"].split("\n")
        assert lines[1] == "Environment: canvas_available=false canvas_visible=false"

    @pytest.mark.asyncio
    async def test_pending_plan_counts_as_world_live(self) -> None:
        """world_live = hasRuns ∨ pending-plan: 计划已 dock 但首跑未起时,
        桌面画布已揭幕 (plan-ready reveal 的安全过近似)。"""
        ctx = await build_context(
            _StubDb(), _project(), [], [], _pending_plan(),
            canvas_available=True,
        )
        lines = ctx["text"].split("\n")
        assert lines[1] == "Environment: canvas_available=true canvas_visible=true"

    @pytest.mark.asyncio
    async def test_no_run_no_plan_is_not_world_live(self) -> None:
        ctx = await build_context(
            _StubDb(), _project(), [], [], None,
            canvas_available=True,
        )
        lines = ctx["text"].split("\n")
        assert lines[1] == "Environment: canvas_available=true canvas_visible=false"

    @pytest.mark.asyncio
    async def test_unreported_capability_omits_the_line(self) -> None:
        """未知恒闭: 能力位未上报 (旧客户端 / worker 路径无戳) → Environment
        行缺席, 承接句门闭 — 永不编造指向可能不存在的产物行的句子。"""
        ctx = await build_context(
            _StubDb(runs=[_run()]), _project(), [], [], None,
        )
        assert "Environment:" not in ctx["text"]

    @pytest.mark.asyncio
    async def test_default_param_keeps_old_callers_silent(self) -> None:
        """读容忍: 不传 canvas_available 的旧调用方 (零环境事实) 行为不变。"""
        ctx = await build_context(_StubDb(), _project(), [], [], None)
        assert "Environment:" not in ctx["text"]
