"""A match only moves forward: proposed -> running -> finished.

On 16/11 a phone with a stale screen sent "start" for match 1 seconds after it
was finished; the server reopened it, and every later draft failed with "Já
existe uma partida aberta" while the screen showed no open match.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.main import finish_match, generate_match, session_state, start_match
from app.models import Match
from tests.test_opponent_mode import make_night


def draft(db, sid):
    return asyncio.run(generate_match(sid, db))["match_id"]


def test_start_after_finish_does_not_reopen_the_match():
    db, sid = make_night([], n_players=14)
    mid = draft(db, sid)
    asyncio.run(start_match(mid, db))
    asyncio.run(finish_match(mid, db))
    ended = db.get(Match, mid).ended_at

    with pytest.raises(HTTPException) as e:
        asyncio.run(start_match(mid, db))

    assert e.value.status_code == 409
    m = db.get(Match, mid)
    assert m.status == "finished" and m.ended_at == ended
    draft(db, sid)  # the night goes on


def test_double_start_keeps_the_original_start_time():
    db, sid = make_night([], n_players=14)
    mid = draft(db, sid)
    asyncio.run(start_match(mid, db))
    started = db.get(Match, mid).started_at

    with pytest.raises(HTTPException) as e:
        asyncio.run(start_match(mid, db))

    assert e.value.status_code == 409
    assert db.get(Match, mid).started_at == started


def test_finish_twice_keeps_the_first_result():
    db, sid = make_night([], n_players=14)
    mid = draft(db, sid)
    asyncio.run(start_match(mid, db))
    asyncio.run(finish_match(mid, db))
    ended = db.get(Match, mid).ended_at

    with pytest.raises(HTTPException) as e:
        asyncio.run(finish_match(mid, db))

    assert e.value.status_code == 409
    assert db.get(Match, mid).ended_at == ended


def test_cannot_finish_a_match_that_never_started():
    db, sid = make_night([], n_players=14)
    mid = draft(db, sid)

    with pytest.raises(HTTPException) as e:
        asyncio.run(finish_match(mid, db))

    assert e.value.status_code == 409
    assert db.get(Match, mid).status == "proposed"


def test_screen_shows_an_open_match_even_if_a_later_one_exists():
    # Old databases may already hold this state; the screen must show the match
    # that blocks the draft instead of hiding it.
    db, sid = make_night([], n_players=14)
    first = draft(db, sid)
    asyncio.run(start_match(first, db))
    asyncio.run(finish_match(first, db))
    second = draft(db, sid)
    asyncio.run(start_match(second, db))
    asyncio.run(finish_match(second, db))
    db.get(Match, first).status = "running"
    db.commit()

    assert session_state(sid, db)["current_match"]["id"] == first
