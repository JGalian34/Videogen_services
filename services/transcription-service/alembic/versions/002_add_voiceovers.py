"""Add voiceovers table for TTS / ElevenLabs

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
    op.create_table(
        "voiceovers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("poi_id", sa.Uuid(), nullable=False),
        sa.Column("script_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("language", sa.String(10), nullable=False, server_default="fr"),
        sa.Column("voice_id", sa.String(100), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="stub"),
        sa.Column("full_audio_path", sa.String(1000), nullable=True),
        sa.Column("full_narration_text", sa.Text(), nullable=True),
        sa.Column("total_duration_seconds", sa.Float(), nullable=True),
        sa.Column("scene_audios", sa.JSON(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voiceovers_poi_id", "voiceovers", ["poi_id"])
    op.create_index("ix_voiceovers_script_id", "voiceovers", ["script_id"])


def downgrade() -> None:
    op.drop_index("ix_voiceovers_script_id")
    op.drop_index("ix_voiceovers_poi_id")
    op.drop_table("voiceovers")
