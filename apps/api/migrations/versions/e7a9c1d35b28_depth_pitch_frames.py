"""replay graph frames onto the depth-pitch law (统一摆位律)

Revision ID: e7a9c1d35b28
Revises: d8e9f0a1b2c3
Create Date: 2026-09-09

The frame law changed (ADR-057 follow-up, 2026-09-09 拍板): columns are now
DEPTH-pitched — x = depth × pitch — instead of derived from a parent's
right edge (mixed frame widths made parent-right columns ragged: same-depth
siblings could drift into horizontal overlap), and a fresh column's first
node rises above its topmost parent (the port-geometry delta — the out→in
arc stays gentle). Frames are assigned once at birth and existing frames
never move in live operation (append-only 保序律) — so the worlds born
under the old law are replayed HERE, once, at deploy time: every project's
full node+edge set is re-laid-out by the new law in parents-first birth
order. Pure data rewrite of graph_nodes.layout; no schema change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e7a9c1d35b28"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The law's constants, inlined — a migration must stay correct even if the
# app's values later move (see graph_store._PITCH/_FRESH_COLUMN_RISE).
_PITCH = 436  # max frame width (340) + main gap (96)
_GAP_CROSS = 24
_FRESH_COLUMN_RISE = 126
_FRAME_CLASS = {
    "asset": (280, 260),
    "document": (260, 200),
    "text": (340, 440),
    "clip": (280, 660),
}
_KIND_FRAME_CLASS = {"asset": "asset", "document": "document"}

nodes = sa.table(
    "graph_nodes",
    sa.column("id", sa.UUID),
    sa.column("project_id", sa.UUID),
    sa.column("kind", sa.String),
    sa.column("spec", postgresql.JSONB),
    sa.column("layout", postgresql.JSONB),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
edges = sa.table(
    "graph_edges",
    sa.column("project_id", sa.UUID),
    sa.column("from_node", sa.UUID),
    sa.column("to_node", sa.UUID),
)


def _frame_of(kind: str, spec: dict) -> tuple[int, int]:
    cls = _KIND_FRAME_CLASS.get(kind) or str((spec or {}).get("frame_class") or "") or "clip"
    return _FRAME_CLASS.get(cls, _FRAME_CLASS["clip"])


def upgrade() -> None:
    conn = op.get_bind()
    project_ids = conn.execute(sa.select(nodes.c.project_id).distinct()).scalars().all()
    for pid in project_ids:
        rows = conn.execute(
            sa.select(nodes.c.id, nodes.c.kind, nodes.c.spec, nodes.c.created_at).where(
                nodes.c.project_id == pid
            )
        ).all()
        edge_rows = conn.execute(
            sa.select(edges.c.from_node, edges.c.to_node).where(edges.c.project_id == pid)
        ).all()
        by_id = {r.id for r in rows}
        parents: dict = {r.id: [] for r in rows}
        for from_node, to_node in edge_rows:
            if from_node in by_id and to_node in by_id:
                parents[to_node].append(from_node)

        # Depth = the topological generation (max parent depth + 1,
        # islands 0), memoized; the trail guard keeps a poisoned world
        # (a cycle) from looping forever.
        depth_memo: dict = {}

        def depth_of(nid, trail=()) -> int:
            memo = depth_memo.get(nid)
            if memo is not None:
                return memo
            if nid in trail:
                return 0
            ups = parents.get(nid, [])
            d = 0 if not ups else max(depth_of(u, trail + (nid,)) for u in ups) + 1
            depth_memo[nid] = d
            return d

        # Parents-first replay in birth order — mirrors
        # graph_store.settle_frames_with_edges' passes.
        pending = sorted(rows, key=lambda r: (r.created_at is None, r.created_at, str(r.id)))
        frames: dict = {}
        settled: set = set()
        while pending:
            progressed = False
            for r in list(pending):
                ups = parents[r.id]
                if any(u not in settled for u in ups):
                    continue
                depth = depth_of(r.id)
                w, h = _frame_of(r.kind, r.spec)
                column = [m for m in settled if depth_of(m) == depth]
                if column:
                    y = max(frames[m]["y"] + frames[m]["h"] for m in column) + _GAP_CROSS
                elif ups:
                    y = min(frames[u]["y"] for u in ups) - _FRESH_COLUMN_RISE
                else:
                    y = 0
                frames[r.id] = {"x": depth * _PITCH, "y": y, "w": w, "h": h}
                settled.add(r.id)
                pending.remove(r)
                progressed = True
            if not progressed:
                for r in pending:
                    depth = depth_of(r.id)
                    w, h = _frame_of(r.kind, r.spec)
                    frames[r.id] = {"x": depth * _PITCH, "y": 0, "w": w, "h": h}
                    settled.add(r.id)
                break

        for nid, frame in frames.items():
            conn.execute(nodes.update().where(nodes.c.id == nid).values(layout=frame))


def downgrade() -> None:
    # Frames are derived data — the pre-law geometry is not recoverable.
    pass
