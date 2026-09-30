from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_tournament_and_teams(db):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    team_a = Team(tournament_id=t.id, code="A")
    team_b = Team(tournament_id=t.id, code="B")
    db.add_all([team_a, team_b])
    db.flush()
    return t, team_a, team_b


def test_tournament_match_roundtrip():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    m = TournamentMatch(
        tournament_id=t.id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
        court="Quadra 1",
    )
    db.add(m)
    db.commit()

    saved = db.query(TournamentMatch).filter_by(tournament_id=t.id).one()
    assert saved.team_a_id == team_a.id
    assert saved.team_b_id == team_b.id
    assert saved.scheduled_at == datetime(2026, 11, 28, 13, 0)
    assert saved.court == "Quadra 1"


def test_tournament_match_defaults():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    m = TournamentMatch(
        tournament_id=t.id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
    )
    db.add(m)
    db.commit()

    assert m.status == "agendado"
    assert m.is_final is False
    assert m.court is None


from app.tournament_matches import create_match, list_matches, update_match, delete_match
from app.schemas import TournamentMatchCreate, TournamentMatchUpdate


def test_create_and_list_matches():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    matches = list_matches(t.id, db)
    assert len(matches) == 1
    assert matches[0]["team_a_code"] == "A"
    assert matches[0]["team_b_code"] == "B"
    assert matches[0]["status"] == "agendado"


def test_matches_are_listed_in_scheduled_order():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 15, 0)),
        db,
    )
    create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    matches = list_matches(t.id, db)
    scheduled_times = [m["scheduled_at"] for m in matches]
    assert scheduled_times == sorted(scheduled_times)


def test_create_match_rejects_same_team_twice():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    with pytest.raises(HTTPException):
        create_match(
            t.id,
            TournamentMatchCreate(
                team_a_id=team_a.id, team_b_id=team_a.id, scheduled_at=datetime(2026, 11, 28, 13, 0)
            ),
            db,
        )


def test_create_match_404s_on_team_from_another_tournament():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t1, team_a, _team_b = make_tournament_and_teams(db)
    _t2, _other_a, other_b = make_tournament_and_teams(db)

    with pytest.raises(HTTPException):
        create_match(
            t1.id,
            TournamentMatchCreate(
                team_a_id=team_a.id, team_b_id=other_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)
            ),
            db,
        )


def test_update_match_status():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    updated = update_match(t.id, m.id, TournamentMatchUpdate(status="em_andamento"), db)
    assert updated.status == "em_andamento"


def test_update_match_rejects_invalid_status():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    with pytest.raises(HTTPException) as exc_info:
        update_match(t.id, m.id, TournamentMatchUpdate(status="xyz"), db)
    assert exc_info.value.status_code == 400


def test_delete_match():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    delete_match(t.id, m.id, db)

    assert list_matches(t.id, db) == []


def test_update_missing_match_raises_404():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, _team_a, _team_b = make_tournament_and_teams(db)

    with pytest.raises(HTTPException) as exc_info:
        update_match(t.id, 999, TournamentMatchUpdate(status="encerrado"), db)
    assert exc_info.value.status_code == 404
