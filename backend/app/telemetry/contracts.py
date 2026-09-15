from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class TelemetryFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    organization_id: int | None = None
    department_id: int | None = None
    team_id: int | None = None
    member_id: int | None = None
    model: str | None = None
    status: str | None = None
    interval: str = "day"


@dataclass(frozen=True)
class UsageRecord:
    request_id: str
    apim_subscription_id: str
    timestamp: datetime
    organization_id: int
    department_id: int
    team_id: int
    member_id: int
    model: str
    status: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost: Decimal | None
    latency_ms: int | None
    error_code: str | None


@dataclass(frozen=True)
class Summary:
    request_count: int
    total_tokens: int | None
    estimated_cost: Decimal | None
    error_count: int


@dataclass(frozen=True)
class UsagePoint:
    period: datetime
    request_count: int
    total_tokens: int | None
    estimated_cost: Decimal | None


@dataclass(frozen=True)
class UsageAggregate:
    key: int | str
    request_count: int
    total_tokens: int | None
    estimated_cost: Decimal | None


@dataclass(frozen=True)
class BudgetStatus:
    scope_type: str
    scope_id: int
    budget_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    utilization: Decimal
    currency: str


@dataclass(frozen=True)
class ErrorAggregate:
    error_code: str
    request_count: int


@dataclass(frozen=True)
class UnmappedSubscription:
    apim_subscription_id: str
    request_count: int
    first_seen: datetime
    last_seen: datetime
    total_tokens: int | None
    estimated_cost: Decimal | None


class TelemetryProvider(Protocol):
    def get_summary(self, filters: TelemetryFilters | None = None) -> Summary: ...

    def get_usage_timeseries(self, filters: TelemetryFilters | None = None) -> list[UsagePoint]: ...

    def get_usage_by_department(
        self, filters: TelemetryFilters | None = None
    ) -> list[UsageAggregate]: ...

    def get_usage_by_team(
        self, filters: TelemetryFilters | None = None
    ) -> list[UsageAggregate]: ...

    def get_usage_by_member(
        self, filters: TelemetryFilters | None = None
    ) -> list[UsageAggregate]: ...

    def get_usage_by_model(
        self, filters: TelemetryFilters | None = None
    ) -> list[UsageAggregate]: ...

    def get_recent_requests(
        self, filters: TelemetryFilters | None = None, limit: int = 20
    ) -> list[UsageRecord]: ...

    def get_budget_status(self, filters: TelemetryFilters | None = None) -> list[BudgetStatus]: ...

    def get_error_summary(
        self, filters: TelemetryFilters | None = None
    ) -> list[ErrorAggregate]: ...
