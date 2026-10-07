import asyncio

import pytest
from fastapi import HTTPException
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import (
    create_session, generate_match, start_match, finish_match, session_state,
    release_fill_in, substitute,
)
from app.models import Player, Attendance, Match, MatchPlayer
from app.schemas import SessionCreate, GenerateRequest, SubstituteRequest

ARRIVAL = datetime(2026, 10, 7, 19, 0)


def make_night(opponents, n_players=14):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    players = [Player(name=f"P{i:02d}", score=70, gender="X") for i in range(n_players)]
    db.add_all(players)
    db.flush()
    created = asyncio.run(create_session(
        SessionCreate(name="Vôlei", player_ids=[p.id for p in players], opponents=opponents), db
    ))
    for order, att in enumerate(db.execute(select(Attendance)).scalars(), start=1):
        att.status, att.arrival_order, att.arrived_at = "arrived", order, ARRIVAL
    db.commit()
    return db, created["id"]


def play_one(db, session_id, **request):
    match_id = asyncio.run(generate_match(session_id, db, GenerateRequest(**request)))["match_id"]
    asyncio.run(start_match(match_id, db))
    asyncio.run(finish_match(match_id, db))
    return db.get(Match, match_id)


def test_against_a_team_drafts_only_six_players_on_one_side():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])

    match_id = asyncio.run(generate_match(sid, db))["match_id"]

    rows = db.execute(select(MatchPlayer).where(MatchPlayer.match_id == match_id)).scalars().all()
    assert len(rows) == 6
    assert {r.team for r in rows} == {"A"}
    assert db.get(Match, match_id).opponent == "Equipe Azul"


def test_the_opponent_alternates_each_match():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])

    opponents = [play_one(db, sid).opponent for _ in range(3)]

    assert opponents == ["Equipe Azul", "Equipe Verde", "Equipe Azul"]


def test_nobody_in_the_draft_plays_three_in_a_row():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])

    squads = []
    for _ in range(4):
        m = play_one(db, sid)
        squads.append({r.player_id for r in db.execute(select(MatchPlayer).where(MatchPlayer.match_id == m.id)).scalars()})

    for i in range(len(squads) - 2):
        assert not (squads[i] & squads[i + 1] & squads[i + 2])


def test_session_state_exposes_the_opponent():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])
    asyncio.run(generate_match(sid, db))

    state = session_state(sid, db)

    assert state["session"]["opponents"] == ["Equipe Azul", "Equipe Verde"]
    assert state["current_match"]["opponent"] == "Equipe Azul"
    assert len(state["current_match"]["teams"]["A"]) == 6
    assert state["current_match"]["teams"]["B"] == []


def test_without_opponents_it_is_still_twelve_players_in_two_teams():
    db, sid = make_night(None, n_players=14)

    match_id = asyncio.run(generate_match(sid, db))["match_id"]

    rows = db.execute(select(MatchPlayer).where(MatchPlayer.match_id == match_id)).scalars().all()
    assert len(rows) == 12
    assert {r.team for r in rows} == {"A", "B"}
    assert db.get(Match, match_id).opponent is None


def sides(db, match_id):
    rows = db.execute(select(MatchPlayer).where(MatchPlayer.match_id == match_id)).scalars().all()
    return (
        [r.player_id for r in rows if r.team == "A"],
        [r.player_id for r in rows if r.team == "B"],
    )


def test_the_first_match_can_be_against_either_team_and_the_rotation_follows():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])

    opponents = [
        play_one(db, sid, opponent="Equipe Verde").opponent,
        play_one(db, sid).opponent,
        play_one(db, sid).opponent,
    ]

    assert opponents == ["Equipe Verde", "Equipe Azul", "Equipe Verde"]


def test_session_state_suggests_the_team_after_the_last_match():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])
    assert session_state(sid, db)["session"]["next_opponent"] == "Equipe Azul"

    play_one(db, sid, opponent="Equipe Verde")

    assert session_state(sid, db)["session"]["next_opponent"] == "Equipe Azul"
    play_one(db, sid)
    assert session_state(sid, db)["session"]["next_opponent"] == "Equipe Verde"


def test_missing_people_are_drafted_to_fill_the_opponents_side():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])

    match_id = asyncio.run(generate_match(sid, db, GenerateRequest(opponent="Equipe Azul", missing=2)))["match_id"]

    ours, theirs = sides(db, match_id)
    assert len(ours) == 6 and len(theirs) == 2
    assert not set(ours) & set(theirs)
    state = session_state(sid, db)["current_match"]
    assert len(state["teams"]["A"]) == 6 and len(state["teams"]["B"]) == 2


def test_an_unknown_opponent_or_a_silly_missing_count_is_refused():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])

    for request in (GenerateRequest(opponent="Outro"), GenerateRequest(missing=6), GenerateRequest(missing=-1)):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(generate_match(sid, db, request))
        assert exc_info.value.status_code == 400
    assert db.query(Match).count() == 0


def test_the_fill_ins_still_follow_the_rest_rule():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])

    squads = []
    for _ in range(4):
        m = play_one(db, sid, missing=1)
        squads.append(set(sum(sides(db, m.id), [])))

    for i in range(len(squads) - 2):
        assert not (squads[i] & squads[i + 1] & squads[i + 2])


def test_releasing_a_fill_in_before_the_start_just_removes_them():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])
    match_id = asyncio.run(generate_match(sid, db, GenerateRequest(opponent="Equipe Azul", missing=2)))["match_id"]
    _, theirs = sides(db, match_id)

    asyncio.run(release_fill_in(match_id, theirs[0], db))

    ours, theirs_now = sides(db, match_id)
    assert len(ours) == 6 and theirs_now == [theirs[1]]


def test_releasing_a_fill_in_mid_match_calls_no_replacement_and_keeps_their_turn():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])
    match_id = asyncio.run(generate_match(sid, db, GenerateRequest(opponent="Equipe Azul", missing=1)))["match_id"]
    asyncio.run(start_match(match_id, db))
    _, (filler,) = sides(db, match_id)

    asyncio.run(release_fill_in(match_id, filler, db))

    state = session_state(sid, db)["current_match"]
    assert state["teams"]["B"] == []  # gone from the panel
    with pytest.raises(HTTPException) as exc_info:  # and no vacancy was opened
        asyncio.run(substitute(match_id, SubstituteRequest(player_id=filler), db))
    assert exc_info.value.status_code == 400
    asyncio.run(finish_match(match_id, db))
    by_id = {p["id"]: p for p in session_state(sid, db)["players"]}
    assert by_id[filler]["matches"] == 0  # filling in did not use up their turn


def test_only_the_opponents_side_can_be_released():
    db, sid = make_night(["Equipe Azul", "Equipe Verde"])
    match_id = asyncio.run(generate_match(sid, db, GenerateRequest(opponent="Equipe Azul", missing=1)))["match_id"]
    ours, _ = sides(db, match_id)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(release_fill_in(match_id, ours[0], db))
    assert exc_info.value.status_code == 404


def test_release_is_refused_in_a_normal_match():
    db, sid = make_night(None, n_players=14)
    match_id = asyncio.run(generate_match(sid, db))["match_id"]
    _, b = sides(db, match_id)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(release_fill_in(match_id, b[0], db))
    assert exc_info.value.status_code == 400
