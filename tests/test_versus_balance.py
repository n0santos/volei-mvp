import asyncio
from datetime import date, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import create_session, generate_match, start_match, finish_match
from app.models import Player, Tournament, Team, TeamPlayer, Attendance, MatchPlayer
from app.schemas import SessionCreate, GenerateRequest
from app.services.versus import opponent_average, best_split

ARRIVAL = datetime(2020, 1, 1)


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_team(db, code, scores, gender="X"):
    t = Tournament(name=f"T-{code}", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    team = Team(tournament_id=t.id, code=code)
    db.add(team)
    db.flush()
    for i, s in enumerate(scores):
        p = Player(name=f"{code}-{i}", score=s, gender=gender)
        db.add(p)
        db.flush()
        db.add(TeamPlayer(team_id=team.id, player_id=p.id))
    db.commit()
    return team


def night(db, scores, opponent="Equipe Azul"):
    """Players arrive in the order given; returns (session_id, players)."""
    players = [Player(name=f"N{i}", score=s, gender="X") for i, s in enumerate(scores)]
    db.add_all(players)
    db.flush()
    sid = asyncio.run(create_session(
        SessionCreate(name="n", player_ids=[p.id for p in players], opponents=[opponent]), db
    ))["id"]
    atts = {a.player_id: a for a in db.execute(select(Attendance)).scalars()}
    for order, p in enumerate(players, start=1):
        a = atts[p.id]
        a.status, a.arrival_order, a.arrived_at = "arrived", order, ARRIVAL
    db.commit()
    return sid, players


def play(db, sid, **request):
    match_id = asyncio.run(generate_match(sid, db, GenerateRequest(**request)))["match_id"]
    ours = {r.player_id for r in db.execute(
        select(MatchPlayer).where(MatchPlayer.match_id == match_id, MatchPlayer.team == "A")
    ).scalars()}
    asyncio.run(start_match(match_id, db))
    asyncio.run(finish_match(match_id, db))
    return ours


def test_opponent_average_uses_the_whole_roster_with_the_mens_offset():
    db = make_db()
    add_team(db, "Equipe Azul", [60, 70, 80], gender="M")  # +10 each

    assert opponent_average(db, "Equipe Azul") == 80
    assert opponent_average(db, "Ninguém") is None


def test_best_split_gives_the_fill_ins_that_even_the_sides_out():
    players = [Player(name=str(i), score=s, gender="X") for i, s in enumerate([40] * 6 + [70])]

    ours, fill_ins, gap = best_split(players, missing=1, opponent_avg=50)

    # fill-in 70: we are 40 vs their (50*5+70)/6 = 53.3 (gap 13.3);
    # fill-in 40: we are 45 vs their (50*5+40)/6 = 48.3 (gap 3.3) - better
    assert [p.score for p in fill_ins] == [40]
    assert 70 in [p.score for p in ours]
    assert round(gap, 2) == 3.33


def test_the_opening_squad_still_follows_arrival_order():
    db = make_db()
    add_team(db, "Equipe Azul", [40] * 7)
    # the two 90s arrived first: the group's rule opens the night with them
    sid, players = night(db, [90, 90] + [40] * 6)

    ours = play(db, sid)

    assert {p.score for p in players if p.id in ours} == {90, 40}
    assert {players[0].id, players[1].id} <= ours


def test_with_equal_turns_the_squad_closest_to_the_opponent_plays(monkeypatch):
    # the mechanism itself: no slack, so only the closest squad is free of cost
    monkeypatch.setattr("app.services.selection.BALANCE_TOLERANCE", 0.0)
    monkeypatch.setattr("app.services.selection.BALANCE_MARGIN", 0.0)
    db = make_db()
    add_team(db, "Equipe Azul", [40] * 7)
    # six 40s open the night; of the eight who wait, two are 90s
    sid, players = night(db, [40] * 6 + [90, 90] + [40] * 6)
    strong = {p.id for p in players if p.score == 90}

    play(db, sid)
    second = play(db, sid)

    assert not strong & second  # all eight waited equally: the 40s fit the opponent


def test_balance_never_outranks_a_turn_spent_waiting(monkeypatch):
    monkeypatch.setattr("app.services.selection.BALANCE_TOLERANCE", 0.0)
    monkeypatch.setattr("app.services.selection.BALANCE_MARGIN", 0.0)
    db = make_db()
    add_team(db, "Equipe Azul", [40] * 7)
    sid, players = night(db, [40] * 6 + [90, 90] + [40] * 6)
    strong = {p.id for p in players if p.score == 90}

    play(db, sid)
    play(db, sid)           # the 90s sit out again: balance prefers the 40s
    third = play(db, sid)   # two matches waiting force them in despite the gap

    assert strong <= third


def test_the_match_panel_gets_both_averages():
    from app.main import session_state

    db = make_db()
    add_team(db, "Equipe Azul", [60] * 7)
    sid, players = night(db, [60] * 8)
    asyncio.run(generate_match(sid, db, GenerateRequest()))

    balance = session_state(sid, db)["current_match"]["balance"]

    assert balance == {"ours_avg": 60, "opponent_avg": 60}


def test_with_the_default_slack_everyone_plays_the_same_number_of_matches():
    # fairness first: over a night nobody plays more than one match above anyone else
    db = make_db()
    add_team(db, "Equipe Azul", [40] * 7)
    sid, players = night(db, [90, 90, 85, 40, 40, 40, 40, 40, 40, 40, 40, 40, 40])

    counts = {p.id: 0 for p in players}
    for _ in range(8):
        for pid in play(db, sid):
            counts[pid] += 1

    assert max(counts.values()) - min(counts.values()) <= 1
