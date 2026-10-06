from datetime import date, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.models import Tournament, Team, TournamentMatch, TournamentSetResult
from app.schemas import (
    TournamentMatchCreate, TournamentMatchUpdate,
    GenerateSemifinalsRequest, GenerateFinalsRequest,
)
from app.tournament_matches import (
    create_match, update_match, get_standings,
    generate_semifinals, generate_finals, get_podium,
)

WHEN = datetime(2026, 11, 29, 9, 0)
SEMIS = GenerateSemifinalsRequest(semifinal_1_at=WHEN, semifinal_2_at=WHEN)
FINALS = GenerateFinalsRequest(third_place_at=WHEN, final_at=WHEN)


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_two_groups(db):
    """Teams A1..A3 in group A and B1..B3 in group B; returns (tournament, {code: team})."""
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    teams = {}
    for code in ("A1", "A2", "A3", "B1", "B2", "B3"):
        teams[code] = Team(tournament_id=t.id, code=code, group_name=code[0])
        db.add(teams[code])
    db.commit()
    return t, teams


def decide(db, match, winner="A"):
    """Close two sets so `match` is decided in favor of side A or B."""
    sets = [(15, 10), (15, 10)] if winner == "A" else [(10, 15), (10, 15)]
    for i, (pa, pb) in enumerate(sets, start=1):
        db.add(TournamentSetResult(match_id=match.id, set_number=i, points_a=pa, points_b=pb, closed=True))
    match.status = "encerrado"
    db.commit()


def play_group(db, t, teams, prefix, tie=False):
    """Round robin where X1 beats X2 and X3, and X2 beats X3 (or a 3-way cycle if tie)."""
    x1, x2, x3 = (teams[f"{prefix}{i}"] for i in (1, 2, 3))
    pairs = [(x1, x2, "A"), (x2, x3, "A"), (x3, x1, "A")] if tie else [(x1, x2, "A"), (x1, x3, "A"), (x2, x3, "A")]
    for a, b, winner in pairs:
        m = create_match(t.id, TournamentMatchCreate(team_a_id=a.id, team_b_id=b.id, scheduled_at=WHEN), db)
        decide(db, m, winner)


def build_finished_groups(db):
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A")
    play_group(db, t, teams, "B")
    return t, teams


def code_of(teams, team_id):
    return next(code for code, team in teams.items() if team.id == team_id)


def test_generate_semifinals_crosses_the_groups():
    db = make_db()
    t, teams = build_finished_groups(db)

    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)

    assert (sf1.stage, code_of(teams, sf1.team_a_id), code_of(teams, sf1.team_b_id)) == ("semifinal_1", "A1", "B2")
    assert (sf2.stage, code_of(teams, sf2.team_a_id), code_of(teams, sf2.team_b_id)) == ("semifinal_2", "B1", "A2")


def test_generate_semifinals_rejects_an_unfinished_group():
    db = make_db()
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A")

    with pytest.raises(HTTPException) as exc_info:
        generate_semifinals(t.id, SEMIS, db)
    assert exc_info.value.status_code == 400
    assert "grupo B" in exc_info.value.detail


def test_generate_semifinals_rejects_a_tie_for_the_last_spot():
    db = make_db()
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A", tie=True)
    play_group(db, t, teams, "B")

    with pytest.raises(HTTPException) as exc_info:
        generate_semifinals(t.id, SEMIS, db)
    assert exc_info.value.status_code == 400
    assert "Empate" in exc_info.value.detail


def test_generate_semifinals_rejects_when_they_already_exist():
    db = make_db()
    t, teams = build_finished_groups(db)
    generate_semifinals(t.id, SEMIS, db)

    with pytest.raises(HTTPException) as exc_info:
        generate_semifinals(t.id, SEMIS, db)
    assert exc_info.value.status_code == 409


def test_knockout_matches_do_not_count_toward_group_standings():
    db = make_db()
    t, teams = build_finished_groups(db)
    before = get_standings(t.id, db)
    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1)
    decide(db, sf2)

    assert get_standings(t.id, db) == before


def test_generate_finals_needs_both_semifinals_decided():
    db = make_db()
    t, teams = build_finished_groups(db)
    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1)

    with pytest.raises(HTTPException) as exc_info:
        generate_finals(t.id, FINALS, db)
    assert exc_info.value.status_code == 400


