"""Add subscription display and rotation metadata.

Revision ID: 0002_phase3_subscription_metadata
Revises: 0001_phase1_schema
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_phase3_subscription_metadata"
down_revision = "0001_phase1_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("member_subscriptions")
    }
    if "subscription_display_name" not in existing_columns:
        op.add_column(
            "member_subscriptions",
            sa.Column("subscription_display_name", sa.String(length=200), nullable=True),
        )
    if "last_rotated_at" not in existing_columns:
        op.add_column(
            "member_subscriptions",
            sa.Column("last_rotated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("member_subscriptions")
    }
    if "last_rotated_at" in existing_columns:
        op.drop_column("member_subscriptions", "last_rotated_at")
    if "subscription_display_name" in existing_columns:
        op.drop_column("member_subscriptions", "subscription_display_name")