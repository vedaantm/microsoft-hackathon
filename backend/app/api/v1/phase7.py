from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.alerts import refresh_alerts
from app.api.v1.auth import Identity, ensure_scope, require_role
from app.api.v1.common import get_db, page_params
from app.models import Alert, AuditEvent
from app.schemas import AlertRead, AuditEventRead, PageParams, PaginatedResponse

alerts_router = APIRouter()
audit_router = APIRouter()


def _ensure_alert_scope(identity: Identity, db: Session, alert: Alert) -> None:
    if alert.scope_type == "organization":
        ensure_scope(identity, db, organization_id=alert.scope_id)
    elif alert.scope_type == "department":
        ensure_scope(identity, db, department_id=alert.scope_id)
    elif alert.scope_type == "team":
        ensure_scope(identity, db, team_id=alert.scope_id)
    elif alert.scope_type == "member":
        ensure_scope(identity, db, member_id=alert.scope_id)
    else:
        ensure_scope(identity, db, organization_id=alert.organization_id)


def _page(items: list, params: PageParams) -> dict:
    start = (params.page - 1) * params.page_size
    return {
        "items": items[start : start + params.page_size],
        "total": len(items),
        **params.model_dump(),
    }


@alerts_router.get("/alerts", response_model=PaginatedResponse[AlertRead])
def list_alerts(
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(
        require_role("org_admin", "department_manager", "team_manager", "member")
    ),
) -> dict:
    refresh_alerts(db)
    items = []
    alerts = (
        db.query(Alert)
        .filter(Alert.organization_id == identity.organization_id)
        .order_by(Alert.triggered_at.desc(), Alert.id.desc())
        .all()
    )
    for alert in alerts:
        try:
            _ensure_alert_scope(identity, db, alert)
        except HTTPException:
            continue
        items.append(alert)
    return _page(items, params)


def _change_alert_status(alert_id: int, status: str, db: Session, identity: Identity) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        from app.api.v1.common import get_or_404

        alert = get_or_404(db, Alert, alert_id)
    _ensure_alert_scope(identity, db, alert)
    valid_transition = (alert.status, status) in {
        ("open", "acknowledged"),
        ("acknowledged", "resolved"),
    }
    if not valid_transition:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_alert_transition",
                "message": f"Alert cannot transition from {alert.status} to {status}.",
                "field_errors": [],
            },
        )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if status == "acknowledged":
        alert.status = status
        alert.acknowledged_at = now
    else:
        alert.status = status
        alert.resolved_at = now
    db.commit()
    db.refresh(alert)
    return alert


@alerts_router.post("/alerts/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    identity: Identity = Depends(
        require_role("org_admin", "department_manager", "team_manager", "member")
    ),
) -> Alert:
    return _change_alert_status(alert_id, "acknowledged", db, identity)


@alerts_router.post("/alerts/{alert_id}/resolve", response_model=AlertRead)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    identity: Identity = Depends(
        require_role("org_admin", "department_manager", "team_manager", "member")
    ),
) -> Alert:
    return _change_alert_status(alert_id, "resolved", db, identity)


@audit_router.get("/audit-events", response_model=PaginatedResponse[AuditEventRead])
def list_audit_events(
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role("org_admin")),
) -> dict:
    query = db.query(AuditEvent).filter(AuditEvent.organization_id == identity.organization_id)
    return _page(query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).all(), params)
