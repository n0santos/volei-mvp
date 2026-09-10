from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Player, Session as GameSession, Attendance, Match, MatchPlayer
from app.services.fairness import history
from app.services.selection import select_players

ARRIVAL = datetime(2026, 1, 1, 19, 0, 0)


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_session(db, count):
    session = GameSession(name="test")
    db.add(session)
    db.flush()
    players = [Player(name=f"P{i:02d}", score=70, gender="X") for i in range(count)]
    db.add_all(players)
    db.flush()
    for order, p in enumerate(players, start=1):
        db.add(Attendance(
            session_id=session.id, player_id=p.id, status="arrived",
            arrival_order=order, arrived_at=ARRIVAL,
        ))
    db.commit()
    return session, players


def play_match(db, session, squad, number, role="starter"):
    m = Match(session_id=session.id, number=number, status="finished")
    m.started_at = ARRIVAL + timedelta(minutes=30 * number)
    m.ended_at = m.started_at + timedelta(minutes=20)
    db.add(m)
    db.flush()
    for p in squad:
        db.add(MatchPlayer(
            match_id=m.id, player_id=p.id, team="A", role=role,
            entered_at=m.started_at, exited_at=m.ended_at,
        ))
    db.commit()
    return m


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


def test_nobody_ever_plays_three_matches_in_a_row():
    # The group's rule: two in a row is unavoidable with a full court, but a
    # third is never allowed - whoever just played twice sits the next one out.
    db = make_db()
    session, players = make_session(db, 22)

    played_in = []
    for number in range(1, 11):
        squad = select_players(db, session.id, target=12)
        play_match(db, session, squad, number)
        played_in.append({p.id for p in squad})

    for first, second, third in zip(played_in, played_in[1:], played_in[2:]):
        three_in_a_row = first & second & third
        assert not three_in_a_row, f"jogaram 3 seguidas: {three_in_a_row}"


def test_playing_least_never_buys_a_third_match_in_a_row():
    # Someone who arrived late has played few matches all night, so the
    # "whoever played least goes first" rule points straight at them - but they
    # have just played twice in a row, and the bench wins that argument.
    db = make_db()
    session, players = make_session(db, 3)
    latecomer, *regulars = players

    for number in range(1, 7):
        play_match(db, session, regulars, number)
    play_match(db, session, [latecomer], 7)
    play_match(db, session, players, 8)

    hist = history(db, session.id)
    assert hist[latecomer.id]["playing_streak"] == 2
    assert hist[latecomer.id]["matches"] < hist[regulars[0].id]["matches"]

    chosen_ids = {p.id for p in select_players(db, session.id, target=2)}
    assert latecomer.id not in chosen_ids, "entrou pra 3ª seguida por ter jogado pouco"
    assert chosen_ids == {p.id for p in regulars}


def test_block_is_relaxed_only_as_far_as_the_numbers_demand():
    # With fewer than 18 present the rule stops fitting on a 6x6 court, so the
    # block is lifted for exactly as many people as the court still needs -
    # never more.
    db = make_db()
    session, players = make_session(db, 15)

    play_match(db, session, players[:12], 1)
    play_match(db, session, players[3:], 2)

    hist = history(db, session.id)
    blocked = {p.id for p in players if hist[p.id]["playing_streak"] >= 2}
    assert len(blocked) == 9

    chosen = select_players(db, session.id, target=12)
    assert len(chosen) == 12

    # Only 6 of the 15 are free to play, so the court needs 6 of the 9 blocked.
    released = {p.id for p in chosen} & blocked
    assert len(released) == 6, "liberou mais gente bloqueada do que o necessário"
    assert {p.id for p in chosen} - blocked == {p.id for p in players} - blocked


def test_remaining_slots_go_to_whoever_played_least():
    # When people who just played have to fill the leftover slots, the draw
    # runs among those with the fewest matches on the night - not among all of
    # them equally.
    db = make_db()
    session, players = make_session(db, 13)

    play_match(db, session, players[:6], 1)      # players 0-5 get an extra match
    play_match(db, session, [players[12]], 2)    # breaks everyone else's streak
    play_match(db, session, players[:12], 3)     # 0-11 all sit on one straight match

    hist = history(db, session.id)
    assert {hist[p.id]["matches"] for p in players[:6]} == {2}
    assert {hist[p.id]["matches"] for p in players[6:12]} == {1}

    chosen_ids = {p.id for p in select_players(db, session.id, target=12)}

    assert players[12].id in chosen_ids, "quem estava esperando tem que entrar"
    for p in players[6:12]:
        assert p.id in chosen_ids, "quem jogou menos tem que entrar antes"
    left_out = {p.id for p in players} - chosen_ids
    assert left_out <= {p.id for p in players[:6]}


def test_arriving_late_does_not_jump_ahead_of_someone_being_skipped():
    # Both have just played one match, so the only thing separating them is
    # history: the latecomer has missed nothing because they were not here,
    # while the regular has sat through four matches without being picked.
    # Counting matches *played* would reward the latecomer for being absent.
    db = make_db()
    session, players = make_session(db, 5)
    regular, filler, latecomer, d1, d2 = players

    db.query(Attendance).filter_by(player_id=latecomer.id).update(
        {"arrived_at": ARRIVAL + timedelta(minutes=140)}
    )
    db.commit()

    for number in range(1, 5):
        play_match(db, session, [d1, d2], number)
    play_match(db, session, [regular, latecomer], 5)

    db.query(Attendance).filter(Attendance.player_id.in_([d1.id, d2.id])).update(
        {"status": "left"}, synchronize_session=False
    )
    db.commit()

    hist = history(db, session.id)
    assert hist[latecomer.id]["playing_streak"] == hist[regular.id]["playing_streak"] == 1
    assert hist[latecomer.id]["missed"] == 0, "não estava no ginásio, não perdeu nada"
    assert hist[regular.id]["missed"] == 4
    assert hist[filler.id]["outside_streak"] >= 2

    chosen = {p.id for p in select_players(db, session.id, target=2)}
    assert filler.id in chosen, "quem esperou 2+ entra sempre"
    assert regular.id in chosen, "quem vinha sendo pulado tem que passar na frente"
    assert latecomer.id not in chosen


def test_nobody_waits_two_matches_while_there_is_room_for_them():
    # With 12 on court, everyone left out fits into the next match as long as
    # fewer than 24 are present - so sitting out twice in a row should simply
    # never happen at this size, and the group counts on that.
    db = make_db()
    session, players = make_session(db, 22)

    for number in range(1, 13):
        squad = select_players(db, session.id, target=12)
        play_match(db, session, squad, number)

        hist = history(db, session.id)
        esperando_demais = {
            p.name for p in players if hist[p.id]["outside_streak"] >= 2
        }
        assert not esperando_demais, (
            f"após a partida {number}, esperaram 2 seguidas: {esperando_demais}"
        )
