from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.models import Tournament, Team, TournamentSetResult
from app.schemas import (
    TournamentMatchCreate, TournamentMatchUpdate,
    GenerateSemifinalsRequest, GenerateFinalRequest, DrawRequest,
)
from app.services.tournament_engine import DRAW_FIXTURES
from app.tournament_matches import (
    create_match, update_match, get_standings, register_draw,
    generate_semifinals, generate_final, get_podium,
)

WHEN = datetime(2026, 11, 29, 9, 0)
SEMIS = GenerateSemifinalsRequest(semifinal_1_at=WHEN, semifinal_2_at=WHEN)
FINAL = GenerateFinalRequest(final_at=WHEN)
TIMES = [datetime(2026, 11, 28, 13, 0) + timedelta(minutes=50 * i) for i in range(len(DRAW_FIXTURES))]

# Winners (side A/B) of the nine games in fixture order. Wins per slot A..F =
# 2,2,2,2,1,0: a clean cut between 4th and 5th place.
FOUR_QUALIFY = "AAAAAABAA"


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_six(db):
    """Six teams T1..T6; returns (tournament, [teams])."""
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    teams = [Team(tournament_id=t.id, code=f"T{i}") for i in range(1, 7)]
    db.add_all(teams)
    db.commit()
    return t, teams


def draw(db, t, teams):
    """Register the draw with slots A..F = teams in order; returns (slots, matches)."""
    slots = dict(zip("ABCDEF", (team.id for team in teams)))
    return slots, register_draw(t.id, DrawRequest(slots=slots, times=TIMES), db)


def decide(db, match, winner="A"):
    """Close two sets so `match` is decided in favor of side A or B."""
    sets = [(15, 10), (15, 10)] if winner == "A" else [(10, 15), (10, 15)]
    for i, (pa, pb) in enumerate(sets, start=1):
        db.add(TournamentSetResult(match_id=match.id, set_number=i, points_a=pa, points_b=pb, closed=True))
    match.status = "encerrado"
    db.commit()


def play_all(db, matches, winners=FOUR_QUALIFY):
    for m, w in zip(matches, winners):
        decide(db, m, w)


def build_finished_table(db):
    t, teams = make_six(db)
    slots, matches = draw(db, t, teams)
    play_all(db, matches)
    return t, teams


def code_of(teams, team_id):
    return next(team.code for team in teams if team.id == team_id)


def table_order(db, t):
    return [row["team"] for row in get_standings(t.id, db)["rows"]]


def test_semifinals_are_first_vs_fourth_and_second_vs_third():
    db = make_db()
    t, teams = build_finished_table(db)
    order = table_order(db, t)

    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)

    assert (sf1.stage, code_of(teams, sf1.team_a_id), code_of(teams, sf1.team_b_id)) == ("semifinal_1", order[0], order[3])
    assert (sf2.stage, code_of(teams, sf2.team_a_id), code_of(teams, sf2.team_b_id)) == ("semifinal_2", order[1], order[2])


def test_semifinals_wait_for_the_whole_table():
    db = make_db()
    t, teams = make_six(db)
    _, matches = draw(db, t, teams)
    play_all(db, matches[:8], FOUR_QUALIFY[:8])

    with pytest.raises(HTTPException) as exc_info:
        generate_semifinals(t.id, SEMIS, db)
    assert exc_info.value.status_code == 400


def test_semifinals_reject_a_tie_for_the_last_spot():
    db = make_db()
    t, teams = make_six(db)
    _, matches = draw(db, t, teams)
    play_all(db, matches, "A" * 9)  # wins 3,2,2,1,1,0: 4th and 5th are level

    with pytest.raises(HTTPException) as exc_info:
        generate_semifinals(t.id, SEMIS, db)
    assert exc_info.value.status_code == 400
    assert "Empate" in exc_info.value.detail


