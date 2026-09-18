from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.api.v1.common import get_db
from app.models import (
    Alert,
    AuditEvent,
    Base,
    BudgetPolicy,
    MemberSubscription,
    Organization,
    UsageEvent,
)
from app.telemetry import SeedTelemetryProvider
from scripts import seed


def client_for(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase7.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory.begin() as session:
        seed.seed(session)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(main, "telemetry_provider", SeedTelemetryProvider(factory))
    monkeypatch.setenv("AUTH_MODE", "development")
    main.app.dependency_overrides[get_db] = override_get_db
    return engine, factory


def test_alert_computation_covers_seed_threshold_families(tmp_path, monkeypatch) -> None:
    _engine, factory = client_for(tmp_path, monkeypatch)
    from app.alerts import compute_alert_candidates

    with factory.begin() as session:
        session.add(UsageEvent(
            request_id="phase7-missing-token",
            apim_subscription_id="northstar-sub-avery-001",
            organization_id=1,
            department_id=1,
            team_id=1,
            member_id=1,
            timestamp=datetime(2026, 9, 17),
            model_alias="northstar-chat",
            outcome="success",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            estimated_cost=None,
        ))
        session.add(UsageEvent(
            request_id="phase7-unmapped-subscription",
            apim_subscription_id="phase7-unmapped-subscription",
            organization_id=1,
            timestamp=datetime(2026, 9, 17),
            model_alias="northstar-chat",
            outcome="success",
            total_tokens=10,
            estimated_cost=0,
        ))
    with factory() as session:
        candidates = compute_alert_candidates(
            session.query(UsageEvent).all(),
            session.query(BudgetPolicy).all(),
            session.query(MemberSubscription).all(),
            token_quota=100,
        )
    alert_types = {candidate.alert_type for candidate in candidates}
    assert {"token_quota_80", "token_quota_90", "token_quota_100"} <= alert_types
    assert {
        "cost_budget_threshold",
        "repeated_rate_limit_or_quota",
        "repeated_provider_failure",
        "unmapped_subscription",
    } <= alert_types


def test_unmapped_event_without_organization_is_not_attributed(tmp_path, monkeypatch) -> None:
    _engine, factory = client_for(tmp_path, monkeypatch)
    from app.alerts import compute_alert_candidates

    with factory.begin() as session:
        session.add(Organization(name="Second Organization", slug="second-organization"))
        session.add(UsageEvent(
            request_id="phase7-unowned-event",
            apim_subscription_id="phase7-unowned-subscription",
            organization_id=None,
            timestamp=datetime(2026, 9, 17),
            model_alias="northstar-chat",
            outcome="success",
            total_tokens=10,
            estimated_cost=0,
        ))
    with factory() as session:
        candidates = compute_alert_candidates(
            session.query(UsageEvent).all(),
            session.query(BudgetPolicy).all(),
            session.query(MemberSubscription).all(),
        )

    unmapped = [
        candidate for candidate in candidates if candidate.alert_type == "unmapped_subscription"
    ]
    assert all(candidate.organization_id not in {1, 2} for candidate in unmapped)
    assert not unmapped


def test_alerts_are_scoped_by_role(tmp_path, monkeypatch) -> None:
    _engine, factory = client_for(tmp_path, monkeypatch)
    with factory.begin() as session:
        session.add(
            Alert(
                organization_id=1,
                scope_type="department",
                scope_id=2,
                alert_type="test_scope_leak",
                severity="warning",
                message="Research alert",
                triggered_at=datetime(2026, 9, 17),
            )
        )
    with TestClient(main.app) as client:
        login = client.post("/api/v1/auth/dev-login", json={"identifier": "mina.park@example.test"})
        assert login.status_code == 200
        response = client.get("/api/v1/alerts?page_size=100")
        assert response.status_code == 200, response.text
        assert all(
            (item["scope_type"], item["scope_id"]) != ("department", 2)
            for item in response.json()["items"]
        )


def test_alert_lifecycle_requires_open_acknowledged_resolved(tmp_path, monkeypatch) -> None:
    _engine, factory = client_for(tmp_path, monkeypatch)
    with factory.begin() as session:
        session.add(
            Alert(
                organization_id=1,
                scope_type="organization",
                scope_id=1,
                alert_type="test_lifecycle",
                severity="warning",
                message="Lifecycle alert",
                triggered_at=datetime(2026, 9, 17),
            )
        )

    with TestClient(main.app) as client:
        login = client.post(
            "/api/v1/auth/dev-login",
            json={"identifier": "avery.quinn@example.test"},
        )
        assert login.status_code == 200
        acknowledged = client.post("/api/v1/alerts/1/acknowledge")
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "acknowledged"
        resolved = client.post("/api/v1/alerts/1/resolve")
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"
        rejected = client.post("/api/v1/alerts/1/acknowledge")
        assert rejected.status_code == 409
        assert rejected.json() == {
            "error": "invalid_alert_transition",
            "message": "Alert cannot transition from resolved to acknowledged.",
            "field_errors": [],
        }


def test_admin_mutations_write_audit_events(tmp_path, monkeypatch) -> None:
    _engine, factory = client_for(tmp_path, monkeypatch)
    with TestClient(main.app) as client:
        login = client.post(
            "/api/v1/auth/dev-login", json={"identifier": "avery.quinn@example.test"}
        )
        assert login.status_code == 200
        response = client.patch(
            "/api/v1/departments/1", json={"name": "Product Engineering Updated"}
        )
        assert response.status_code == 200
        audit = client.get("/api/v1/audit-events")
        assert audit.status_code == 200
        assert any(
            item["action"] == "update"
            and item["entity_type"] == "department"
            and item["entity_id"] == 1
            for item in audit.json()["items"]
        )
    with factory() as session:
        assert session.query(AuditEvent).count() >= 1
