"""Typed harness stops that must retain their identity across Agent calls."""


class AgentStopError(Exception):
    """A bounded execution stopped; fallback cannot restart it."""


class AgentBudgetError(AgentStopError):
    """The shared execution budget is exhausted."""


class AgentOutputError(AgentStopError):
    """The bounded output correction was exhausted."""
