from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    scope_type: str
    scope_id: int
    alert_type: str
    severity: str
    message: str
    status: str
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    actor_member_id: int | None
    action: str
    entity_type: str
    entity_id: int | None
    occurred_at: datetime
    details: dict[str, Any] | None
