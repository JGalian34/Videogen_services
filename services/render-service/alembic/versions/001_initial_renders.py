"""Initial render_jobs and render_scenes tables

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
        "render_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("poi_id", sa.Uuid(), nullable=False),
        sa.Column("script_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_scenes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_scenes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_path", sa.String(1000), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_render_jobs_poi_id", "render_jobs", ["poi_id"])

    op.create_table(
        "render_scenes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("render_job_id", sa.Uuid(), sa.ForeignKey("render_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("visual_prompt", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("output_path", sa.String(1000), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("provider", sa.String(50), nullable=False, server_default="stub"),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("render_scenes")
    op.drop_index("ix_render_jobs_poi_id")
    op.drop_table("render_jobs")
