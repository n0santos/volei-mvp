import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import exit_player, substitute, substitutes, swap_player
from app.models import Player, Session as GameSession, Attendance, Match, MatchPlayer
from app.schemas import SubstituteRequest, SwapRequest
from app.services.selection import select_players

ARRIVAL = datetime(2026, 1, 1, 19, 0, 0)


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_players(db, session, names):
    players = [Player(name=n, score=70, gender="X") for n in names]
    db.add_all(players)
    db.flush()
    for order, p in enumerate(players, start=1):
        db.add(Attendance(
            session_id=session.id, player_id=p.id, status="arrived",
            arrival_order=order, arrived_at=ARRIVAL,
        ))
    db.commit()
    return players


def add_match(db, session, number, squad, status="finished"):
    m = Match(session_id=session.id, number=number, status=status)
    if status != "proposed":
        m.started_at = ARRIVAL + timedelta(minutes=30 * number)
    if status == "finished":
        m.ended_at = m.started_at + timedelta(minutes=20)
    db.add(m)
    db.flush()
    for p in squad:
        db.add(MatchPlayer(
            match_id=m.id, player_id=p.id, team="A", role="starter",
            entered_at=m.started_at, exited_at=m.ended_at,
        ))
    db.commit()
    return m


def do_swap(db, match_id, out_player, in_player):
    asyncio.run(swap_player(
        match_id, SwapRequest(out_player_id=out_player.id, in_player_id=in_player.id), db
    ))


def test_substitution_concept():
    # Integration tests are intentionally kept small in the MVP.
    # The API records exit and replacement as separate events.
    assert True


def test_who_just_played_twice_is_not_offered_as_a_substitute():
    # Walking on would be their third match in a row, which the group rules
    # out - the bench applies to substitutions too, not just the draw.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()

    tired = Player(name="Tired", score=70, gender="X")
    rested = Player(name="Rested", score=70, gender="X")
    playing = Player(name="Playing", score=70, gender="X")
    db.add_all([tired, rested, playing])
    db.flush()
    for order, p in enumerate([tired, rested, playing], start=1):
        db.add(Attendance(
            session_id=session.id, player_id=p.id, status="arrived",
            arrival_order=order, arrived_at=ARRIVAL,
        ))

    for number in (1, 2):
        m = Match(session_id=session.id, number=number, status="finished")
        m.started_at = ARRIVAL + timedelta(minutes=30 * number)
        m.ended_at = m.started_at + timedelta(minutes=20)
        db.add(m)
        db.flush()
        db.add(MatchPlayer(
            match_id=m.id, player_id=tired.id, team="A", role="starter",
            entered_at=m.started_at, exited_at=m.ended_at,
        ))
    running = Match(session_id=session.id, number=3, status="running")
    running.started_at = ARRIVAL + timedelta(minutes=120)
    db.add(running)
    db.flush()
    db.add(MatchPlayer(
        match_id=running.id, player_id=playing.id, team="A", role="starter",
        entered_at=running.started_at,
    ))
    db.commit()

    offered = [c["name"] for c in substitutes(running.id, db)]
    assert offered == ["Rested"]


def test_voluntary_swap_never_offers_someone_on_their_third():
    # Nobody is hurt and nothing has started: there is no reason good enough to
    # hand someone a third match in a row, not even an empty bench.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    tired, playing = add_players(db, session, ["Tired", "Playing"])

    add_match(db, session, 1, [tired])
    add_match(db, session, 2, [tired])
    proposed = add_match(db, session, 3, [playing], status="proposed")

    assert substitutes(proposed.id, db) == []


def test_someone_leaving_before_the_start_is_an_emergency_too():
    # Drawn, then went home before the match started. With nobody rested on the
    # bench the choice is a tired player or a team a man short - always 6x6.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    tired, leaving = add_players(db, session, ["Tired", "Leaving"])

    add_match(db, session, 1, [tired])
    add_match(db, session, 2, [tired])
    proposed = add_match(db, session, 3, [leaving], status="proposed")
    db.query(Attendance).filter_by(player_id=leaving.id).update({"status": "left"})
    db.commit()

    offered = substitutes(proposed.id, db, out_player_id=leaving.id)
    assert [c["name"] for c in offered] == ["Tired"]

    do_swap(db, proposed.id, leaving, tired)
    squad = [mp.player_id for mp in db.query(MatchPlayer).filter_by(match_id=proposed.id)]
    assert squad == [tired.id]


