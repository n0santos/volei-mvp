import asyncio
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import finish_match
from app.models import Player, Session as GameSession, Match, MatchPlayer
from app.schemas import FinishRequest
from app.services.ranking import ranking

START = datetime(2026, 1, 1, 19, 0, 0)


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    session = GameSession(name="test")
    db.add(session)
    db.commit()
    return db, session


def add_players(db, names):
    players = [Player(name=n, score=70, gender="X") for n in names]
    db.add_all(players)
    db.commit()
    return players


def play(db, session, number, team_a, team_b, winner, subs_a=()):
    m = Match(session_id=session.id, number=number, status="running",
              started_at=START + timedelta(minutes=20 * number))
    db.add(m)
    db.flush()
    for team, squad, role in (("A", team_a, "starter"), ("B", team_b, "starter"), ("A", subs_a, "substitute")):
        for p in squad:
            db.add(MatchPlayer(match_id=m.id, player_id=p.id, team=team, role=role, entered_at=m.started_at))
    db.commit()
    asyncio.run(finish_match(m.id, FinishRequest(winner=winner), db))
    return m


def test_orders_by_win_rate_not_by_total_wins():
    db, session = make_db()
    early, late, loser = add_players(db, ["Early", "Late", "Loser"])

    # Early played every match and piled up wins early on, but lost the rest.
    play(db, session, 1, [early], [loser], "A")
    play(db, session, 2, [early], [loser], "A")
    play(db, session, 3, [loser], [early], "A")
    play(db, session, 4, [early, late], [loser], "B")
    play(db, session, 5, [late], [early], "A")

    rows = ranking(db, session.id)
    assert [(r["name"], r["wins"], r["played"]) for r in rows] == [
        ("Loser", 2, 4),
        ("Late", 1, 2),
        ("Early", 2, 5),
    ]


def test_win_rate_ranking_with_ties_broken_by_wins():
    db, session = make_db()
    a, b, c = add_players(db, ["A", "B", "C"])

    play(db, session, 1, [a, b], [c], "A")
    play(db, session, 2, [a], [b, c], "A")
    play(db, session, 3, [c], [b], "A")

    rows = {r["name"]: r for r in ranking(db, session.id)}
    assert (rows["A"]["wins"], rows["A"]["played"]) == (2, 2)
    assert (rows["B"]["wins"], rows["B"]["played"]) == (1, 3)
    assert (rows["C"]["wins"], rows["C"]["played"]) == (1, 3)
    assert [r["name"] for r in ranking(db, session.id)][0] == "A"


def test_undecided_matches_and_substitutes_do_not_count():
    db, session = make_db()
    starter, sub, other = add_players(db, ["Starter", "Sub", "Other"])

    play(db, session, 1, [starter], [other], "A", subs_a=[sub])
    play(db, session, 2, [starter], [other], None)

    rows = {r["name"]: r for r in ranking(db, session.id)}
    assert (rows["Starter"]["wins"], rows["Starter"]["played"]) == (1, 1)
    assert "Sub" not in rows


def test_finish_records_the_winner():
    db, session = make_db()
    x, y = add_players(db, ["X", "Y"])
    m = play(db, session, 1, [x], [y], "B")
    assert db.get(Match, m.id).winner == "B"
