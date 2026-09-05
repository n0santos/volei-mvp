from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Player, Session as GameSession, Attendance, Match
from app.services.selection import select_players


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_module_imports():
    assert callable(select_players)


def test_first_match_of_the_day_prefers_earliest_arrivals():
    # Before anyone has played, everyone is tied at zero wait/played/minutes.
    # The group's convention is first-come-first-served for the opening
    # match, not a lottery - whoever checked in earliest should get in.
    db = make_db()
    session = GameSession(name="test")
    db.add(session)
    db.flush()

    players = [Player(name=n, score=70, gender="X") for n in ("A", "B", "C", "D")]
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

    chosen_ids = {p.id for p in select_players(db, session.id, target=2)}
    earliest_two = {players[0].id, players[1].id}
    assert chosen_ids == earliest_two


def test_tiebreak_after_first_match_is_randomized():
    # Once matches have started, ties between equally-fair players (same
    # wait/playing history) are settled by a random draw each time - like
    # the group's usual "adedonha" - rather than always favoring whoever
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
    # A finished match already happened this session, so we're past the
    # "first match of the day" case.
    db.add(Match(session_id=session.id, number=1, status="finished"))
    db.commit()

    excluded_across_runs = set()
    for _ in range(40):
        chosen_ids = {p.id for p in select_players(db, session.id, target=2)}
        excluded = {p.id for p in players} - chosen_ids
        excluded_across_runs |= excluded

    assert len(excluded_across_runs) > 1, (
        "the same player was excluded every time — tie-break is not randomized"
    )