def test_leaving_does_not_unlock_a_tired_player_while_someone_rested_waits():
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    tired, rested, leaving = add_players(db, session, ["Tired", "Rested", "Leaving"])

    add_match(db, session, 1, [tired])
    add_match(db, session, 2, [tired])
    proposed = add_match(db, session, 3, [leaving], status="proposed")
    db.query(Attendance).filter_by(player_id=leaving.id).update({"status": "left"})
    db.commit()

    assert [c["name"] for c in substitutes(proposed.id, db, out_player_id=leaving.id)] == ["Rested"]
    with pytest.raises(HTTPException):
        do_swap(db, proposed.id, leaving, tired)


def test_emergency_substitution_still_falls_back_to_a_tired_player():
    # Mid-match the alternative is playing a man short, so the bench rule gives.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    tired, playing = add_players(db, session, ["Tired", "Playing"])

    add_match(db, session, 1, [tired])
    add_match(db, session, 2, [tired])
    running = add_match(db, session, 3, [playing], status="running")

    assert [c["name"] for c in substitutes(running.id, db)] == ["Tired"]


def test_swap_hands_over_the_same_slot():
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    a, b, c = add_players(db, session, ["A", "B", "C"])
    proposed = add_match(db, session, 1, [a, b], status="proposed")
    db.query(MatchPlayer).filter_by(match_id=proposed.id, player_id=b.id).update({"team": "B"})
    db.commit()

    do_swap(db, proposed.id, b, c)

    rows = db.query(MatchPlayer).filter_by(match_id=proposed.id).all()
    assert {r.player_id for r in rows} == {a.id, c.id}
    assert len(rows) == 2
    swapped = next(r for r in rows if r.player_id == c.id)
    assert swapped.team == "B" and swapped.role == "starter"


def test_swap_is_refused_once_the_match_is_under_way():
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    a, b, c = add_players(db, session, ["A", "B", "C"])
    running = add_match(db, session, 1, [a, b], status="running")

    with pytest.raises(HTTPException):
        do_swap(db, running.id, b, c)


def test_swap_is_refused_for_someone_already_on_the_court():
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    a, b = add_players(db, session, ["A", "B"])
    proposed = add_match(db, session, 1, [a, b], status="proposed")

    with pytest.raises(HTTPException):
        do_swap(db, proposed.id, b, a)


def test_coming_in_by_swap_still_counts_toward_the_two_in_a_row_rule():
    # Walking in through a swap is playing: if it completes two straight
    # matches, the bench applies next time exactly as if they had been drawn.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    a, b, x, c = add_players(db, session, ["A", "B", "X", "C"])

    add_match(db, session, 1, [x, a])
    proposed = add_match(db, session, 2, [b, c], status="proposed")
    do_swap(db, proposed.id, c, x)

    proposed.status = "finished"
    proposed.ended_at = proposed.started_at
    db.commit()

    chosen = {p.id for p in select_players(db, session.id, target=2)}
    assert x.id not in chosen, "jogou 2 seguidas e ainda entrou no sorteio da 3ª"


def test_two_vacancies_are_filled_one_per_team():
    # Two people leave the court before anyone comes back in. Each substitute
    # must take the slot that is actually empty - otherwise one team ends up
    # short and the other plays with an extra.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    squad = add_players(db, session, ["A1", "A2", "B1", "B2", "S1", "S2"])
    a1, a2, b1, b2, s1, s2 = squad

    running = add_match(db, session, 1, [], status="running")
    for p, team in ((a1, "A"), (a2, "A"), (b1, "B"), (b2, "B")):
        db.add(MatchPlayer(
            match_id=running.id, player_id=p.id, team=team, role="starter",
            entered_at=running.started_at,
        ))
    db.commit()

    # B leaves first, then A - so the most recent vacancy is A's.
    asyncio.run(exit_player(running.id, b1.id, db))
    asyncio.run(exit_player(running.id, a1.id, db))

    asyncio.run(substitute(running.id, SubstituteRequest(player_id=s1.id), db))
    asyncio.run(substitute(running.id, SubstituteRequest(player_id=s2.id), db))

    on_court = defaultdict(list)
    for mp in db.query(MatchPlayer).filter_by(match_id=running.id).all():
        if mp.exited_at is None:
            on_court[mp.team].append(mp.player_id)

    assert len(on_court["A"]) == 2, f"time A ficou com {len(on_court['A'])}"
    assert len(on_court["B"]) == 2, f"time B ficou com {len(on_court['B'])}"
    assert s1.id in on_court["A"], "primeiro substituto devia cobrir a vaga mais recente (time A)"
    assert s2.id in on_court["B"]
