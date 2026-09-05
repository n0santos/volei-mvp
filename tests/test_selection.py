from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Player, Session as GameSession, Attendance
from app.services.selection import select_players


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_module_imports():
    assert callable(select_players)


def test_tiebreak_among_equally_fair_players_is_randomized():
    # Three players with identical fairness history (all brand new, same
    # score/gender), differing only in arrival order. Choosing 2 of 3 means
    # one is always left out. In real life this group settles the tie with
    # a raffle ("adedonha") rather than always cutting the same person; the
    # app should behave the same way instead of always favoring whoever
    # arrived first.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()

    players = [Player(name=n, score=70, gender="X") for n in ("A", "B", "C")]
    db.add_all(players)
    db.flush()

    for order, p in enumerate(players, start=1):
        db.add(Attendance(
            session_id=session.id,
            player_id=p.id,
            status="arrived",
            arrival_order=order,
        ))
    db.commit()

    excluded_across_runs = set()
    for _ in range(40):
        chosen_ids = {p.id for p in select_players(db, session.id, target=2)}
        excluded = {p.id for p in players} - chosen_ids
        excluded_across_runs |= excluded

    assert len(excluded_across_runs) > 1, (
        "the same player was excluded every time — tie-break is not randomized"
    )
