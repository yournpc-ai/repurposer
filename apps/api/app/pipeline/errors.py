"""Pipeline execution error taxonomy (agent-loop-upgrade W3).

Kept import-free so every layer (tools / node classes / orchestrator) can
share it without cycles.
"""


class TransientNodeError(Exception):
    """A retryable step failure: provider / network / storage hiccups.

    ``execute_step`` resets the node to ``pending`` (the worker's next tick is
    the backoff) when the kind carries retry budget (``NodeBase.retries``);
    anything else fails fast. Deterministic failures — missing inputs, empty
    batches, validation errors — must raise ordinary exceptions so they never
    burn retry budget.
    """
