"""unify names: chat_sessions → conversations, plan_nodes → workflow_steps, + messages.mentions

NAMING 判例 N-12 / N-13 / N-15（docs/tasks/chat-loop-v1.md Task 0）：
- chat_sessions 表 → conversations（session 撞 auth session；OpenAI Conversations API 同款）
- messages.session_id → conversation_id（含索引名）
- plan_nodes 表 → workflow_steps（plan 一词三用歧义；表对词族统一
  workflow_runs+workflow_steps；前端早已叫 step；Mastra workflow steps 同构。
  概念层 RunPlan 不动——这不是 N-10 翻案，是存储层对齐行业词）
- outputs.plan_node_id → workflow_step_id（含索引名）
- messages.mentions JSONB default []（@ 实体引用座位，chat-loop-v1 Task 3）

Revision ID: c4a9e2f17b03
Revises: b2d6f9a53e18
Create Date: 2026-07-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c4a9e2f17b03"
down_revision: Union[str, Sequence[str], None] = "b2d6f9a53e18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # chat_sessions → conversations
    op.rename_table("chat_sessions", "conversations")
    op.execute("ALTER INDEX ix_chat_sessions_project_id RENAME TO ix_conversations_project_id")
    op.execute("ALTER INDEX ix_chat_sessions_asset_id RENAME TO ix_conversations_asset_id")
    op.alter_column("messages", "session_id", new_column_name="conversation_id")
    op.execute("ALTER INDEX ix_messages_session_id RENAME TO ix_messages_conversation_id")

    # plan_nodes → workflow_steps
    op.rename_table("plan_nodes", "workflow_steps")
    op.execute("ALTER INDEX ix_plan_nodes_run_status RENAME TO ix_workflow_steps_run_status")
    op.execute("ALTER INDEX ix_plan_nodes_kind_status RENAME TO ix_workflow_steps_kind_status")
    op.alter_column("outputs", "plan_node_id", new_column_name="workflow_step_id")
    op.execute("ALTER INDEX ix_outputs_plan_node_id RENAME TO ix_outputs_workflow_step_id")

    # messages.mentions seat (@ entity refs; picker UI is a later iteration)
    op.add_column(
        "messages",
        sa.Column("mentions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("messages", "mentions")

    op.execute("ALTER INDEX ix_outputs_workflow_step_id RENAME TO ix_outputs_plan_node_id")
    op.alter_column("outputs", "workflow_step_id", new_column_name="plan_node_id")
    op.execute("ALTER INDEX ix_workflow_steps_kind_status RENAME TO ix_plan_nodes_kind_status")
    op.execute("ALTER INDEX ix_workflow_steps_run_status RENAME TO ix_plan_nodes_run_status")
    op.rename_table("workflow_steps", "plan_nodes")

    op.execute("ALTER INDEX ix_messages_conversation_id RENAME TO ix_messages_session_id")
    op.alter_column("messages", "conversation_id", new_column_name="session_id")
    op.execute("ALTER INDEX ix_conversations_asset_id RENAME TO ix_chat_sessions_asset_id")
    op.execute("ALTER INDEX ix_conversations_project_id RENAME TO ix_chat_sessions_project_id")
    op.rename_table("conversations", "chat_sessions")
