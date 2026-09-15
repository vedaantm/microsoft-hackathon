from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    departments: Mapped[list[Department]] = relationship(back_populates="organization")
    teams: Mapped[list[Team]] = relationship(back_populates="organization")
    members: Mapped[list[Member]] = relationship(back_populates="organization")
    applications: Mapped[list[Application]] = relationship(back_populates="organization")
    model_configurations: Mapped[list[ModelConfiguration]] = relationship(
        back_populates="organization"
    )
    usage_events: Mapped[list[UsageEvent]] = relationship(back_populates="organization")


class Department(TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_departments_org_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="departments")
    teams: Mapped[list[Team]] = relationship(back_populates="department")
    members: Mapped[list[Member]] = relationship(back_populates="department")
    usage_events: Mapped[list[UsageEvent]] = relationship(back_populates="department")


class Team(TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_teams_org_slug"),
        UniqueConstraint("department_id", "slug", name="uq_teams_department_slug"),
        UniqueConstraint("department_id", "name", name="uq_teams_department_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="teams")
    department: Mapped[Department] = relationship(back_populates="teams")
    members: Mapped[list[Member]] = relationship(back_populates="team")
    applications: Mapped[list[Application]] = relationship(back_populates="team")
    usage_events: Mapped[list[UsageEvent]] = relationship(back_populates="team")


class Member(TimestampMixin, Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="members")
    department: Mapped[Department] = relationship(back_populates="members")
    team: Mapped[Team] = relationship(back_populates="members")
    subscriptions: Mapped[list[MemberSubscription]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
    usage_events: Mapped[list[UsageEvent]] = relationship(back_populates="member")


class MemberSubscription(Base):
    __tablename__ = "member_subscriptions"
    __table_args__ = (
        Index("ix_member_subscriptions_apim_subscription_id", "apim_subscription_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)
    apim_subscription_id: Mapped[str] = mapped_column(String(200), nullable=False)
    subscription_display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    member: Mapped[Member] = relationship(back_populates="subscriptions")


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_applications_org_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="applications")
    team: Mapped[Team | None] = relationship(back_populates="applications")
    usage_events: Mapped[list[UsageEvent]] = relationship(back_populates="application")


class ModelConfiguration(TimestampMixin, Base):
    __tablename__ = "model_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(200), nullable=False)
    input_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    output_cost_per_1k_tokens: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="model_configurations")


class BudgetPolicy(TimestampMixin, Base):
    __tablename__ = "budget_policies"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('organization', 'department', 'team', 'member')",
            name="ck_budget_scope_type",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_budget_effective_range",
        ),
        Index(
            "ix_budget_policies_scope_dates",
            "scope_type",
            "scope_id",
            "effective_from",
            "effective_to",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_member_timestamp", "member_id", "timestamp"),
        Index("ix_usage_events_team_timestamp", "team_id", "timestamp"),
        Index("ix_usage_events_subscription_timestamp", "apim_subscription_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    apim_subscription_id: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    model_alias: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    token_count_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))

    organization: Mapped[Organization | None] = relationship(back_populates="usage_events")
    department: Mapped[Department | None] = relationship(back_populates="usage_events")
    team: Mapped[Team | None] = relationship(back_populates="usage_events")
    member: Mapped[Member | None] = relationship(back_populates="usage_events")
    application: Mapped[Application | None] = relationship(back_populates="usage_events")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
