"""Add artist aliases.
Revision ID: 0002_artist_aliases
Revises: 0001_existing_schema
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_artist_aliases"
down_revision = "0001_existing_schema"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "artist_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("artist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("sort_name", sa.Text()),
        sa.Column("locale", sa.String(32)),
        sa.Column("alias_type", sa.String(64)),
        sa.Column("primary_for_locale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(alias)) > 0", name="ck_artist_alias_not_empty"),
    )
    op.create_index("ix_artist_aliases_artist", "artist_aliases", ["artist_id"])
    op.execute("""
        CREATE UNIQUE INDEX uq_artist_alias_identity
        ON artist_aliases (artist_id, lower(alias), COALESCE(locale, ''))
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_artist_alias_identity")
    op.drop_index("ix_artist_aliases_artist", table_name="artist_aliases")
    op.drop_table("artist_aliases")
