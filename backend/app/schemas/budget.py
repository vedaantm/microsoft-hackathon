from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import UtcDatetime


class BudgetCreate(BaseModel):
    organization_id: int
    scope_type: str
    scope_id: int
    budget_amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    effective_from: datetime
    effective_to: datetime | None = None
    status: str = "active"


class BudgetPatch(BaseModel):
    budget_amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    status: str | None = None


class BudgetRead(BudgetCreate):
    id: int
    effective_from: UtcDatetime
    effective_to: UtcDatetime | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class BudgetStatusRead(BaseModel):
    scope_type: str
    scope_id: int
    budget_amount: Decimal
    estimated_spent_amount: Decimal
    estimated_remaining_amount: Decimal
    utilization: Decimal
    currency: str