def test_semifinals_reject_when_they_already_exist():
    db = make_db()
    t, teams = build_finished_table(db)
    generate_semifinals(t.id, SEMIS, db)

    with pytest.raises(HTTPException) as exc_info:
        generate_semifinals(t.id, SEMIS, db)
    assert exc_info.value.status_code == 409


def test_knockout_matches_do_not_count_toward_the_table():
    db = make_db()
    t, teams = build_finished_table(db)
    before = get_standings(t.id, db)
    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1)
    decide(db, sf2)

    assert get_standings(t.id, db) == before


def test_final_needs_both_semifinals_decided():
    db = make_db()
    t, teams = build_finished_table(db)
    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1)

    with pytest.raises(HTTPException) as exc_info:
        generate_final(t.id, FINAL, db)
    assert exc_info.value.status_code == 400


def test_final_pairs_the_semifinal_winners_and_there_is_no_third_place_game():
    db = make_db()
    t, teams = build_finished_table(db)
    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1, winner="A")
    decide(db, sf2, winner="B")

    final = generate_final(t.id, FINAL, db)

    assert final.stage == "final" and final.is_final is True
    assert (final.team_a_id, final.team_b_id) == (sf1.team_a_id, sf2.team_b_id)


def test_final_rejects_when_it_already_exists():
    db = make_db()
    t, teams = build_finished_table(db)
    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1)
    decide(db, sf2)
    generate_final(t.id, FINAL, db)

    with pytest.raises(HTTPException) as exc_info:
        generate_final(t.id, FINAL, db)
    assert exc_info.value.status_code == 409


def test_podium_fills_in_as_the_final_gets_decided():
    db = make_db()
    t, teams = build_finished_table(db)
    assert get_podium(t.id, db) == {"champion": None, "runner_up": None}

    sf1, sf2 = generate_semifinals(t.id, SEMIS, db)
    decide(db, sf1, winner="A")
    decide(db, sf2, winner="B")
    final = generate_final(t.id, FINAL, db)
    assert get_podium(t.id, db) == {"champion": None, "runner_up": None}

    decide(db, final, winner="B")
    assert get_podium(t.id, db) == {
        "champion": code_of(teams, sf2.team_b_id),
        "runner_up": code_of(teams, sf1.team_a_id),
    }


def test_create_match_rejects_unknown_stage():
    db = make_db()
    t, teams = make_six(db)
    for stage in ("quartas", "terceiro_lugar"):
        with pytest.raises(HTTPException) as exc_info:
            create_match(
                t.id,
                TournamentMatchCreate(team_a_id=teams[0].id, team_b_id=teams[1].id, scheduled_at=WHEN, stage=stage),
                db,
            )
        assert exc_info.value.status_code == 400


def test_a_knockout_stage_can_only_be_created_once():
    db = make_db()
    t, teams = make_six(db)
    data = TournamentMatchCreate(
        team_a_id=teams[0].id, team_b_id=teams[1].id, scheduled_at=WHEN, stage="semifinal_1"
    )
    create_match(t.id, data, db)

    with pytest.raises(HTTPException) as exc_info:
        create_match(t.id, data, db)
    assert exc_info.value.status_code == 409


def test_qualifying_matches_can_repeat():
    db = make_db()
    t, teams = make_six(db)
    data = TournamentMatchCreate(team_a_id=teams[0].id, team_b_id=teams[1].id, scheduled_at=WHEN)
    create_match(t.id, data, db)
    create_match(t.id, data, db)  # no error: only knockout stages are unique


def test_manual_final_keeps_is_final_in_sync():
    db = make_db()
    t, teams = make_six(db)
    m = create_match(
        t.id,
        TournamentMatchCreate(team_a_id=teams[0].id, team_b_id=teams[1].id, scheduled_at=WHEN, stage="final"),
        db,
    )
    assert m.is_final is True

    update_match(t.id, m.id, TournamentMatchUpdate(stage="semifinal_1"), db)
    assert (m.stage, m.is_final) == ("semifinal_1", False)


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
