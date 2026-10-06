from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch
from app.schemas import TournamentMatchCreate, SetPointRequest, WalkoverRequest
from app.tournament_matches import create_match, add_point, close_set, set_walkover, get_podium

SATURDAY = datetime(2026, 11, 28, 13, 0)


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_two_groups(db):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    teams = {}
    for code in ("A1", "A2", "A3", "B1", "B2", "B3"):
        teams[code] = Team(tournament_id=t.id, code=code, group_name=code[0])
        db.add(teams[code])
    db.commit()
    return t, teams


def new_match(db, t, a, b, stage="grupos"):
    return create_match(t.id, TournamentMatchCreate(team_a_id=a.id, team_b_id=b.id, scheduled_at=SATURDAY, stage=stage), db)


def win_by_scoreboard(db, t, match, winner="a"):
    """Play two 15-x sets through the scoreboard so close_set is what finishes the match."""
    loser = "b" if winner == "a" else "a"
    for _ in range(2):
        for _ in range(15):
            add_point(t.id, match.id, SetPointRequest(team=winner, delta=1), db)
        for _ in range(10):
            add_point(t.id, match.id, SetPointRequest(team=loser, delta=1), db)
        close_set(t.id, match.id, db)


def stage_of(db, stage):
    return db.query(TournamentMatch).filter_by(stage=stage).one_or_none()


def play_group(db, t, teams, prefix, skip_last=False):
    x1, x2, x3 = (teams[f"{prefix}{i}"] for i in (1, 2, 3))
    pairs = [(x1, x2), (x1, x3), (x2, x3)]
    for i, (a, b) in enumerate(pairs):
        m = new_match(db, t, a, b)
        if skip_last and i == len(pairs) - 1:
            return m
        win_by_scoreboard(db, t, m)


def test_semifinals_appear_when_the_last_group_game_is_decided():
    db = make_db()
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A")
    last = play_group(db, t, teams, "B", skip_last=True)
    assert stage_of(db, "semifinal_1") is None

    win_by_scoreboard(db, t, last)

    sf1, sf2 = stage_of(db, "semifinal_1"), stage_of(db, "semifinal_2")
    assert (sf1.team_a_id, sf1.team_b_id) == (teams["A1"].id, teams["B2"].id)
    assert (sf2.team_a_id, sf2.team_b_id) == (teams["B1"].id, teams["A2"].id)


def test_knockout_games_use_the_regulation_times_on_the_last_day():
    db = make_db()
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A")
    play_group(db, t, teams, "B")
    win_by_scoreboard(db, t, stage_of(db, "semifinal_1"))
    win_by_scoreboard(db, t, stage_of(db, "semifinal_2"))

    times = {m.stage: m.scheduled_at for m in db.query(TournamentMatch).filter(TournamentMatch.stage != "grupos")}

    assert times == {
        "semifinal_1": datetime(2026, 11, 29, 9, 0),
        "semifinal_2": datetime(2026, 11, 29, 10, 0),
        "terceiro_lugar": datetime(2026, 11, 29, 11, 0),
        "final": datetime(2026, 11, 29, 12, 0),
    }


def test_third_place_and_final_appear_when_both_semifinals_are_decided():
    db = make_db()
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A")
    play_group(db, t, teams, "B")
    sf1, sf2 = stage_of(db, "semifinal_1"), stage_of(db, "semifinal_2")

    win_by_scoreboard(db, t, sf1, winner="a")  # A1 beats B2
    assert stage_of(db, "final") is None  # one semifinal isn't enough
    win_by_scoreboard(db, t, sf2, winner="b")  # A2 beats B1

    third, final = stage_of(db, "terceiro_lugar"), stage_of(db, "final")
    assert {third.team_a_id, third.team_b_id} == {teams["B2"].id, teams["B1"].id}
    assert {final.team_a_id, final.team_b_id} == {teams["A1"].id, teams["A2"].id}
    assert final.is_final is True


def test_a_walkover_on_the_last_game_also_advances_the_tournament():
    db = make_db()
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A")
    last = play_group(db, t, teams, "B", skip_last=True)

    set_walkover(t.id, last.id, WalkoverRequest(present="a"), db)

    assert stage_of(db, "semifinal_1") is not None


def test_nothing_is_created_while_a_group_still_has_games_to_play():
    db = make_db()
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A")
    play_group(db, t, teams, "B", skip_last=True)

    assert db.query(TournamentMatch).filter(TournamentMatch.stage != "grupos").count() == 0


def test_a_tie_for_a_qualifying_spot_creates_nothing_and_raises_nothing():
    db = make_db()
    t, teams = make_two_groups(db)
    # Group A as a three-way cycle: nobody can be told apart
    a1, a2, a3 = teams["A1"], teams["A2"], teams["A3"]
    for a, b in [(a1, a2), (a2, a3), (a3, a1)]:
        win_by_scoreboard(db, t, new_match(db, t, a, b))
    play_group(db, t, teams, "B")

    assert stage_of(db, "semifinal_1") is None


def test_manually_registered_semifinals_still_lead_to_the_automatic_final():
    # The tie escape hatch: the organization draws and creates the semifinals by hand.
    db = make_db()
    t, teams = make_two_groups(db)
    sf1 = new_match(db, t, teams["A1"], teams["B2"], stage="semifinal_1")
    sf2 = new_match(db, t, teams["B1"], teams["A2"], stage="semifinal_2")

    win_by_scoreboard(db, t, sf1)
    win_by_scoreboard(db, t, sf2)

    assert stage_of(db, "final") is not None
    assert stage_of(db, "terceiro_lugar") is not None


def test_later_results_never_duplicate_the_knockout_games():
    db = make_db()
    t, teams = make_two_groups(db)
    play_group(db, t, teams, "A")
    play_group(db, t, teams, "B")
    win_by_scoreboard(db, t, stage_of(db, "semifinal_1"))
    win_by_scoreboard(db, t, stage_of(db, "semifinal_2"))
    win_by_scoreboard(db, t, stage_of(db, "final"))
    win_by_scoreboard(db, t, stage_of(db, "terceiro_lugar"))

    assert db.query(TournamentMatch).filter(TournamentMatch.stage != "grupos").count() == 4
    assert get_podium(t.id, db)["champion"] is not None
