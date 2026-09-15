from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.api.v1.common import get_db
from app.models import Base, BudgetPolicy
from app.telemetry import SeedTelemetryProvider
from scripts import seed


@pytest.fixture
def phase4_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase4.db'}")
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
    main.app.dependency_overrides[get_db] = override_get_db
    with TestClient(main.app) as client:
        yield client, factory
    main.app.dependency_overrides.clear()


def test_all_usage_endpoints_are_paginated_except_summary(phase4_client) -> None:
    client, _factory = phase4_client
    base = "/api/v1/usage"
    assert client.get(f"{base}/summary").status_code == 200
    for path in (
        "timeseries",
        "by-department",
        "by-team",
        "by-member",
        "by-model",
        "recent",
        "errors",
        "unmapped",
    ):
        response = client.get(f"{base}/{path}?page=1&page_size=2")
        assert response.status_code == 200, response.text
        body = response.json()
        assert {"items", "total", "page", "page_size"} <= set(body)
        assert len(body["items"]) <= 2


def test_usage_filters_reach_seed_provider(phase4_client) -> None:
    client, _factory = phase4_client
    response = client.get(
        "/api/v1/usage/recent?date_from=2026-02-01T00:00:00&date_to=2026-02-02T00:00:00"
        "&model=northstar-chat&status=success"
    )
    assert response.status_code == 200
    assert [item["request_id"] for item in response.json()["items"]] == ["seed-001"]


def test_budget_crud_and_four_level_inheritance(phase4_client) -> None:
    client, factory = phase4_client
    organization_id = 1
    scopes = [("organization", 1), ("department", 1), ("team", 1), ("member", 1)]
    response = client.post(
        "/api/v1/budgets",
        json={
            "organization_id": organization_id,
            "scope_type": "member",
            "scope_id": 12,
            "budget_amount": 99,
            "effective_from": "2027-01-01T00:00:00",
        },
    )
    assert response.status_code == 201, response.text

    listed = client.get("/api/v1/budgets?page_size=100").json()
    assert listed["total"] == 9
    created_id = listed["items"][-1]["id"]
    patched = client.patch(f"/api/v1/budgets/{created_id}", json={"budget_amount": 99})
    assert patched.status_code == 200
    assert patched.json()["budget_amount"] == "99.00"

    status = client.get("/api/v1/budgets/status?as_of=2027-02-01T00:00:00&page_size=100")
    assert status.status_code == 200
    resolved = {(item["scope_type"], item["scope_id"]) for item in status.json()["items"]}
    assert all(scope in resolved for scope in scopes)
    assert factory().query(BudgetPolicy).count() == 9


def test_overlapping_active_budget_returns_standard_409(phase4_client) -> None:
    client, _factory = phase4_client
    response = client.post(
        "/api/v1/budgets",
        json={
            "organization_id": 1,
            "scope_type": "organization",
            "scope_id": 1,
            "budget_amount": 999,
            "effective_from": "2026-02-01T00:00:00",
            "effective_to": "2026-03-01T00:00:00",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"] == "budget_conflict"
    assert response.json()["field_errors"] == []


def test_cost_estimate_uses_seed_model_price(phase4_client) -> None:
    client, _factory = phase4_client
    response = client.get("/api/v1/usage/recent?page_size=100&model=northstar-chat")
    assert response.status_code == 200
    first = next(item for item in response.json()["items"] if item["request_id"] == "seed-001")
    assert Decimal(first["estimated_cost"]) == Decimal("0.000800")


def test_budget_status_reports_provider_usage(phase4_client) -> None:
    client, _factory = phase4_client
    response = client.get("/api/v1/budgets/status?as_of=2026-02-15T00:00:00&page_size=100")
    assert response.status_code == 200
    organization = next(
        item for item in response.json()["items"] if item["scope_type"] == "organization"
    )
    assert Decimal(organization["estimated_spent_amount"]) > 0
