"""Add voiceover and publish fields to render_jobs

Revision ID: 002
Revises: 001
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("render_jobs", sa.Column("voiceover_audio_path", sa.String(1000), nullable=True))
    op.add_column("render_jobs", sa.Column("voiceover_id", sa.String(50), nullable=True))
    op.add_column("render_jobs", sa.Column("published_url", sa.String(2000), nullable=True))
    op.add_column("render_jobs", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("render_jobs", "published_at")
    op.drop_column("render_jobs", "published_url")
    op.drop_column("render_jobs", "voiceover_id")
    op.drop_column("render_jobs", "voiceover_audio_path")