def test_generate_finals_pairs_winners_and_losers():
    db = make_db()
    t, teams = build_finished_groups(db)
    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)  # A1 x B2, B1 x A2
    decide(db, sf1, winner="A")  # A1 beats B2
    decide(db, sf2, winner="B")  # A2 beats B1

    third, final = generate_finals(t.id, FINALS, db)

    assert third.stage == "terceiro_lugar"
    assert {code_of(teams, third.team_a_id), code_of(teams, third.team_b_id)} == {"B2", "B1"}
    assert final.stage == "final" and final.is_final is True
    assert {code_of(teams, final.team_a_id), code_of(teams, final.team_b_id)} == {"A1", "A2"}


def test_generate_finals_rejects_when_they_already_exist():
    db = make_db()
    t, teams = build_finished_groups(db)
    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1)
    decide(db, sf2)
    generate_finals(t.id, FINALS, db)

    with pytest.raises(HTTPException) as exc_info:
        generate_finals(t.id, FINALS, db)
    assert exc_info.value.status_code == 409


def test_podium_fills_in_as_matches_get_decided():
    db = make_db()
    t, teams = build_finished_groups(db)
    assert get_podium(t.id, db) == {"champion": None, "runner_up": None, "third_place": None}

    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1, winner="A")  # A1 beats B2
    decide(db, sf2, winner="B")  # A2 beats B1
    third, final = generate_finals(t.id, FINALS, db)
    assert get_podium(t.id, db) == {"champion": None, "runner_up": None, "third_place": None}

    decide(db, final, winner="B")  # A2 beats A1
    assert get_podium(t.id, db) == {"champion": "A2", "runner_up": "A1", "third_place": None}

    decide(db, third, winner="A")  # B2 beats B1
    assert get_podium(t.id, db) == {"champion": "A2", "runner_up": "A1", "third_place": "B2"}


def test_create_match_rejects_unknown_stage():
    db = make_db()
    t, teams = make_two_groups(db)
    with pytest.raises(HTTPException) as exc_info:
        create_match(
            t.id,
            TournamentMatchCreate(team_a_id=teams["A1"].id, team_b_id=teams["B1"].id, scheduled_at=WHEN, stage="quartas"),
            db,
        )
    assert exc_info.value.status_code == 400


def test_a_knockout_stage_can_only_be_created_once():
    db = make_db()
    t, teams = make_two_groups(db)
    data = TournamentMatchCreate(
        team_a_id=teams["A1"].id, team_b_id=teams["B1"].id, scheduled_at=WHEN, stage="semifinal_1"
    )
    create_match(t.id, data, db)

    with pytest.raises(HTTPException) as exc_info:
        create_match(t.id, data, db)
    assert exc_info.value.status_code == 409


def test_group_stage_matches_can_repeat():
    db = make_db()
    t, teams = make_two_groups(db)
    data = TournamentMatchCreate(team_a_id=teams["A1"].id, team_b_id=teams["A2"].id, scheduled_at=WHEN)
    create_match(t.id, data, db)
    create_match(t.id, data, db)  # no error: only knockout stages are unique


def test_manual_final_keeps_is_final_in_sync():
    db = make_db()
    t, teams = make_two_groups(db)
    m = create_match(
        t.id,
        TournamentMatchCreate(team_a_id=teams["A1"].id, team_b_id=teams["B1"].id, scheduled_at=WHEN, stage="final"),
        db,
    )
    assert m.is_final is True

    update_match(t.id, m.id, TournamentMatchUpdate(stage="terceiro_lugar"), db)
    assert (m.stage, m.is_final) == ("terceiro_lugar", False)


def test_migration_backfills_stage_from_is_final(tmp_path, monkeypatch):
    old_engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old_engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE tournament_matches (id INTEGER PRIMARY KEY, is_final BOOLEAN NOT NULL)"
        )
        conn.exec_driver_sql("INSERT INTO tournament_matches (id, is_final) VALUES (1, 0), (2, 1)")
    monkeypatch.setattr(database, "engine", old_engine)

    database.add_missing_columns()

    with old_engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT id, stage FROM tournament_matches ORDER BY id").all()
    assert rows == [(1, "grupos"), (2, "final")]
