from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import BudgetPolicy, UsageEvent
from app.telemetry.contracts import (
    BudgetStatus,
    ErrorAggregate,
    Summary,
    TelemetryFilters,
    UnmappedSubscription,
    UsageAggregate,
    UsagePoint,
    UsageRecord,
)


def _sum_nullable(values: list[int | Decimal | None]) -> int | Decimal | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _deduplicate_events(events: list[UsageEvent]) -> list[UsageEvent]:
    unique: dict[str, UsageEvent] = {}
    for event in events:
        if event.request_id not in unique:
            unique[event.request_id] = event
    return list(unique.values())


class SeedTelemetryProvider:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self.session_factory = session_factory

    def _events(self, filters: TelemetryFilters | None = None) -> list[UsageEvent]:
        filters = filters or TelemetryFilters()
        with self.session_factory() as session:
            query = select(UsageEvent).where(UsageEvent.member_id.is_not(None))
            if filters.date_from:
                query = query.where(UsageEvent.timestamp >= filters.date_from)
            if filters.date_to:
                date_to = filters.date_to
                if date_to.time() == datetime.min.time():
                    date_to = date_to + timedelta(days=1)
                query = query.where(UsageEvent.timestamp < date_to)
            for column, value in (
                (UsageEvent.organization_id, filters.organization_id),
                (UsageEvent.department_id, filters.department_id),
                (UsageEvent.team_id, filters.team_id),
                (UsageEvent.member_id, filters.member_id),
                (UsageEvent.model_alias, filters.model),
                (UsageEvent.outcome, filters.status),
            ):
                if value is not None:
                    query = query.where(column == value)
            events = list(session.scalars(query.order_by(UsageEvent.timestamp, UsageEvent.id)))

        return _deduplicate_events(events)

    @staticmethod
    def _record(event: UsageEvent) -> UsageRecord:
        return UsageRecord(
            request_id=event.request_id,
            apim_subscription_id=event.apim_subscription_id,
            timestamp=event.timestamp,
            organization_id=event.organization_id,
            department_id=event.department_id,
            team_id=event.team_id,
            member_id=event.member_id,
            model=event.model_alias,
            status=event.outcome,
            input_tokens=event.input_tokens,
            output_tokens=event.output_tokens,
            total_tokens=event.total_tokens,
            estimated_cost=event.estimated_cost,
            latency_ms=event.latency_ms,
            error_code=event.error_code,
        )

    def get_summary(self, filters: TelemetryFilters | None = None) -> Summary:
        events = self._events(filters)
        return Summary(
            request_count=len(events),
            total_tokens=_sum_nullable([event.total_tokens for event in events]),
            estimated_cost=_sum_nullable([event.estimated_cost for event in events]),
            error_count=sum(event.outcome != "success" for event in events),
        )

    def get_usage_timeseries(self, filters: TelemetryFilters | None = None) -> list[UsagePoint]:
        filters = filters or TelemetryFilters()
        buckets: dict[datetime, list[UsageEvent]] = defaultdict(list)
        for event in self._events(filters):
            if filters.interval == "hour":
                period = event.timestamp.replace(minute=0, second=0, microsecond=0)
            elif filters.interval == "week":
                period = (event.timestamp - timedelta(days=event.timestamp.weekday())).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            else:
                period = event.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            buckets[period].append(event)
        return [
            UsagePoint(
                period=period,
                request_count=len(events),
                total_tokens=_sum_nullable([event.total_tokens for event in events]),
                estimated_cost=_sum_nullable([event.estimated_cost for event in events]),
            )
            for period, events in sorted(buckets.items())
        ]

    def _aggregate(self, filters: TelemetryFilters | None, attribute: str) -> list[UsageAggregate]:
        groups: dict[int | str, list[UsageEvent]] = defaultdict(list)
        for event in self._events(filters):
            groups[getattr(event, attribute)].append(event)
        return [
            UsageAggregate(
                key=key,
                request_count=len(events),
                total_tokens=_sum_nullable([event.total_tokens for event in events]),
                estimated_cost=_sum_nullable([event.estimated_cost for event in events]),
            )
            for key, events in sorted(groups.items(), key=lambda item: str(item[0]))
        ]

    def get_usage_by_department(
        self, filters: TelemetryFilters | None = None
    ) -> list[UsageAggregate]:
        return self._aggregate(filters, "department_id")

    def get_usage_by_team(self, filters: TelemetryFilters | None = None) -> list[UsageAggregate]:
        return self._aggregate(filters, "team_id")

    def get_usage_by_member(self, filters: TelemetryFilters | None = None) -> list[UsageAggregate]:
        return self._aggregate(filters, "member_id")

    def get_usage_by_model(self, filters: TelemetryFilters | None = None) -> list[UsageAggregate]:
        return self._aggregate(filters, "model_alias")

    def get_recent_requests(
        self, filters: TelemetryFilters | None = None, limit: int = 20
    ) -> list[UsageRecord]:
        events = sorted(
            self._events(filters), key=lambda event: (event.timestamp, event.id), reverse=True
        )
        return [self._record(event) for event in events[:limit]]

    def get_budget_status(self, filters: TelemetryFilters | None = None) -> list[BudgetStatus]:
        events = self._events(filters)
        with self.session_factory() as session:
            policies = list(session.scalars(select(BudgetPolicy).order_by(BudgetPolicy.id)))
        result = []
        for policy in policies:
            spent = sum(
                (event.estimated_cost or Decimal("0"))
                for event in events
                if (
                    policy.scope_type == "organization" and event.organization_id == policy.scope_id
                )
                or (policy.scope_type == "department" and event.department_id == policy.scope_id)
                or (policy.scope_type == "team" and event.team_id == policy.scope_id)
                or (policy.scope_type == "member" and event.member_id == policy.scope_id)
            )
            result.append(BudgetStatus(
                scope_type=policy.scope_type,
                scope_id=policy.scope_id,
                budget_amount=policy.budget_amount,
                spent_amount=spent,
                remaining_amount=policy.budget_amount - spent,
                utilization=spent / policy.budget_amount if policy.budget_amount else Decimal("0"),
                currency=policy.currency,
            ))
        return result

    def get_error_summary(self, filters: TelemetryFilters | None = None) -> list[ErrorAggregate]:
        errors: dict[str, int] = defaultdict(int)
        for event in self._events(filters):
            if event.outcome != "success":
                errors[event.error_code or event.outcome] += 1
        return [
            ErrorAggregate(error_code=code, request_count=count)
            for code, count in sorted(errors.items())
        ]

    def get_unmapped_subscriptions(
        self, filters: TelemetryFilters | None = None
    ) -> list[UnmappedSubscription]:
        filters = filters or TelemetryFilters()
        with self.session_factory() as session:
            query = select(UsageEvent).where(UsageEvent.member_id.is_(None))
            if filters.date_from:
                query = query.where(UsageEvent.timestamp >= filters.date_from)
            if filters.date_to:
                date_to = filters.date_to
                if date_to.time() == datetime.min.time():
                    date_to = date_to + timedelta(days=1)
                query = query.where(UsageEvent.timestamp < date_to)
            events = list(session.scalars(query.order_by(UsageEvent.timestamp, UsageEvent.id)))
        unique = _deduplicate_events(events)
        grouped: dict[str, list[UsageEvent]] = defaultdict(list)
        for event in unique:
            grouped[event.apim_subscription_id].append(event)
        return [UnmappedSubscription(
            apim_subscription_id=subscription_id,
            request_count=len(events),
            first_seen=min(event.timestamp for event in events),
            last_seen=max(event.timestamp for event in events),
            total_tokens=_sum_nullable([event.total_tokens for event in events]),
            estimated_cost=_sum_nullable([event.estimated_cost for event in events]),
        ) for subscription_id, events in sorted(grouped.items())]
