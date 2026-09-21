from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Application, Base, Member, MemberSubscription, Organization
from scripts import seed


@pytest.fixture
def session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
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
