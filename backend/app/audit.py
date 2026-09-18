from typing import Any

from sqlalchemy.orm import Session

from app.api.v1.auth import Identity
from app.api.v1.common import commit
from app.models import AuditEvent


def record_audit(
    db: Session,
    identity: Identity,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=identity.organization_id,
            actor_member_id=identity.member_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
    )
    commit(db)
