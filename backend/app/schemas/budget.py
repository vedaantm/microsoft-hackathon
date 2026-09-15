from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


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
    created_at: datetime
    updated_at: datetime


class BudgetStatusRead(BaseModel):
    scope_type: str
    scope_id: int
    budget_amount: Decimal
    estimated_spent_amount: Decimal
    estimated_remaining_amount: Decimal
    utilization: Decimal
    currency: str