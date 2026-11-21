"""Remove the retired manual canvas and its Chat capability flag."""

from alembic import op

revision = "j6d01_retire_canvas"
down_revision = "j6c02_media_jobs"
branch_labels = depends_on = None


def upgrade():
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")
    op.drop_column("conversations", "canvas_available")


def downgrade():
    raise NotImplementedError("The retired manual canvas cannot be reconstructed.")
