from datetime import date, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.models import Tournament, Team, TournamentSetResult
from app.schemas import (
    TournamentMatchCreate, SetPointRequest, WalkoverRequest, GenerateSemifinalsRequest,
)
from app.tournament_matches import (
    create_match, get_scoreboard, add_point, get_standings,
    set_walkover, undo_walkover, generate_semifinals,
)

WHEN = datetime(2026, 11, 28, 13, 0)


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_teams(db, codes=("A1", "A2", "A3", "B1", "B2", "B3")):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    teams = {}
    for code in codes:
        teams[code] = Team(tournament_id=t.id, code=code, group_name=code[0])
        db.add(teams[code])
    db.commit()
    return t, teams


def new_match(db, t, a, b, stage="grupos"):
    return create_match(
        t.id, TournamentMatchCreate(team_a_id=a.id, team_b_id=b.id, scheduled_at=WHEN, stage=stage), db
    )


def sets_of(db, match):
    rows = db.execute(
        select(TournamentSetResult).where(TournamentSetResult.match_id == match.id).order_by(TournamentSetResult.set_number)
    ).scalars().all()
    return [(r.points_a, r.points_b, r.closed) for r in rows]


def test_walkover_records_two_closed_15_0_sets_for_the_team_that_showed_up():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["A2"])

    set_walkover(t.id, m.id, WalkoverRequest(present="a"), db)

    assert sets_of(db, m) == [(15, 0, True), (15, 0, True)]
    assert (m.status, m.walkover) == ("encerrado", True)
    board = get_scoreboard(t.id, m.id, db)
    assert board["result"]["winner"] == "A"
    assert (board["result"]["sets_a"], board["result"]["sets_b"]) == (2, 0)
    assert board["match"]["walkover"] is True


def test_walkover_when_team_b_shows_up():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["A2"])

    set_walkover(t.id, m.id, WalkoverRequest(present="b"), db)

    assert sets_of(db, m) == [(0, 15, True), (0, 15, True)]
    assert get_scoreboard(t.id, m.id, db)["result"]["winner"] == "B"


def test_walkover_counts_like_a_2_0_in_the_standings():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["A2"])
    set_walkover(t.id, m.id, WalkoverRequest(present="a"), db)

    group_a = next(g for g in get_standings(t.id, db) if g["group"] == "A")
    rows = {r["team"]: r for r in group_a["rows"]}

    assert (rows["A1"]["tournament_points"], rows["A1"]["wins"], rows["A1"]["sets_balance"], rows["A1"]["points_balance"]) == (3, 1, 2, 30)
    assert (rows["A2"]["tournament_points"], rows["A2"]["losses"], rows["A2"]["sets_balance"], rows["A2"]["points_balance"]) == (0, 1, -2, -30)


def test_walkover_rejects_an_unknown_side():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["A2"])

    with pytest.raises(HTTPException) as exc_info:
        set_walkover(t.id, m.id, WalkoverRequest(present="x"), db)
    assert exc_info.value.status_code == 400


def test_walkover_rejects_a_match_that_already_has_a_score():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["A2"])
    add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)

    with pytest.raises(HTTPException) as exc_info:
        set_walkover(t.id, m.id, WalkoverRequest(present="a"), db)
    assert exc_info.value.status_code == 409


def test_walkover_cannot_be_applied_twice():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["A2"])
    set_walkover(t.id, m.id, WalkoverRequest(present="a"), db)

    with pytest.raises(HTTPException) as exc_info:
        set_walkover(t.id, m.id, WalkoverRequest(present="b"), db)
    assert exc_info.value.status_code == 409


def test_undo_walkover_reopens_the_match():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["A2"])
    set_walkover(t.id, m.id, WalkoverRequest(present="a"), db)

    undo_walkover(t.id, m.id, db)

    assert sets_of(db, m) == []
    assert (m.status, m.walkover) == ("agendado", False)
    add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)  # can be scored normally again


def test_undo_walkover_rejects_a_match_that_was_not_a_walkover():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["A2"])

    with pytest.raises(HTTPException) as exc_info:
        undo_walkover(t.id, m.id, db)
    assert exc_info.value.status_code == 409


def play_group_by_walkover(db, t, teams, prefix):
    x1, x2, x3 = (teams[f"{prefix}{i}"] for i in (1, 2, 3))
    for a, b in [(x1, x2), (x1, x3), (x2, x3)]:
        m = new_match(db, t, a, b)
        set_walkover(t.id, m.id, WalkoverRequest(present="a"), db)


def test_walkovers_feed_the_semifinals_and_then_cannot_be_undone():
    db = make_db()
    t, teams = make_teams(db)
    play_group_by_walkover(db, t, teams, "A")
    play_group_by_walkover(db, t, teams, "B")
    when = GenerateSemifinalsRequest(semifinal_1_at=WHEN, semifinal_2_at=WHEN)

    sf1, sf2 = generate_semifinals(t.id, when, db)

    assert (sf1.team_a_id, sf1.team_b_id) == (teams["A1"].id, teams["B2"].id)
    group_match = next(
        m for m in db.query(type(sf1)).filter_by(stage="grupos") if m.walkover
    )
    with pytest.raises(HTTPException) as exc_info:
        undo_walkover(t.id, group_match.id, db)
    assert exc_info.value.status_code == 409


def test_a_knockout_walkover_can_be_undone_while_nothing_follows_it():
    db = make_db()
    t, teams = make_teams(db)
    m = new_match(db, t, teams["A1"], teams["B2"], stage="semifinal_1")
    set_walkover(t.id, m.id, WalkoverRequest(present="a"), db)

    undo_walkover(t.id, m.id, db)

    assert m.walkover is False


def test_migration_adds_walkover_defaulting_to_false(tmp_path, monkeypatch):
    old_engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old_engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE tournament_matches (id INTEGER PRIMARY KEY, is_final BOOLEAN NOT NULL)"
        )
        conn.exec_driver_sql("INSERT INTO tournament_matches (id, is_final) VALUES (1, 0)")
    monkeypatch.setattr(database, "engine", old_engine)

    database.add_missing_columns()

    with old_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT walkover FROM tournament_matches").scalar() == 0
