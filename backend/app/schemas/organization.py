from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UtcDatetime


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100)
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    status: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100)
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    slug: str
    status: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100)
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    department_id: int
    name: str
    slug: str
    status: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(min_length=1, max_length=30)
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    role: str | None = Field(default=None, min_length=1, max_length=30)
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    department_id: int
    team_id: int
    name: str
    email: str
    role: str
    status: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apim_subscription_id: str = Field(min_length=1, max_length=200)
    subscription_display_name: str | None = Field(default=None, max_length=200)
    status: str = Field(default="active", pattern="^(active|inactive|archived)$")
    last_rotated_at: datetime | None = None


class SubscriptionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apim_subscription_id: str | None = Field(default=None, min_length=1, max_length=200)
    subscription_display_name: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|inactive|archived)$")
    last_rotated_at: datetime | None = None


class SubscriptionRead(BaseModel):
    apim_subscription_id: str
    subscription_display_name: str | None = None
    status: str
    last_rotated_at: UtcDatetime | None = None