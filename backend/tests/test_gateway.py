from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from openai import OpenAI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.api import gateway
from app.api.v1.common import get_db
from app.models import Base, BudgetPolicy, UsageEvent
from app.telemetry import SeedTelemetryProvider
from scripts import seed


def client_for(tmp_path: Path, monkeypatch, llm_transport: httpx.BaseTransport):
    engine = create_engine(f"sqlite:///{tmp_path / 'gateway.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory.begin() as session:
        seed.seed(session)
        policy = session.query(BudgetPolicy).filter_by(scope_type="member", scope_id=1).one()
        policy.budget_amount = 601

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(main, "telemetry_provider", SeedTelemetryProvider(factory))
    monkeypatch.setattr(
        gateway,
        "OpenAI",
        lambda **kwargs: OpenAI(
            api_key="test-key",
            base_url="http://test/v1",
            http_client=httpx.Client(transport=llm_transport),
        ),
    )
    monkeypatch.setenv("GATEWAY_LLM_MODEL", "mock-model")
    main.app.dependency_overrides[get_db] = override_get_db
    return factory


def test_gateway_success_writes_attributed_event(tmp_path, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1780000000,
                "model": "mock-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
            },
        )

    factory = client_for(tmp_path, monkeypatch, httpx.MockTransport(handler))
    with TestClient(main.app) as client:
        response = client.post(
            "/gateway/v1/chat/completions",
            headers={"Ocp-Apim-Subscription-Key": "northstar-sub-avery-001"},
            json={"model": "local-live", "messages": [{"role": "user", "content": "Hello"}]},
        )
    assert response.status_code == 200
    assert response.json()["usage"]["total_tokens"] == 19
    with factory() as session:
        event = (
            session.query(UsageEvent)
            .filter(UsageEvent.request_id != "seed-001")
            .order_by(UsageEvent.id.desc())
            .first()
        )
        assert event is not None
        assert event.organization_id == 1
        assert event.department_id == 1
        assert event.team_id == 1
        assert event.member_id == 1
        assert event.input_tokens == 12
        assert event.output_tokens == 7
        assert event.total_tokens == 19
        assert event.telemetry_source == "local_gateway"
        assert event.outcome == "success"


def test_gateway_invalid_key_returns_401(tmp_path, monkeypatch) -> None:
    factory = client_for(tmp_path, monkeypatch, httpx.MockTransport(lambda _: httpx.Response(500)))
    with TestClient(main.app) as client:
        response = client.post(
            "/gateway/v1/chat/completions",
            headers={"Ocp-Apim-Subscription-Key": "unknown"},
            json={"model": "local-live", "messages": [{"role": "user", "content": "Hello"}]},
        )
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_subscription_key"
    with factory() as session:
        assert session.query(UsageEvent).count() == 32


def test_gateway_blocks_member_at_token_quota_before_llm_call(tmp_path, monkeypatch) -> None:
    factory = client_for(tmp_path, monkeypatch, httpx.MockTransport(lambda _: httpx.Response(500)))
    with factory.begin() as session:
        policy = session.query(BudgetPolicy).filter_by(scope_type="member", scope_id=1).one()
        policy.budget_amount = 600

    def fail_if_called(**kwargs):
        raise AssertionError("LLM client must not be constructed for an over-quota request")

    monkeypatch.setattr(gateway, "OpenAI", fail_if_called)
    with TestClient(main.app) as client:
        response = client.post(
            "/gateway/v1/chat/completions",
            headers={"Ocp-Apim-Subscription-Key": "northstar-sub-avery-001"},
            json={"model": "local-live", "messages": [{"role": "user", "content": "Hello"}]},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "budget_exceeded"
    assert "token budget" in response.json()["message"]
    with factory() as session:
        event = session.query(UsageEvent).order_by(UsageEvent.id.desc()).first()
        assert event is not None
        assert event.outcome == "quota_blocked"
        assert event.error_code == "QUOTA_EXCEEDED"


def test_gateway_provider_failure_is_logged(tmp_path, monkeypatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"message": "unavailable", "type": "server_error"}},
        )

    factory = client_for(tmp_path, monkeypatch, httpx.MockTransport(handler))
    with TestClient(main.app) as client:
        response = client.post(
            "/gateway/v1/chat/completions",
            headers={"Ocp-Apim-Subscription-Key": "northstar-sub-avery-001"},
            json={"model": "local-live", "messages": [{"role": "user", "content": "Hello"}]},
        )
    assert response.status_code == 502
    with factory() as session:
        event = session.query(UsageEvent).order_by(UsageEvent.id.desc()).first()
        assert event is not None
        assert event.outcome == "provider_error"
        assert event.member_id == 1
        assert event.telemetry_source == "local_gateway"