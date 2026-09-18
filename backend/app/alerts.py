from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Alert, BudgetPolicy, MemberSubscription, UsageEvent

TOKEN_QUOTA = 1000
REPEATED_FAILURE_THRESHOLD = 2


@dataclass(frozen=True)
class AlertCandidate:
    organization_id: int
    scope_type: str
    scope_id: int
    alert_type: str
    severity: str
    message: str


def _scope(event: UsageEvent) -> tuple[str, int] | None:
    if event.member_id is not None:
        return "member", event.member_id
    if event.team_id is not None:
        return "team", event.team_id
    if event.department_id is not None:
        return "department", event.department_id
    if event.organization_id is not None:
        return "organization", event.organization_id
    return None


def _candidate(
    organization_id: int,
    scope: tuple[str, int],
    alert_type: str,
    severity: str,
    message: str,
) -> AlertCandidate:
    return AlertCandidate(organization_id, scope[0], scope[1], alert_type, severity, message)


def compute_alert_candidates(
    events: Iterable[UsageEvent],
    budgets: Iterable[BudgetPolicy],
    subscriptions: Iterable[MemberSubscription],
    *,
    token_quota: int = TOKEN_QUOTA,
) -> list[AlertCandidate]:
    events = list(events)
    candidates: list[AlertCandidate] = []
    token_totals: defaultdict[tuple[int, str, int], int] = defaultdict(int)
    costs: defaultdict[tuple[int, str, int], Decimal] = defaultdict(lambda: Decimal("0"))
    repeated: defaultdict[tuple[str, tuple[str, int]], int] = defaultdict(int)
    missing: defaultdict[tuple[str, int], int] = defaultdict(int)
    mapped_subscription_ids = {subscription.apim_subscription_id for subscription in subscriptions}
    organization_ids = {
        event.organization_id
        for event in events
        if event.organization_id is not None
    }

    for event in events:
        scope = _scope(event)
        if scope is not None and event.organization_id is not None:
            key = (event.organization_id, *scope)
            token_totals[key] += event.total_tokens or 0
            costs[key] += event.estimated_cost or Decimal("0")
            if event.outcome in {"rate_limited", "quota_blocked"}:
                repeated[("rate_limit_or_quota", (event.organization_id, *scope))] += 1
            if event.outcome == "provider_error":
                repeated[("provider_failure", (event.organization_id, *scope))] += 1
            if any(
                value is None
                for value in (event.input_tokens, event.output_tokens, event.total_tokens)
            ):
                missing[scope] += 1

        if event.apim_subscription_id not in mapped_subscription_ids:
            organization_id = event.organization_id or next(iter(organization_ids), 1)
            candidates.append(
                _candidate(
                    organization_id,
                    ("organization", organization_id),
                    "unmapped_subscription",
                    "warning",
                    f"APIM subscription {event.apim_subscription_id} is not mapped to a member.",
                )
            )

    for key, total in token_totals.items():
        organization_id, scope_type, scope_id = key
        percent = total / token_quota if token_quota else 0
        for threshold, severity in ((0.8, "warning"), (0.9, "high"), (1.0, "critical")):
            if percent >= threshold:
                candidates.append(
                    _candidate(
                        organization_id,
                        (scope_type, scope_id),
                        f"token_quota_{int(threshold * 100)}",
                        severity,
                        f"{scope_type.title()} token usage reached {int(percent * 100)}% of quota.",
                    )
                )

    for policy in budgets:
        key = (policy.organization_id, policy.scope_type, policy.scope_id)
        utilization = costs[key] / policy.budget_amount if policy.budget_amount else Decimal("0")
        if utilization >= 1:
            severity = "critical"
        elif utilization >= Decimal("0.8"):
            severity = "warning"
        else:
            continue
        candidates.append(
            _candidate(
                policy.organization_id,
                (policy.scope_type, policy.scope_id),
                "cost_budget_threshold",
                severity,
                f"{policy.scope_type.title()} estimated cost reached {utilization:.0%} of budget.",
            )
        )

    for (failure_type, scoped), count in repeated.items():
        if count >= REPEATED_FAILURE_THRESHOLD:
            organization_id, scope_type, scope_id = scoped
            alert_type = "repeated_rate_limit_or_quota"
            if failure_type != "rate_limit_or_quota":
                alert_type = "repeated_provider_failure"
            message = (
                f"{count} rate-limit or quota-block responses were recorded."
                if failure_type == "rate_limit_or_quota"
                else f"{count} provider failures were recorded."
            )
            candidates.append(
                _candidate(
                    organization_id,
                    (scope_type, scope_id),
                    alert_type,
                    "high",
                    message,
                )
            )

    for scope, count in missing.items():
        if count:
            organization_id = next(
                (
                    event.organization_id
                    for event in events
                    if _scope(event) == scope and event.organization_id is not None
                ),
                1,
            )
            candidates.append(
                _candidate(
                    organization_id,
                    scope,
                    "missing_token_telemetry",
                    "warning",
                    f"{count} usage event(s) are missing token telemetry.",
                )
            )

    unique: dict[tuple[int, str, int, str], AlertCandidate] = {}
    for candidate in candidates:
        unique[
            (
                candidate.organization_id,
                candidate.scope_type,
                candidate.scope_id,
                candidate.alert_type,
            )
        ] = candidate
    return list(unique.values())


def refresh_alerts(db: Session, *, token_quota: int = TOKEN_QUOTA) -> None:
    events = db.query(UsageEvent).all()
    budgets = db.query(BudgetPolicy).filter(BudgetPolicy.status == "active").all()
    subscriptions = db.query(MemberSubscription).filter(MemberSubscription.status == "active").all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for candidate in compute_alert_candidates(
        events, budgets, subscriptions, token_quota=token_quota
    ):
        existing = (
            db.query(Alert)
            .filter(
                Alert.organization_id == candidate.organization_id,
                Alert.scope_type == candidate.scope_type,
                Alert.scope_id == candidate.scope_id,
                Alert.alert_type == candidate.alert_type,
                Alert.status == "open",
            )
            .first()
        )
        if existing is None:
            db.add(
                Alert(
                    organization_id=candidate.organization_id,
                    scope_type=candidate.scope_type,
                    scope_id=candidate.scope_id,
                    alert_type=candidate.alert_type,
                    severity=candidate.severity,
                    message=candidate.message,
                    triggered_at=now,
                )
            )
    db.commit()
