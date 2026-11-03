"""auth_connections

Revision ID: 084_custom
Revises: 083
Create Date: 2026-09-20 22:09:56.242158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '084_custom'
down_revision: Union[str, Sequence[str], None] = '083'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("auth_type", sa.String(30), nullable=False),
        sa.Column("credentials", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_auth_connections_user_id", "auth_connections", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_auth_connections_user_id", table_name="auth_connections")
    op.drop_table("auth_connections")
