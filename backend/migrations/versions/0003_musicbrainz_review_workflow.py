"""Add append-only MusicBrainz review decisions.
Revision ID: 0003_musicbrainz_review_workflow
Revises: 0002_artist_aliases
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_musicbrainz_review_workflow"
down_revision = "0002_artist_aliases"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "musicbrainz_review_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("raw_record_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("raw_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_kind", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("reviewer", sa.String(length=120), nullable=False,
                  server_default=sa.text("'manual'")),
        sa.Column("target_artist_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("artists.id", ondelete="RESTRICT")),
        sa.Column("target_release_group_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("release_groups.id", ondelete="RESTRICT")),
        sa.Column("target_release_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("releases.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "action IN ('APPROVED', 'REJECTED', 'LINKED')",
            name="ck_mb_review_action",
        ),
        sa.CheckConstraint(
            "entity_kind IN ('artists', 'release_groups', 'releases')",
            name="ck_mb_review_entity_kind",
        ),
        sa.CheckConstraint(
            "action <> 'REJECTED' OR length(trim(coalesce(reason, ''))) > 0",
            name="ck_mb_review_rejection_reason",
        ),
        sa.CheckConstraint(
            "(action = 'LINKED' AND num_nonnulls(target_artist_id, target_release_group_id, target_release_id) = 1) "
            "OR (action <> 'LINKED' AND num_nonnulls(target_artist_id, target_release_group_id, target_release_id) = 0)",
            name="ck_mb_review_link_target_count",
        ),
        sa.CheckConstraint(
            "target_artist_id IS NULL OR entity_kind = 'artists'",
            name="ck_mb_review_artist_target_kind",
        ),
        sa.CheckConstraint(
            "target_release_group_id IS NULL OR entity_kind = 'release_groups'",
            name="ck_mb_review_group_target_kind",
        ),
        sa.CheckConstraint(
            "target_release_id IS NULL OR entity_kind = 'releases'",
            name="ck_mb_review_release_target_kind",
        ),
    )
    op.create_index(
        "ix_mb_review_decisions_record_created",
        "musicbrainz_review_decisions",
        ["raw_record_id", "created_at"],
    )
    op.create_index(
        "ix_mb_review_decisions_action_created",
        "musicbrainz_review_decisions",
        ["action", "created_at"],
    )


def downgrade():
    op.drop_index("ix_mb_review_decisions_action_created", table_name="musicbrainz_review_decisions")
    op.drop_index("ix_mb_review_decisions_record_created", table_name="musicbrainz_review_decisions")
    op.drop_table("musicbrainz_review_decisions")
