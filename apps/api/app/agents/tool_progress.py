"""Progress belongs to one execution, including work it delegates to child tasks."""
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolProgress:
    call_id: str
    step: str


_reporter: ContextVar[Callable[[str], Awaitable[None]] | None] = ContextVar(
    "tool_progress_reporter", default=None,
)


_call_id: ContextVar[str | None] = ContextVar("native_call_id", default=None)


def current_call_id() -> str | None:
    return _call_id.get()


@contextmanager
def bind_progress(
    call_id: str, emit: Callable[[ToolProgress], Awaitable[None] | None] | None,
) -> Iterator[None]:
    active = True

    async def report(step: str) -> None:
        if active and emit is not None:
            result = emit(ToolProgress(call_id, step))
            if result is not None:
                await result

    identity = _call_id.set(call_id)
    token = _reporter.set(report)
    try:
        yield
    finally:
        active = False
        _reporter.reset(token)
        _call_id.reset(identity)


async def report_progress(step: str) -> None:
    report = _reporter.get()
    if report is not None:
        await report(step)
