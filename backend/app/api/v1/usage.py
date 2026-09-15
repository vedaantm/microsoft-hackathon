from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.auth import Identity, require_role, scoped_filters
from app.api.v1.common import get_db, page_params
from app.models import ModelConfiguration
from app.schemas import (
    ErrorAggregateRead,
    PageParams,
    PaginatedResponse,
    UnmappedSubscriptionRead,
    UsageAggregateRead,
    UsagePointRead,
    UsageRecordRead,
    UsageSummaryRead,
)
from app.telemetry import TelemetryFilters

router = APIRouter()


def provider():
    from app.main import telemetry_provider

    return telemetry_provider


def filters(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    organization_id: int | None = None,
    department_id: int | None = None,
    team_id: int | None = None,
    member_id: int | None = None,
    model: str | None = None,
    status: str | None = None,
    interval: str = Query("day", pattern="^(hour|day|week)$"),
) -> TelemetryFilters:
    return TelemetryFilters(
        date_from=date_from,
        date_to=date_to,
        organization_id=organization_id,
        department_id=department_id,
        team_id=team_id,
        member_id=member_id,
        model=model,
        status=status,
        interval=interval,
    )


def page(items: list, params: PageParams) -> dict:
    start = (params.page - 1) * params.page_size
    return {
        "items": items[start : start + params.page_size],
        "total": len(items),
        **params.model_dump(),
    }


def _records(filters: TelemetryFilters):
    return provider().get_recent_requests(filters, limit=100000)


def _cost(record, db: Session) -> Decimal | None:
    if record.input_tokens is None or record.output_tokens is None:
        return None
    configurations = db.query(ModelConfiguration).filter(
        ModelConfiguration.organization_id == record.organization_id,
        ModelConfiguration.alias == record.model,
        ModelConfiguration.effective_from <= record.timestamp,
        ModelConfiguration.effective_to.is_(None)
        | (ModelConfiguration.effective_to > record.timestamp),
    ).order_by(ModelConfiguration.effective_from.desc()).all()
    if not configurations:
        return None
    configuration = configurations[0]
    return (
        Decimal(record.input_tokens) * configuration.input_cost_per_1k_tokens
        + Decimal(record.output_tokens) * configuration.output_cost_per_1k_tokens
    ) / Decimal(1000)


def _record_costs(filters: TelemetryFilters, db: Session) -> dict[str, Decimal | None]:
    return {record.request_id: _cost(record, db) for record in _records(filters)}


def _sum_costs(filters: TelemetryFilters, db: Session) -> Decimal | None:
    values = [value for value in _record_costs(filters, db).values() if value is not None]
    return sum(values, Decimal("0")) if values else None


@router.get("/usage/summary", response_model=UsageSummaryRead)
def summary(
    filters: TelemetryFilters = Depends(filters),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    result = provider().get_summary(filters)
    return {**result.__dict__, "estimated_cost": _sum_costs(filters, db)}


@router.get("/usage/timeseries", response_model=PaginatedResponse[UsagePointRead])
def timeseries(
    filters: TelemetryFilters = Depends(filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    items = provider().get_usage_timeseries(filters)
    costs: dict[datetime, Decimal] = defaultdict(lambda: Decimal("0"))
    for record in _records(filters):
        cost = _cost(record, db)
        if cost is not None:
            if filters.interval == "hour":
                period = record.timestamp.replace(minute=0, second=0, microsecond=0)
            elif filters.interval == "week":
                period = (record.timestamp - timedelta(days=record.timestamp.weekday())).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            else:
                period = record.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            costs[period] += cost
    items = [{**item.__dict__, "estimated_cost": costs.get(item.period)} for item in items]
    return page(items, params)


def aggregate_endpoint(
    method: str,
    attribute: str,
    filters: TelemetryFilters,
    params: PageParams,
    db: Session,
):
    items = getattr(provider(), method)(filters)
    costs: dict[int | str, Decimal] = defaultdict(lambda: Decimal("0"))
    for record in _records(filters):
        cost = _cost(record, db)
        if cost is not None:
            costs[getattr(record, attribute)] += cost
    costed_items = [{**item.__dict__, "estimated_cost": costs.get(item.key)} for item in items]
    return page(costed_items, params)


@router.get("/usage/by-department", response_model=PaginatedResponse[UsageAggregateRead])
def by_department(
    filters: TelemetryFilters = Depends(filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    return aggregate_endpoint("get_usage_by_department", "department_id", filters, params, db)


@router.get("/usage/by-team", response_model=PaginatedResponse[UsageAggregateRead])
def by_team(
    filters: TelemetryFilters = Depends(filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    return aggregate_endpoint("get_usage_by_team", "team_id", filters, params, db)


@router.get("/usage/by-member", response_model=PaginatedResponse[UsageAggregateRead])
def by_member(
    filters: TelemetryFilters = Depends(filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    return aggregate_endpoint("get_usage_by_member", "member_id", filters, params, db)


@router.get("/usage/by-model", response_model=PaginatedResponse[UsageAggregateRead])
def by_model(
    filters: TelemetryFilters = Depends(filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    return aggregate_endpoint("get_usage_by_model", "model", filters, params, db)


@router.get("/usage/recent", response_model=PaginatedResponse[UsageRecordRead])
def recent(
    filters: TelemetryFilters = Depends(filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    items = provider().get_recent_requests(filters, limit=10000)
    items = [{**item.__dict__, "estimated_cost": _cost(item, db)} for item in items]
    return page(items, params)


@router.get("/usage/errors", response_model=PaginatedResponse[ErrorAggregateRead])
def errors(
    filters: TelemetryFilters = Depends(filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    return page(provider().get_error_summary(filters), params)


@router.get("/usage/unmapped", response_model=PaginatedResponse[UnmappedSubscriptionRead])
def unmapped(
    filters: TelemetryFilters = Depends(filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    identity: Identity = Depends(require_role()),
):
    filters = scoped_filters(identity, db, filters)
    get_unmapped = getattr(provider(), "get_unmapped_subscriptions")
    return page(get_unmapped(filters), params)