import asyncio
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import attendance
from app.models import Player, Session as GameSession, Attendance, Match, MatchPlayer
from app.schemas import AttendanceUpdate
from app.services.fairness import history


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def set_status(db, session_id, player_id, status):
    asyncio.run(attendance(session_id, player_id, AttendanceUpdate(status=status), db))


def make_session(db, names):
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    players = [Player(name=n, score=70, gender="X") for n in names]
    db.add_all(players)
    db.flush()
    for p in players:
        db.add(Attendance(session_id=session.id, player_id=p.id, status="expected"))
    db.commit()
    return session, players


def test_coming_back_after_leaving_clears_left_at():
    db = make_db()
    session, (p,) = make_session(db, ["Volta"])

    set_status(db, session.id, p.id, "arrived")
    set_status(db, session.id, p.id, "left")
    a = db.query(Attendance).filter_by(session_id=session.id, player_id=p.id).one()
    assert a.left_at is not None

    set_status(db, session.id, p.id, "arrived")
    db.refresh(a)
    assert a.left_at is None


def test_player_who_returned_still_accumulates_playing_streak():
    # Regression: someone marked "left" (even by accident) and then checked in
    # again kept a stale left_at, which made fairness.history() treat every
    # later match as outside their presence window. Both streaks froze at 0, so
    # selection.py never penalized them for having just played and picked them
    # for every single match.
    db = make_db()
    session, players = make_session(db, ["Volta", "A", "B", "C"])
    returner = players[0]

    for p in players:
        set_status(db, session.id, p.id, "arrived")
    set_status(db, session.id, returner.id, "left")
    set_status(db, session.id, returner.id, "arrived")

    start = datetime.utcnow() + timedelta(minutes=1)
    for number in (1, 2):
        m = Match(session_id=session.id, number=number, status="finished")
        m.started_at = start + timedelta(minutes=(number - 1) * 30)
        m.ended_at = m.started_at + timedelta(minutes=20)
        db.add(m)
        db.flush()
        for p in players:
            db.add(MatchPlayer(
                match_id=m.id, player_id=p.id, team="A", role="starter",
                entered_at=m.started_at, exited_at=m.ended_at,
            ))
        db.commit()

    hist = history(db, session.id)
    assert hist[returner.id]["playing_streak"] == 2


def test_marking_expected_undoes_a_wrong_check_in():
    # "expected" means the person is not here yet, so a check-in recorded by
    # mistake must not leave their arrival time and queue position behind -
    # those decide the opening line-up and the presence window used by fairness.
    db = make_db()
    session, (first, second) = make_session(db, ["Cedo", "Depois"])

    set_status(db, session.id, first.id, "arrived")
    set_status(db, session.id, second.id, "arrived")
    a = db.query(Attendance).filter_by(session_id=session.id, player_id=first.id).one()
    assert a.arrival_order == 1

    set_status(db, session.id, first.id, "expected")
    db.refresh(a)
    assert a.arrived_at is None
    assert a.arrival_order is None

    # Checking in for real later puts them at the back of the arrival queue.
    set_status(db, session.id, first.id, "arrived")
    db.refresh(a)
    assert a.arrival_order == 3
