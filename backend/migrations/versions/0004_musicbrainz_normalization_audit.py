"""Add append-only audit for MusicBrainz normalization.
Revision ID: 0004_musicbrainz_normalization_audit
Revises: 0003_musicbrainz_review_workflow
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_musicbrainz_normalization_audit"
down_revision = "0003_musicbrainz_review_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "musicbrainz_normalization_audit",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "raw_record_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entity_kind", sa.Text(), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.Text()),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "entity_kind IN ('artists', 'release_groups', 'releases')",
            name="ck_mb_normalization_entity_kind",
        ),
        sa.UniqueConstraint("raw_record_id", name="uq_mb_normalization_raw_record"),
    )
    op.create_index(
        "ix_mb_normalization_created",
        "musicbrainz_normalization_audit",
        ["created_at"],
    )
    op.create_index(
        "ix_mb_normalization_entity",
        "musicbrainz_normalization_audit",
        ["entity_kind", "target_entity_id"],
    )


def downgrade():
    op.drop_index("ix_mb_normalization_entity", table_name="musicbrainz_normalization_audit")
    op.drop_index("ix_mb_normalization_created", table_name="musicbrainz_normalization_audit")
    op.drop_table("musicbrainz_normalization_audit")
