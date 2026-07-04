"""Temporary shim: re-export the refactored ClipAgent under legacy names.

This file exists to avoid breaking imports during the planner → clip_agent
migration. New code should import from ``app.agents.clip_agent``. This shim will
be removed in a follow-up cleanup.
"""

from app.agents.clip_agent import ClipAgent, clip_agent

__all__ = ["ContentPlannerAgent", "planner_agent"]

ContentPlannerAgent = ClipAgent
planner_agent = clip_agent
