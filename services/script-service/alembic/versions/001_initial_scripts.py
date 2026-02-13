"""Initial scripts table

Revision ID: 001
Revises: None
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("poi_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("tone", sa.String(50), nullable=False, server_default="warm"),
        sa.Column("total_duration_seconds", sa.Float(), nullable=False, server_default="30.0"),
        sa.Column("scenes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("narration_text", sa.Text(), nullable=True),
        sa.Column("nlp_provider", sa.String(50), nullable=False, server_default="stub"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scripts_poi_id", "scripts", ["poi_id"])


def downgrade() -> None:
    op.drop_index("ix_scripts_poi_id")
    op.drop_table("scripts")
