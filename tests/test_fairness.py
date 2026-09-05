from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Player, Session as GameSession, Attendance, Match, MatchPlayer
from app.services.fairness import history


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_never_selected_player_still_accumulates_outside_streak():
    # Regression: a player who checked in but was never once picked for a
    # match must still show a growing outside_streak - otherwise the
    # "force them in after waiting 2 matches" rule in selection.py can
    # never trigger for them, and they can be skipped forever.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()

    ignored = Player(name="Ignored", score=70, gender="X")
    others = [Player(name=f"P{i}", score=70, gender="X") for i in range(3)]
    db.add(ignored)
    db.add_all(others)
    db.flush()

    start = datetime(2026, 1, 1, 20, 0, 0)
    db.add(Attendance(
        session_id=session.id, player_id=ignored.id,
        status="arrived", arrival_order=1, arrived_at=start,
    ))
    for i, p in enumerate(others):
        db.add(Attendance(
            session_id=session.id, player_id=p.id,
            status="arrived", arrival_order=i + 2, arrived_at=start,
        ))
    db.commit()

    for match_no in range(1, 4):
        m = Match(session_id=session.id, number=match_no, status="finished")
        m.started_at = start + timedelta(minutes=(match_no - 1) * 30)
        m.ended_at = m.started_at + timedelta(minutes=28)
        db.add(m)
        db.flush()
        # "ignored" never plays; the other 3 always do.
        for p in others:
            db.add(MatchPlayer(
                match_id=m.id, player_id=p.id, team="A", role="starter",
                entered_at=m.started_at, exited_at=m.ended_at,
            ))
        db.commit()

    hist = history(db, session.id)
    assert hist[ignored.id]["outside_streak"] == 3
