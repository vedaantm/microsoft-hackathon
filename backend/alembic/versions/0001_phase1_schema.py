"""Phase 1 database schema.

Revision ID: 0001_phase1_schema
Revises:
"""

from alembic import op

revision = "0001_phase1_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.models import Base

    Base.metadata.drop_all(bind=op.get_bind())
