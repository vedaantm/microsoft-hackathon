from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Member, UsageEvent
from app.telemetry import (
    AzureMonitorTelemetryProvider,
    SeedTelemetryProvider,
    TelemetryFilters,
    create_telemetry_provider,
)
from app.telemetry.seed import _deduplicate_events
from scripts import seed


@pytest.fixture
def provider(tmp_path: Path) -> SeedTelemetryProvider:
    engine = create_engine(f"sqlite:///{tmp_path / 'telemetry.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory.begin() as session:
        seed.seed(session)
    return SeedTelemetryProvider(factory)


def test_seed_provider_implements_all_queries(provider: SeedTelemetryProvider) -> None:
    filters = TelemetryFilters(date_from=datetime(2026, 2, 1), date_to=datetime(2026, 3, 4))

    summary = provider.get_summary(filters)
    assert summary.request_count == 31
    assert summary.total_tokens == 6430
    assert summary.error_count == 9
    assert len(provider.get_usage_timeseries(filters)) == 31
    assert provider.get_usage_by_department(filters)
    assert provider.get_usage_by_team(filters)
    assert provider.get_usage_by_member(filters)
    assert {item.key for item in provider.get_usage_by_model(filters)} == {
        "northstar-chat",
        "northstar-fast",
        "northstar-reason",
    }
    assert len(provider.get_recent_requests(filters, limit=3)) == 3
    assert len(provider.get_budget_status(filters)) == 8
    assert provider.get_error_summary(filters)


def test_unknown_subscription_is_only_in_reconciliation(provider: SeedTelemetryProvider) -> None:
    assert all(item.apim_subscription_id != "unknown-apim-subscription-999"
               for item in provider.get_recent_requests())
    unmapped = provider.get_unmapped_subscriptions()
    assert [item.apim_subscription_id for item in unmapped] == ["unknown-apim-subscription-999"]
    assert unmapped[0].request_count == 1


def test_duplicate_request_ids_are_deduplicated() -> None:
    first = UsageEvent(request_id="duplicate", timestamp=datetime(2026, 1, 1))
    second = UsageEvent(request_id="duplicate", timestamp=datetime(2026, 1, 2))
    assert _deduplicate_events([first, second]) == [first]


def test_missing_token_counts_remain_null(provider: SeedTelemetryProvider, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'nullable.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory.begin() as session:
        seed.seed(session)
        member = session.query(Member).first()
        session.add(UsageEvent(
            request_id="missing-tokens",
            apim_subscription_id=member.subscriptions[0].apim_subscription_id,
            organization_id=member.organization_id,
            department_id=member.department_id,
            team_id=member.team_id,
            member_id=member.id,
            timestamp=datetime(2026, 3, 5),
            model_alias="northstar-chat",
            outcome="success",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            estimated_cost=Decimal("0.10"),
        ))
    records = SeedTelemetryProvider(factory).get_recent_requests(limit=1)
    assert records[0].request_id == "missing-tokens"
    assert records[0].total_tokens is None


@pytest.mark.parametrize("method", [
    "get_summary",
    "get_usage_timeseries",
    "get_usage_by_department",
    "get_usage_by_team",
    "get_usage_by_member",
    "get_usage_by_model",
    "get_recent_requests",
    "get_budget_status",
    "get_error_summary",
])
def test_azure_provider_methods_are_explicitly_unimplemented(method: str) -> None:
    with pytest.raises(NotImplementedError, match="Phase 8"):
        getattr(AzureMonitorTelemetryProvider(), method)()


def test_provider_selection_defaults_and_supports_application_insights() -> None:
    assert isinstance(create_telemetry_provider("seed"), SeedTelemetryProvider)
    assert isinstance(
        create_telemetry_provider("application_insights"), AzureMonitorTelemetryProvider
    )
    with pytest.raises(ValueError, match="Unsupported TELEMETRY_SOURCE"):
        create_telemetry_provider("unknown")
