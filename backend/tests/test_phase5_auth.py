import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.api.v1 import auth
from app.api.v1.common import get_db
from app.models import Base
from app.telemetry import SeedTelemetryProvider
from scripts import seed


@pytest.fixture
def auth_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase5.db'}")
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
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("email", "allowed_filter"),
    [
        ("avery.quinn@example.test", "member_id=12"),
        ("mina.park@example.test", "department_id=1"),
        ("theo.grant@example.test", "team_id=1"),
        ("nora.vale@example.test", "member_id=4"),
    ],
)
def test_role_scope_matrix_allows_own_scope_and_denies_other_members(
    auth_client: TestClient, email: str, allowed_filter: str
) -> None:
    login = auth_client.post("/api/v1/auth/dev-login", json={"identifier": email})
    assert login.status_code == 200, login.text

    usage = auth_client.get(f"/api/v1/usage/recent?{allowed_filter}")
    assert usage.status_code == 200, usage.text

    budget = auth_client.get(f"/api/v1/budgets/status?{allowed_filter}")
    assert budget.status_code == 200, budget.text

    outside_usage = auth_client.get("/api/v1/usage/recent?member_id=99999")
    assert outside_usage.status_code == 403
    outside_budget = auth_client.get("/api/v1/budgets/status?member_id=99999")
    assert outside_budget.status_code == 403


def test_auth_identity_and_logout(auth_client: TestClient) -> None:
    login = auth_client.post(
        "/api/v1/auth/dev-login", json={"identifier": "mina.park@example.test"}
    )
    assert login.status_code == 200

    identity = auth_client.get("/api/v1/auth/me")
    assert identity.status_code == 200
    assert identity.json()["role"] == "department_manager"
    assert identity.json()["scope"] == {
        "organization_id": 1,
        "department_id": 1,
        "team_id": 1,
        "member_id": 2,
    }

    assert auth_client.post("/api/v1/auth/logout").status_code == 204
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_department_manager_hierarchy_lists_are_scoped(
    auth_client: TestClient,
) -> None:
    login = auth_client.post(
        "/api/v1/auth/dev-login", json={"identifier": "mina.park@example.test"}
    )
    assert login.status_code == 200, login.text

    departments = auth_client.get("/api/v1/organizations/1/departments")
    assert departments.status_code == 200, departments.text
    assert departments.json()["total"] == 1
    assert [row["id"] for row in departments.json()["items"]] == [1]

    teams = auth_client.get("/api/v1/departments/1/teams")
    assert teams.status_code == 200, teams.text
    assert teams.json()["total"] == 2
    assert {row["id"] for row in teams.json()["items"]} == {1, 2}

    members = auth_client.get("/api/v1/teams/1/members")
    assert members.status_code == 200, members.text
    assert members.json()["total"] == 3
    assert {row["id"] for row in members.json()["items"]} == {1, 2, 3}

    outside_departments = auth_client.get("/api/v1/organizations/1/departments?page=2")
    assert outside_departments.status_code == 200, outside_departments.text
    assert outside_departments.json()["items"] == []


def test_session_survives_auth_module_restart_with_same_secret(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_SECRET", "stable-test-session-secret")
    importlib.reload(auth)

    login = auth_client.post(
        "/api/v1/auth/dev-login", json={"identifier": "avery.quinn@example.test"}
    )
    assert login.status_code == 200

    importlib.reload(auth)
    identity = auth_client.get("/api/v1/auth/me")
    assert identity.status_code == 200
    assert identity.json()["member_id"] == 1


@pytest.mark.parametrize("auth_mode", [None, "production", "", "Development"])
def test_dev_login_is_hidden_outside_exact_development_mode(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch, auth_mode: str | None
) -> None:
    if auth_mode is None:
        monkeypatch.delenv("AUTH_MODE", raising=False)
    else:
        monkeypatch.setenv("AUTH_MODE", auth_mode)

    response = auth_client.post(
        "/api/v1/auth/dev-login", json={"identifier": "avery.quinn@example.test"}
    )
    assert response.status_code == 404
