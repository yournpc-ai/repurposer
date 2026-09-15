"""Pure tests for the FK-safe outputs deletion order (Gate #2 Commit 2).

No DB, no LLM, no HTTP: a statement-recording stub session (the
test_graph_wiring_pure.py pattern) asserts every ``delete_outputs_fk_safe``
call issues its DELETEs in the projects.py:715-717 order — operations
(NO ACTION FK) → publications (RESTRICT FK) → outputs — for both the
id-list and the SELECT forms, and that an empty id list issues nothing.
The order IS the contract: any path deleting an output that carries
journaled ops or publication rows dies at the FK without it.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.sql.dml import Delete

from app.models.tables import Output
from app.pipeline.outputs import delete_outputs_fk_safe


class _StubDb:
    """Records the target table of every DELETE it is asked to execute."""

    def __init__(self):
        self.deleted_tables: list[str] = []

    async def execute(self, stmt, *args, **kwargs):
        assert isinstance(stmt, Delete), f"expected DELETEs only, got {stmt!r}"
        self.deleted_tables.append(stmt.table.name)
        return None


@pytest.mark.asyncio
async def test_id_list_deletes_in_fk_safe_order():
    db = _StubDb()
    await delete_outputs_fk_safe(db, [uuid4(), uuid4()])
    assert db.deleted_tables == ["operations", "publications", "outputs"]


@pytest.mark.asyncio
async def test_select_form_deletes_in_fk_safe_order():
    """The bulk-predicate call sites (derivative sweep) hand in a SELECT of
    outputs.id — same three deletes, same order."""
    db = _StubDb()
    doomed = select(Output.id).where(Output.type == "quote_frame")
    await delete_outputs_fk_safe(db, doomed)
    assert db.deleted_tables == ["operations", "publications", "outputs"]


@pytest.mark.asyncio
async def test_empty_id_list_is_a_noop():
    db = _StubDb()
    await delete_outputs_fk_safe(db, [])
    assert db.deleted_tables == []
