import asyncio
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import database
from app.main import finish_match, generate_match, start_match
from app.models import Event, Match
from app.schemas import FinishRequest
from tests.test_opponent_mode import make_night


def running_match(db, session_id):
    match_id = asyncio.run(generate_match(session_id, db))["match_id"]
    asyncio.run(start_match(match_id, db))
    return match_id


def test_finish_records_the_winner_and_logs_it():
    db, sid = make_night([], n_players=12)
    match_id = running_match(db, sid)

    asyncio.run(finish_match(match_id, db, FinishRequest(winner="B")))

    m = db.get(Match, match_id)
    assert m.status == "finished" and m.winner == "B"
    ev = db.execute(select(Event).where(Event.match_id == match_id, Event.type == "match_finished")).scalar_one()
    assert json.loads(ev.payload) == {"winner": "B"}


def test_finish_without_a_winner_still_closes_the_match():
    # Forgetting to tap must never block ending a match or cost anyone a turn.
    db, sid = make_night([], n_players=12)
    match_id = running_match(db, sid)

    asyncio.run(finish_match(match_id, db))

    m = db.get(Match, match_id)
    assert m.status == "finished" and m.winner is None


def test_only_sides_a_and_b_are_valid_winners():
    with pytest.raises(ValidationError):
        FinishRequest(winner="C")


def test_add_missing_columns_gives_old_matches_a_winner_column(tmp_path, monkeypatch):
    old_engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old_engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE matches (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, number INTEGER NOT NULL)"
        )
        conn.exec_driver_sql("INSERT INTO matches VALUES (1, 1, 1)")
    monkeypatch.setattr(database, "engine", old_engine)

    database.add_missing_columns()

    with old_engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(matches)")}
        assert "winner" in cols
        assert conn.exec_driver_sql("SELECT winner FROM matches").scalar() is None
