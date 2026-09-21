from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Application,
    BudgetPolicy,
    Department,
    Member,
    MemberSubscription,
    ModelConfiguration,
    Organization,
    Team,
    UsageEvent,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "sample-data"
if not FIXTURES.exists():
    FIXTURES = Path(__file__).resolve().parents[1] / "sample-data"


def load_json(name: str):
    with (FIXTURES / name).open(encoding="utf-8") as fixture:
        return json.load(fixture)


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def seed(session: Session) -> None:
    data = load_json("organization.json")
    organization = Organization(**data["organization"])
    session.add(organization)
    session.flush()

    departments = {}
    for item in data["departments"]:
        department = Department(organization_id=organization.id, **item)
        session.add(department)
        departments[item["slug"]] = department
    session.flush()

    teams = {}
    for item in data["teams"]:
        department = departments[item.pop("department_slug")]
        team = Team(
            organization_id=organization.id, department_id=department.id, **item, status="active"
        )
        session.add(team)
        teams[team.slug] = team
    session.flush()

    for item in data["applications"]:
        team = teams[item.pop("team_slug")]
        session.add(
            Application(organization_id=organization.id, team_id=team.id, status="active", **item)
        )
    session.flush()

    members = {}
    for item in data["members"]:
        team = teams[item.pop("team_slug")]
        member = Member(
            organization_id=organization.id,
            department_id=team.department_id,
            team_id=team.id,
            status="active",
            **item,
        )
        session.add(member)
        members[member.email] = member
    session.flush()

    for item in data["subscriptions"]:
        session.add(
            MemberSubscription(
                member_id=members[item["email"]].id,
                apim_subscription_id=item["apim_subscription_id"],
            )
        )

    # Local gateway pricing is $0 while it uses a free tier; replace it when billing applies.
    for item in load_json("models.json"):
        session.add(
            ModelConfiguration(
                organization_id=organization.id,
                effective_from=parse_datetime(item.pop("effective_from")),
                **{
                    key: Decimal(str(value)) if "cost" in key else value
                    for key, value in item.items()
                },
            )
        )

    session.flush()
    slug_by_scope = {organization.slug: organization}
    slug_by_scope.update({department.slug: department for department in departments.values()})
    slug_by_scope.update({team.slug: team for team in teams.values()})
    for item in load_json("budgets.json"):
        if item["scope_type"] == "member":
            scope_id = members[item["scope_email"]].id
        else:
            scope_id = slug_by_scope[item["scope_slug"]].id
        session.add(
            BudgetPolicy(
                organization_id=organization.id,
                scope_type=item["scope_type"],
                scope_id=scope_id,
                budget_amount=Decimal(str(item["budget_amount"])),
                effective_from=parse_datetime(item["effective_from"]),
                effective_to=parse_datetime(item["effective_to"]) if item["effective_to"] else None,
            )
        )

    session.flush()
    subscriptions = {
        subscription.apim_subscription_id: subscription
        for member in members.values()
        for subscription in member.subscriptions
    }
    for item in load_json("usage-events.json"):
        subscription = subscriptions.get(item["apim_subscription_id"])
        member = members[subscription.member.email] if subscription else None
        values = {
            **item,
            "timestamp": parse_datetime(item["timestamp"]),
            "estimated_cost": Decimal(str(item["estimated_cost"])),
            "organization_id": organization.id if member else None,
            "department_id": member.department_id if member else None,
            "team_id": member.team_id if member else None,
            "member_id": member.id if member else None,
        }
        session.add(UsageEvent(**values))


def main() -> None:
    with SessionLocal.begin() as session:
        seed(session)
    print("Seed data loaded successfully.")


if __name__ == "__main__":
    main()
