from datetime import datetime

import pytest
from fastapi import HTTPException

from app.models import Team, TournamentMatch
from app.schemas import DrawRequest
from app.services.tournament_engine import DRAW_FIXTURES
from app.tournament_matches import register_draw, get_standings
from test_tournament_knockout import (
    FOUR_QUALIFY, TIMES, decide, draw, make_db, make_six, play_all,
)


def test_draw_creates_the_nine_fixtures_in_order():
    db = make_db()
    t, teams = make_six(db)
    slots, matches = draw(db, t, teams)

    assert [(m.team_a_id, m.team_b_id) for m in matches] == [(slots[a], slots[b]) for a, b in DRAW_FIXTURES]
    assert [m.scheduled_at for m in matches] == TIMES
    assert all(m.stage == "grupos" for m in matches)
    # every team plays exactly three games
    played = [m.team_a_id for m in matches] + [m.team_b_id for m in matches]
    assert all(played.count(team.id) == 3 for team in teams)


def test_draw_replaces_unplayed_group_games():
    db = make_db()
    t, teams = make_six(db)
    draw(db, t, teams)
    draw(db, t, list(reversed(teams)))

    assert db.query(TournamentMatch).count() == 9


def test_draw_refuses_when_a_game_already_has_a_result():
    db = make_db()
    t, teams = make_six(db)
    _, matches = draw(db, t, teams)
    decide(db, matches[0], "A")

    with pytest.raises(HTTPException) as exc_info:
        draw(db, t, teams)
    assert exc_info.value.status_code == 409


def test_draw_validates_slots_times_and_team_count():
    db = make_db()
    t, teams = make_six(db)
    ids = [team.id for team in teams]

    bad = [
        DrawRequest(slots=dict(zip("ABCDE", ids)), times=TIMES),                    # missing slot
        DrawRequest(slots=dict(zip("ABCDEF", ids[:5] + [ids[0]])), times=TIMES),    # repeated team
        DrawRequest(slots=dict(zip("ABCDEF", ids)), times=TIMES[:8]),               # missing time
    ]
    for request in bad:
        with pytest.raises(HTTPException) as exc_info:
            register_draw(t.id, request, db)
        assert exc_info.value.status_code == 400

    db.add(Team(tournament_id=t.id, code="T7"))
    db.commit()
    with pytest.raises(HTTPException) as exc_info:
        register_draw(t.id, DrawRequest(slots=dict(zip("ABCDEF", ids)), times=TIMES), db)
    assert exc_info.value.status_code == 409


def test_table_is_only_complete_after_all_nine_games():
    db = make_db()
    t, teams = make_six(db)
    _, matches = draw(db, t, teams)

    play_all(db, matches[:8], FOUR_QUALIFY[:8])
    table = get_standings(t.id, db)
    assert table["complete"] is False
    assert not any(row["qualified"] for row in table["rows"])

    decide(db, matches[8], FOUR_QUALIFY[8])
    table = get_standings(t.id, db)
    assert table["complete"] is True
    assert sum(row["qualified"] for row in table["rows"]) == 4
