from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class UsageSummaryRead(BaseModel):
    request_count: int
    total_tokens: int | None
    estimated_cost: Decimal | None
    error_count: int


class UsagePointRead(BaseModel):
    period: datetime
    request_count: int
    total_tokens: int | None
    estimated_cost: Decimal | None


class UsageAggregateRead(BaseModel):
    key: int | str
    request_count: int
    total_tokens: int | None
    estimated_cost: Decimal | None


class UsageRecordRead(BaseModel):
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


class ErrorAggregateRead(BaseModel):
    error_code: str
    request_count: int


class UnmappedSubscriptionRead(BaseModel):
    apim_subscription_id: str
    request_count: int
    first_seen: datetime
    last_seen: datetime
    total_tokens: int | None
    estimated_cost: Decimal | None