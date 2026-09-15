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
    if bind.dialect.name == "sqlite":
        op.execute("""
        CREATE TRIGGER budget_policy_no_overlap
        BEFORE INSERT ON budget_policies
        WHEN NEW.status = 'active' AND EXISTS (
            SELECT 1 FROM budget_policies existing
            WHERE existing.status = 'active'
              AND existing.scope_type = NEW.scope_type
              AND existing.scope_id = NEW.scope_id
              AND existing.effective_from < COALESCE(NEW.effective_to, '9999-12-31 23:59:59')
              AND NEW.effective_from < COALESCE(existing.effective_to, '9999-12-31 23:59:59')
        )
        BEGIN
            SELECT RAISE(ABORT, 'active budget policies overlap');
        END;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS budget_policy_no_overlap")
    from app.models import Base

    Base.metadata.drop_all(bind=bind)
