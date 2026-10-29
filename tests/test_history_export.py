import asyncio
import csv
import io
from datetime import timedelta

from app.main import finish_match, session_history
from app.models import Match
from app.services.export import COLUMNS
from tests.test_opponent_mode import make_night
from tests.test_winner import running_match
from app.schemas import FinishRequest


def parse(db, sid):
    resp = session_history(sid, db)
    assert resp.media_type.startswith("text/csv")
    return list(csv.DictReader(io.StringIO(resp.body.decode())))


def test_history_lists_finished_matches_with_winner_and_team_sums():
    db, sid = make_night([], n_players=12)
    match_id = running_match(db, sid)
    m = db.get(Match, match_id)
    m.started_at -= timedelta(minutes=10)
    db.commit()
    asyncio.run(finish_match(match_id, db, FinishRequest(winner="A")))

    rows = parse(db, sid)
    assert list(rows[0].keys()) == COLUMNS
    assert len(rows) == 12
    assert {r["vencedor"] for r in rows} == {"A"} and {r["valida"] for r in rows} == {"sim"}
    assert {r["jogadores_titulares_time"] for r in rows} == {"6"}


def test_history_flags_a_match_that_ended_within_seconds_as_invalid():
    db, sid = make_night([], n_players=12)
    match_id = running_match(db, sid)
    asyncio.run(finish_match(match_id, db))

    rows = parse(db, sid)
    assert {r["valida"] for r in rows} == {"nao"}
    assert rows[0]["motivo_invalida"].startswith("durou")


def test_history_skips_matches_that_are_not_finished():
    db, sid = make_night([], n_players=12)
    running_match(db, sid)
    assert parse(db, sid) == []
