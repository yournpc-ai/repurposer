"""defer runner-parent FK checks to COMMIT (D9, ADR-050)

Revision ID: c3a9e71f52d0
Revises: b7c2d4e6f801
Create Date: 2026-08-28

Four foreign keys become DEFERRABLE INITIALLY DEFERRED:

- ``outputs.workflow_step_id`` (→ workflow_steps) — the proven D9 wedge:
  writers INSERT outputs inside a Session 2 that spans LLM awaits; the
  immediate FK check KEY-SHARE-locks the parent step row until commit, and
  the runner's OWN display writers (step_display._set_stage/_set_summary,
  render mirrors — own-session jsonb_set UPDATEs of that same row) then wait
  on the runner's own transaction: application-level self-deadlock, the
  exact lock shape the metering per-call UPDATEs had before they went
  in-memory.
- ``outputs.project_id`` / ``operations.project_id`` (→ projects) — same
  family: run-end project updaters (maybe_finalize's status flip) stall on
  mid-run KEY SHARE locks otherwise.
- ``workflow_steps.run_id`` (→ workflow_runs) — fan-out runners INSERT steps
  mid-run; run-row updaters (maybe_finalize, status flips) stall the same
  way.

Integrity is unchanged — the constraint is still enforced, just checked at
COMMIT instead of at statement time. The mid-run row-lock window disappears;
commit-time checks serialize against only brief writer transactions.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3a9e71f52d0'
down_revision: Union[str, Sequence[str], None] = 'b7c2d4e6f801'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FKS = [
    # (table, constraint, definition sans deferrability)
    (
        "outputs",
        "outputs_plan_node_id_fkey",
        "FOREIGN KEY (workflow_step_id) REFERENCES workflow_steps(id) ON DELETE SET NULL",
    ),
    (
        "outputs",
        "outputs_project_id_fkey",
        "FOREIGN KEY (project_id) REFERENCES projects(id)",
    ),
    (
        "operations",
        "operations_project_id_fkey",
        "FOREIGN KEY (project_id) REFERENCES projects(id)",
    ),
    (
        "workflow_steps",
        "plan_nodes_run_id_fkey",
        "FOREIGN KEY (run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE",
    ),
]


def upgrade() -> None:
    for table, name, definition in _FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} {definition} "
            "DEFERRABLE INITIALLY DEFERRED"
        )


def downgrade() -> None:
    for table, name, definition in _FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} {definition}")
