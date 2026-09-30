from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch, TournamentSetResult


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


from app.tournament_matches import (
    create_match,
    list_matches,
    update_match,
    delete_match,
    get_scoreboard,
    add_point,
    close_set,
)
from app.schemas import TournamentMatchCreate, TournamentMatchUpdate, SetPointRequest


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


def test_set_result_roundtrip():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
    )
    db.add(m)
    db.flush()

    s = TournamentSetResult(match_id=m.id, set_number=1, points_a=18, points_b=16, closed=True)
    db.add(s)
    db.commit()

    saved = db.query(TournamentSetResult).filter_by(match_id=m.id).one()
    assert saved.set_number == 1
    assert saved.points_a == 18
    assert saved.points_b == 16
    assert saved.closed is True


def test_set_result_defaults():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
    )
    db.add(m)
    db.flush()

    s = TournamentSetResult(match_id=m.id, set_number=1)
    db.add(s)
    db.commit()

    assert s.points_a == 0
    assert s.points_b == 0
    assert s.closed is False


def make_match(db, tournament_id, team_a_id, team_b_id):
    return create_match(
        tournament_id,
        TournamentMatchCreate(team_a_id=team_a_id, team_b_id=team_b_id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )


def test_first_point_creates_set_one():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)

    board = get_scoreboard(t.id, m.id, db)
    assert len(board["sets"]) == 1
    assert board["sets"][0]["set_number"] == 1
    assert board["sets"][0]["points_a"] == 1
    assert board["current_set"]["points_a"] == 1
    assert board["current_set"]["target"] == 18
    assert board["current_set"]["is_over"] is False


def test_point_cannot_go_negative():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    with pytest.raises(HTTPException) as exc_info:
        add_point(t.id, m.id, SetPointRequest(team="a", delta=-1), db)
    assert exc_info.value.status_code == 400


def test_close_set_requires_set_to_be_over():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)
    add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)

    with pytest.raises(HTTPException) as exc_info:
        close_set(t.id, m.id, db)
    assert exc_info.value.status_code == 400


def test_close_set_and_start_next():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)

    closed = close_set(t.id, m.id, db)
    assert closed["closed"] is True
    assert closed["set_number"] == 1

    add_point(t.id, m.id, SetPointRequest(team="b", delta=1), db)
    board = get_scoreboard(t.id, m.id, db)
    assert board["current_set"]["set_number"] == 2
    assert board["current_set"]["points_b"] == 1


def test_match_finishes_and_status_updates_after_two_sets():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    close_set(t.id, m.id, db)

    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    close_set(t.id, m.id, db)

    board = get_scoreboard(t.id, m.id, db)
    assert board["result"]["winner"] == "A"
    assert board["result"]["sets_a"] == 2
    assert board["current_set"] is None

    db.refresh(m)
    assert m.status == "encerrado"


def test_cannot_add_point_after_match_decided():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    close_set(t.id, m.id, db)
    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    close_set(t.id, m.id, db)

    with pytest.raises(HTTPException) as exc_info:
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    assert exc_info.value.status_code == 400


def test_invalid_team_and_delta_rejected():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    with pytest.raises(HTTPException):
        add_point(t.id, m.id, SetPointRequest(team="c", delta=1), db)
    with pytest.raises(HTTPException):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=2), db)
