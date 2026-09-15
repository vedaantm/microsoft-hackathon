from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.common import commit, get_db, get_or_404, page_params
from app.models import BudgetPolicy, Department, Member, Organization, Team
from app.schemas import (
    BudgetCreate,
    BudgetPatch,
    BudgetRead,
    BudgetStatusRead,
    PageParams,
    PaginatedResponse,
)
from app.telemetry import TelemetryFilters

router = APIRouter()
# TODO(Phase 5): enforce role-based authorization


def _error(message: str, code: str = "budget_conflict") -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": code, "message": message, "field_errors": []},
    )


def _overlaps(candidate: BudgetPolicy, existing: BudgetPolicy) -> bool:
    candidate_end = candidate.effective_to or datetime.max
    existing_end = existing.effective_to or datetime.max
    return candidate.effective_from < existing_end and existing.effective_from < candidate_end


def ensure_valid(policy: BudgetPolicy, db: Session, exclude_id: int | None = None) -> None:
    if policy.effective_to is not None and policy.effective_to <= policy.effective_from:
        raise _error("effective_to must be after effective_from.", "validation_error")
    if policy.status != "active":
        return
    matches = db.query(BudgetPolicy).filter(
        BudgetPolicy.scope_type == policy.scope_type,
        BudgetPolicy.scope_id == policy.scope_id,
        BudgetPolicy.status == "active",
    )
    for existing in matches:
        if existing.id != exclude_id and _overlaps(policy, existing):
            raise _error("An active budget policy already overlaps this scope and date range.")


def read(policy: BudgetPolicy) -> BudgetPolicy:
    return policy


def resolved_policies(db: Session, as_of: datetime) -> list[tuple[str, int, BudgetPolicy]]:
    policies = db.query(BudgetPolicy).filter(BudgetPolicy.status == "active").all()
    selected: dict[tuple[str, int], BudgetPolicy] = {}
    for policy in policies:
        if policy.effective_from <= as_of and (
            policy.effective_to is None or as_of < policy.effective_to
        ):
            key = (policy.scope_type, policy.scope_id)
            if key not in selected or policy.effective_from > selected[key].effective_from:
                selected[key] = policy

    def policy_for(scope_chain: list[tuple[str, int]]) -> BudgetPolicy | None:
        for scope in reversed(scope_chain):
            if scope in selected:
                return selected[scope]
        return None

    resolved: list[tuple[str, int, BudgetPolicy]] = []
    for organization in db.query(Organization).all():
        organization_scope = [("organization", organization.id)]
        policy = policy_for(organization_scope)
        if policy:
            resolved.append(("organization", organization.id, policy))
        for department in db.query(Department).filter_by(organization_id=organization.id):
            department_scope = organization_scope + [("department", department.id)]
            policy = policy_for(department_scope)
            if policy:
                resolved.append(("department", department.id, policy))
            for team in db.query(Team).filter_by(department_id=department.id):
                team_scope = department_scope + [("team", team.id)]
                policy = policy_for(team_scope)
                if policy:
                    resolved.append(("team", team.id, policy))
                for member in db.query(Member).filter_by(team_id=team.id):
                    member_scope = team_scope + [("member", member.id)]
                    policy = policy_for(member_scope)
                    if policy:
                        resolved.append(("member", member.id, policy))
    return resolved


@router.get("/budgets", response_model=PaginatedResponse[BudgetRead])
def list_budgets(params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    items = db.query(BudgetPolicy).order_by(BudgetPolicy.id).all()
    start = (params.page - 1) * params.page_size
    return {
        "items": items[start : start + params.page_size],
        "total": len(items),
        **params.model_dump(),
    }


@router.post("/budgets", response_model=BudgetRead, status_code=201)
def create_budget(payload: BudgetCreate, db: Session = Depends(get_db)):
    policy = BudgetPolicy(**payload.model_dump())
    ensure_valid(policy, db)
    db.add(policy)
    commit(db)
    db.refresh(policy)
    return read(policy)


@router.patch("/budgets/{budget_id}", response_model=BudgetRead)
def patch_budget(budget_id: int, payload: BudgetPatch, db: Session = Depends(get_db)):
    policy = get_or_404(db, BudgetPolicy, budget_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, key, value)
    ensure_valid(policy, db, exclude_id=policy.id)
    commit(db)
    db.refresh(policy)
    return read(policy)


@router.get("/budgets/status", response_model=PaginatedResponse[BudgetStatusRead])
def budget_status(
    as_of: datetime | None = Query(default=None),
    organization_id: int | None = None,
    department_id: int | None = None,
    team_id: int | None = None,
    member_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    from app.main import telemetry_provider

    filters = TelemetryFilters(
        date_from=date_from, date_to=date_to, organization_id=organization_id,
        department_id=department_id, team_id=team_id, member_id=member_id,
    )
    from app.api.v1.usage import _cost

    records = telemetry_provider.get_recent_requests(filters, limit=100000)
    spent_by_scope: dict[tuple[str, int], object] = {}
    for record in records:
        cost = _cost(record, db)
        if cost is None:
            continue
        for scope_type, scope_id in (
            ("organization", record.organization_id),
            ("department", record.department_id),
            ("team", record.team_id),
            ("member", record.member_id),
        ):
            key = (scope_type, scope_id)
            spent_by_scope[key] = spent_by_scope.get(key, 0) + cost
    rows = []
    for scope_type, scope_id, policy in resolved_policies(db, as_of or datetime.utcnow()):
        spent = spent_by_scope.get((scope_type, scope_id), 0)
        rows.append({
            "scope_type": scope_type, "scope_id": scope_id,
            "budget_amount": policy.budget_amount,
            "estimated_spent_amount": spent,
            "estimated_remaining_amount": policy.budget_amount - spent,
            "utilization": spent / policy.budget_amount if policy.budget_amount else 0,
            "currency": policy.currency,
        })
    start = (params.page - 1) * params.page_size
    return {
        "items": rows[start : start + params.page_size],
        "total": len(rows),
        **params.model_dump(),
    }