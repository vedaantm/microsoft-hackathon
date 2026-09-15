from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Application, Base, BudgetPolicy, Member, MemberSubscription, Organization
from scripts import seed


@pytest.fixture
def session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TRIGGER budget_policy_no_overlap
            BEFORE INSERT ON budget_policies
            WHEN NEW.status = 'active' AND EXISTS (
                SELECT 1 FROM budget_policies existing
                WHERE existing.status = 'active'
                  AND existing.scope_type = NEW.scope_type
                  AND existing.scope_id = NEW.scope_id
                  AND existing.effective_from < COALESCE(NEW.effective_to, '9999-12-31 23:59:59')
                  AND NEW.effective_from < COALESCE(existing.effective_to, '9999-12-31 23:59:59')
            )
            BEGIN
                SELECT RAISE(ABORT, 'active budget policies overlap');
            END;
        """)
    with sessionmaker(bind=engine).begin() as db_session:
        yield db_session


def test_seed_loader_populates_all_fixture_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(seed, "SessionLocal", factory)

    with factory.begin() as db_session:
        seed.seed(db_session)
        assert db_session.query(Organization).count() == 1
        assert db_session.query(Application).count() == 1
        assert db_session.query(Member).count() == 12
        assert db_session.query(MemberSubscription).count() == 12
        assert db_session.query(seed.UsageEvent).count() == 32
        assert (
            db_session.query(seed.UsageEvent).filter(seed.UsageEvent.member_id.is_(None)).count()
            == 1
        )


def test_subscription_id_unique_constraint_rejects_duplicate(session) -> None:
    organization = Organization(name="Test Org", slug="test-org")
    session.add(organization)
    session.flush()
    first = Member(
        organization_id=organization.id,
        department_id=1,
        team_id=1,
        name="One",
        email="one@example.test",
        role="member",
    )
    second = Member(
        organization_id=organization.id,
        department_id=1,
        team_id=1,
        name="Two",
        email="two@example.test",
        role="member",
    )
    session.add_all([first, second])
    session.flush()
    session.add_all(
        [
            MemberSubscription(member_id=first.id, apim_subscription_id="duplicate"),
            MemberSubscription(member_id=second.id, apim_subscription_id="duplicate"),
        ]
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_active_budget_overlap_rejected(session) -> None:
    session.add(
        BudgetPolicy(
            organization_id=1,
            scope_type="organization",
            scope_id=1,
            budget_amount=100,
            effective_from=datetime(2026, 1, 1),
            effective_to=datetime(2026, 2, 1),
        )
    )
    session.flush()
    session.add(
        BudgetPolicy(
            organization_id=1,
            scope_type="organization",
            scope_id=1,
            budget_amount=200,
            effective_from=datetime(2026, 1, 15),
            effective_to=datetime(2026, 3, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
