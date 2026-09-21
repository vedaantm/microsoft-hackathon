"""Add local gateway telemetry source and model configuration.

Revision ID: 0003_local_gateway
Revises: 0002_phase3_subscription_metadata
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_local_gateway"
down_revision = "0002_subscription_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("usage_events")
    }
    if "telemetry_source" not in existing_columns:
        op.add_column(
            "usage_events",
            sa.Column(
    "telemetry_source", sa.String(length=30), nullable=False, server_default="seeded"
),
        )

    op.execute(sa.text("""
        INSERT INTO model_configurations (
            organization_id, alias, provider_model, input_cost_per_1k_tokens,
            output_cost_per_1k_tokens, effective_from, status, created_at, updated_at
        )
        SELECT id, 'local-live', 'local-live', 0, 0, '2026-01-01 00:00:00', 'active',
               '2026-01-01 00:00:00', '2026-01-01 00:00:00'
        FROM organizations
        WHERE NOT EXISTS (
            SELECT 1 FROM model_configurations existing
            WHERE existing.organization_id = organizations.id
              AND existing.alias = 'local-live'
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM model_configurations WHERE alias = 'local-live'"))
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("usage_events")
    }
    if "telemetry_source" in existing_columns:
        op.drop_column("usage_events", "telemetry_source")