from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.tournament import create_tournament, active_tournament, create_team, tournament_state
from app.schemas import TournamentCreate, TeamCreate


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_tournament_activates_it():
    db = make_db()
    t = create_tournament(
        TournamentCreate(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29)), db
    )
    assert t.active is True

    active = active_tournament(db)
    assert active["id"] == t.id
    assert active["name"] == "Torneio"


def test_creating_a_new_tournament_deactivates_the_previous_one():
    db = make_db()
    first = create_tournament(
        TournamentCreate(name="Primeiro", start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)), db
    )
    second = create_tournament(
        TournamentCreate(name="Segundo", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29)), db
    )

    db.refresh(first)
    assert first.active is False
    assert second.active is True

    active = active_tournament(db)
    assert active["id"] == second.id


def test_active_tournament_returns_none_when_there_is_none():
    db = make_db()
    assert active_tournament(db) is None


def test_create_team_and_read_tournament_state():
    db = make_db()
    t = create_tournament(
        TournamentCreate(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29)), db
    )
    create_team(t.id, TeamCreate(code="A"), db)
    create_team(t.id, TeamCreate(code="B"), db)

    state = tournament_state(t.id, db)
    assert state["tournament"]["name"] == "Torneio"
    codes = sorted(team["code"] for team in state["teams"])
    assert codes == ["A", "B"]
    assert all(team["players"] == [] for team in state["teams"])


def test_create_team_for_missing_tournament_raises_404():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    with pytest.raises(HTTPException):
        create_team(999, TeamCreate(code="A"), db)


def test_tournament_state_for_missing_tournament_raises_404():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    with pytest.raises(HTTPException):
        tournament_state(999, db)
