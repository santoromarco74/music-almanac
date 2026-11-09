"""Baseline for the pre-existing PostgreSQL schema.

The schema is provisioned by database/init/001_schema.sql. This revision is
intentionally empty: it marks the existing schema without recreating tables.
"""
revision = "0001_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
