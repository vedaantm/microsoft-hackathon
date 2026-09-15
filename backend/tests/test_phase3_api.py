from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.common import get_db
from app.main import app
from app.models import Base, MemberSubscription


@pytest.fixture
def client(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase3.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, factory
    app.dependency_overrides.clear()


def create_hierarchy(client: TestClient) -> tuple[dict, dict, dict, dict]:
    organization = client.post(
        "/api/v1/organizations", json={"name": "Acme", "slug": "acme"}
    ).json()
    department = client.post(
        f"/api/v1/organizations/{organization['id']}/departments",
        json={"name": "Engineering", "slug": "engineering"},
    ).json()
    team = client.post(
        f"/api/v1/departments/{department['id']}/teams",
        json={"name": "Platform", "slug": "platform"},
    ).json()
    member = client.post(
        f"/api/v1/teams/{team['id']}/members",
        json={"name": "Ada", "email": "ada@example.test", "role": "member"},
    ).json()
    return organization, department, team, member


def test_hierarchy_crud_and_soft_delete(client) -> None:
    test_client, _factory = client
    organization, department, team, member = create_hierarchy(test_client)

    assert test_client.get(f"/api/v1/organizations/{organization['id']}").status_code == 200
    assert test_client.patch(
        f"/api/v1/organizations/{organization['id']}", json={"status": "inactive"}
    ).json()["status"] == "inactive"
    assert test_client.patch(
        f"/api/v1/departments/{department['id']}", json={"status": "inactive"}
    ).json()["status"] == "inactive"
    assert test_client.patch(
        f"/api/v1/teams/{team['id']}", json={"status": "inactive"}
    ).json()["status"] == "inactive"
    assert test_client.patch(
        f"/api/v1/members/{member['id']}", json={"status": "inactive"}
    ).json()["status"] == "inactive"
    assert test_client.get(f"/api/v1/members/{member['id']}").json()["status"] == "inactive"


def test_pagination_and_uniqueness_error_shape(client) -> None:
    test_client, _factory = client
    organization, _department, _team, _member = create_hierarchy(test_client)
    duplicate = test_client.post(
        "/api/v1/organizations", json={"name": "Other", "slug": "acme"}
    )
    assert duplicate.status_code == 409
    assert set(duplicate.json()) == {"error", "message", "field_errors"}

    page = test_client.get("/api/v1/organizations?page=1&page_size=1")
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["page"] == 1
    assert page.json()["page_size"] == 1
    assert len(page.json()["items"]) == 1
    assert test_client.get(
        f"/api/v1/organizations/{organization['id']}/departments?page_size=10"
    ).json()["total"] == 1


def test_subscription_mapping_never_exposes_key_like_fields(client) -> None:
    test_client, factory = client
    _organization, _department, _team, member = create_hierarchy(test_client)
    response = test_client.put(
        f"/api/v1/members/{member['id']}/subscription",
        json={
            "apim_subscription_id": "subscription-1",
            "subscription_display_name": "Ada's subscription",
            "status": "active",
            "last_rotated_at": "2026-09-15T12:00:00Z",
        },
    )
    assert response.status_code == 200
    assert set(response.json()) == {
        "apim_subscription_id",
        "subscription_display_name",
        "status",
        "last_rotated_at",
    }
    assert not any("key" in key.lower() or "secret" in key.lower() for key in response.json())
    assert response.json()["subscription_display_name"] == "Ada's subscription"
    assert response.json()["last_rotated_at"] == "2026-09-15T12:00:00"
    fetched = test_client.get(f"/api/v1/members/{member['id']}/subscription")
    assert fetched.status_code == 200
    assert fetched.json()["subscription_display_name"] == "Ada's subscription"
    assert fetched.json()["last_rotated_at"] == "2026-09-15T12:00:00"
    rejected = test_client.put(
        f"/api/v1/members/{member['id']}/subscription",
        json={"apim_subscription_id": "subscription-1", "primary_key": "must-never-appear"},
    )
    assert rejected.status_code == 422
    assert "primary_key" not in rejected.text
    with factory() as session:
        subscription_id = session.query(MemberSubscription).first().id
    patched = test_client.patch(
        f"/api/v1/subscriptions/{subscription_id}",
        json={
            "status": "inactive",
            "subscription_display_name": "Ada's rotated subscription",
            "last_rotated_at": "2026-09-15T13:00:00Z",
        },
    )
    assert patched.status_code == 200
    assert set(patched.json()) == set(response.json())
    assert patched.json()["subscription_display_name"] == "Ada's rotated subscription"
    assert patched.json()["last_rotated_at"] == "2026-09-15T13:00:00"
    fetched = test_client.get(f"/api/v1/members/{member['id']}/subscription")
    assert fetched.json()["subscription_display_name"] == "Ada's rotated subscription"
    assert fetched.json()["last_rotated_at"] == "2026-09-15T13:00:00"
    assert test_client.delete(f"/api/v1/subscriptions/{subscription_id}").status_code == 204