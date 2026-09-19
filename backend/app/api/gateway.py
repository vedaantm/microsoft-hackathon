from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from openai import OpenAI, RateLimitError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.v1.budgets import resolved_policy_for_member
from app.api.v1.common import get_db
from app.models import Member, MemberSubscription, ModelConfiguration, UsageEvent

router = APIRouter()
GATEWAY_MODEL_ALIAS = "local-live"


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = GATEWAY_MODEL_ALIAS
    messages: list[dict[str, Any]] = Field(min_length=1)


def _gateway_error(status_code: int, error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "message": message, "field_errors": []},
    )


def _usage_values(completion: Any) -> tuple[int | None, int | None, int | None]:
    usage = completion.usage
    if usage is None:
        return None, None, None
    return usage.prompt_tokens, usage.completion_tokens, usage.total_tokens


def _estimated_cost(
    configuration: ModelConfiguration,
    input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal:
    input_cost = (Decimal(input_tokens or 0) / 1000) * configuration.input_cost_per_1k_tokens
    output_cost = (Decimal(output_tokens or 0) / 1000) * configuration.output_cost_per_1k_tokens
    return input_cost + output_cost


def _record_event(
    db: Session,
    *,
    subscription: MemberSubscription,
    member: Member,
    configuration: ModelConfiguration,
    request_id: str,
    started_at: datetime,
    latency_ms: int,
    outcome: str,
    error_code: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
) -> None:
    db.add(
        UsageEvent(
            request_id=request_id,
            apim_subscription_id=subscription.apim_subscription_id,
            organization_id=member.organization_id,
            department_id=member.department_id,
            team_id=member.team_id,
            member_id=member.id,
            timestamp=started_at,
            model_alias=GATEWAY_MODEL_ALIAS,
            outcome=outcome,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            token_count_estimated=False,
            estimated_cost=_estimated_cost(configuration, input_tokens, output_tokens),
            latency_ms=latency_ms,
            error_code=error_code,
            telemetry_source="local_gateway",
        )
    )
    db.commit()


def _used_tokens(db: Session, scope_type: str, scope_id: int) -> int:
    scope_column = getattr(UsageEvent, f"{scope_type}_id")
    events = db.query(UsageEvent.total_tokens).filter(scope_column == scope_id).all()
    return sum(total_tokens or 0 for (total_tokens,) in events)


@router.post("/chat/completions")
def chat_completions(
    payload: ChatCompletionRequest,
    ocp_apim_subscription_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not ocp_apim_subscription_key:
        raise _gateway_error(
            401, "invalid_subscription_key", "A valid subscription key is required."
        )

    request_id = str(uuid4())
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    started_clock = time.perf_counter()
    subscription = (
        db.query(MemberSubscription)
        .filter(
            MemberSubscription.apim_subscription_id == ocp_apim_subscription_key,
            MemberSubscription.status == "active",
        )
        .first()
    )
    member = db.get(Member, subscription.member_id) if subscription else None
    if subscription is None or member is None or member.status != "active":
        raise _gateway_error(
            401, "invalid_subscription_key", "A valid subscription key is required."
        )
    if payload.model != GATEWAY_MODEL_ALIAS:
        raise _gateway_error(
            400, "unsupported_model", f"Only {GATEWAY_MODEL_ALIAS!r} is supported."
        )

    configuration = (
        db.query(ModelConfiguration)
        .filter(
            ModelConfiguration.organization_id == member.organization_id,
            ModelConfiguration.alias == GATEWAY_MODEL_ALIAS,
            ModelConfiguration.status == "active",
        )
        .order_by(ModelConfiguration.effective_from.desc())
        .first()
    )
    if configuration is None:
        raise _gateway_error(
            503, "gateway_not_configured", "The local gateway model is not configured."
        )

    resolved_policy = resolved_policy_for_member(db, member, datetime.now(timezone.utc))
    if resolved_policy is not None:
        scope_type, scope_id, policy = resolved_policy
        if _used_tokens(db, scope_type, scope_id) >= policy.budget_amount:
            _record_event(
                db,
                subscription=subscription,
                member=member,
                configuration=configuration,
                request_id=request_id,
                started_at=started_at,
                latency_ms=round((time.perf_counter() - started_clock) * 1000),
                outcome="quota_blocked",
                error_code="QUOTA_EXCEEDED",
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            )
            raise _gateway_error(
                403,
                "budget_exceeded",
                "The applicable token budget has been exceeded.",
            )

    try:
        client = OpenAI(
            api_key=os.getenv("GATEWAY_LLM_API_KEY"),
            base_url=os.getenv("GATEWAY_LLM_BASE_URL") or None,
        )
        completion = client.chat.completions.create(
            model=os.getenv("GATEWAY_LLM_MODEL") or configuration.provider_model,
            messages=payload.messages,
        )
        input_tokens, output_tokens, total_tokens = _usage_values(completion)
        _record_event(
            db,
            subscription=subscription,
            member=member,
            configuration=configuration,
            request_id=request_id,
            started_at=started_at,
            latency_ms=round((time.perf_counter() - started_clock) * 1000),
            outcome="success",
            error_code=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
        return completion.model_dump()
    except RateLimitError as exc:
        _record_event(
            db,
            subscription=subscription,
            member=member,
            configuration=configuration,
            request_id=request_id,
            started_at=started_at,
            latency_ms=round((time.perf_counter() - started_clock) * 1000),
            outcome="rate_limited",
            error_code="429",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
        )
        raise _gateway_error(
            429, "provider_rate_limited", "The model provider rate-limited the request."
        ) from exc
    except Exception as exc:
        _record_event(
            db,
            subscription=subscription,
            member=member,
            configuration=configuration,
            request_id=request_id,
            started_at=started_at,
            latency_ms=round((time.perf_counter() - started_clock) * 1000),
            outcome="provider_error",
            error_code=type(exc).__name__,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
        )
        raise _gateway_error(502, "provider_error", "The model provider request failed.") from exc
