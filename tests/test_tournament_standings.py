from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch, TournamentSetResult
from app.tournament_matches import get_standings, generate_final


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_tournament_and_teams(db, codes=("A", "B"), groups=None):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    groups = groups or (None,) * len(codes)
    teams = [Team(tournament_id=t.id, code=code, group_name=g) for code, g in zip(codes, groups)]
    db.add_all(teams)
    db.flush()
    return t, teams


def standings_rows(tournament_id, db):
    # Flat view of every group's rows - enough for tests that don't care about groups.
    return [row for g in get_standings(tournament_id, db) for row in g["rows"]]


def make_finished_match(db, tournament_id, team_a_id, team_b_id, sets, is_final=False):
    m = TournamentMatch(
        tournament_id=tournament_id, team_a_id=team_a_id, team_b_id=team_b_id,
        scheduled_at=datetime(2026, 11, 28, 13, 0), status="encerrado", is_final=is_final,
    )
    db.add(m)
    db.flush()
    for i, (pa, pb) in enumerate(sets, start=1):
        db.add(TournamentSetResult(match_id=m.id, set_number=i, points_a=pa, points_b=pb, closed=True))
    db.commit()
    return m


def test_standings_from_a_finished_match():
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)])

    standings = standings_rows(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 3
    assert by_team["A"]["wins"] == 1
    assert by_team["B"]["tournament_points"] == 0


def test_teams_with_no_finished_match_still_appear_at_zero():
    db = make_db()
    t, (team_a, team_b, team_c) = make_tournament_and_teams(db, codes=("A", "B", "C"))
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)])

    standings = standings_rows(t.id, db)

    assert len(standings) == 3
    by_team = {row["team"]: row for row in standings}
    assert by_team["C"]["tournament_points"] == 0
    assert by_team["C"]["wins"] == 0
    assert by_team["C"]["tied"] is False
    # Zero-match team appended at the end should come after teams that
    # actually played, in deterministic (team-code) order.
    assert standings[-1]["team"] == "C"


def test_final_match_does_not_count_toward_standings():
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)], is_final=True)

    standings = standings_rows(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 0
    assert by_team["B"]["tournament_points"] == 0


def test_unfinished_match_does_not_count_toward_standings():
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0), status="em_andamento",
    )
    db.add(m)
    db.flush()
    db.add(TournamentSetResult(match_id=m.id, set_number=1, points_a=18, points_b=10, closed=True))
    db.commit()

    standings = standings_rows(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 0
    assert by_team["B"]["tournament_points"] == 0


def test_encerrado_match_with_no_closed_sets_does_not_crash_standings():
    # Regression: the "Encerrar" button (from the Jogos section) can mark a
    # match as encerrado with no actual decided result. get_standings must
    # skip it instead of crashing compute_standings/match_points.
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0), status="encerrado",
    )
    db.add(m)
    db.commit()

    standings = standings_rows(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 0
    assert by_team["B"]["tournament_points"] == 0


def test_encerrado_match_with_one_closed_set_does_not_crash_standings():
    # Same scenario, but with exactly one closed set — still not a decided
    # best-of-3 result (needs 2 closed sets with a winner), so it must still
    # be excluded rather than crashing.
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0), status="encerrado",
    )
    db.add(m)
    db.flush()
    db.add(TournamentSetResult(match_id=m.id, set_number=1, points_a=18, points_b=10, closed=True))
    db.commit()

    standings = standings_rows(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 0
    assert by_team["B"]["tournament_points"] == 0


def test_standings_are_split_by_group():
    db = make_db()
    t, (a, b, c, d) = make_tournament_and_teams(db, codes=("A", "B", "C", "D"), groups=("A", "A", "B", "B"))
    make_finished_match(db, t.id, a.id, b.id, [(15, 10), (15, 12)])
    make_finished_match(db, t.id, c.id, d.id, [(15, 10), (15, 12)])

    groups = get_standings(t.id, db)

    assert [g["group"] for g in groups] == ["A", "B"]
    assert {r["team"] for r in groups[0]["rows"]} == {"A", "B"}
    assert {r["team"] for r in groups[1]["rows"]} == {"C", "D"}
    assert groups[0]["rows"][0]["team"] == "A"
    assert groups[1]["rows"][0]["team"] == "C"


def test_teams_without_a_group_go_in_a_trailing_block_and_never_qualify():
    db = make_db()
    t, (a, b, c) = make_tournament_and_teams(db, codes=("A", "B", "C"), groups=("A", "A", None))

    groups = get_standings(t.id, db)

    assert [g["group"] for g in groups] == ["A", None]
    assert [r["team"] for r in groups[1]["rows"]] == ["C"]
    assert all(r["qualified"] is False for r in groups[1]["rows"])


def test_top_two_of_a_complete_group_qualify():
    db = make_db()
    t, (a, b, c) = make_tournament_and_teams(db, codes=("A", "B", "C"), groups=("A", "A", "A"))
    make_finished_match(db, t.id, a.id, b.id, [(15, 10), (15, 12)])  # A: 3
    make_finished_match(db, t.id, a.id, c.id, [(15, 10), (15, 12)])  # A: 6
    make_finished_match(db, t.id, b.id, c.id, [(15, 10), (15, 12)])  # B: 3, C: 0

    (group,) = get_standings(t.id, db)

    assert group["complete"] is True
    assert [(r["team"], r["qualified"]) for r in group["rows"]] == [("A", True), ("B", True), ("C", False)]


def test_nobody_qualifies_while_the_group_still_has_games_to_play():
    # A-B and B-C are done and the table already has a clear order, but A-C
    # is still to play and could reshuffle it.
    db = make_db()
    t, (a, b, c) = make_tournament_and_teams(db, codes=("A", "B", "C"), groups=("A", "A", "A"))
    make_finished_match(db, t.id, a.id, b.id, [(15, 10), (15, 12)])
    make_finished_match(db, t.id, b.id, c.id, [(15, 10), (15, 12)])

    (group,) = get_standings(t.id, db)

    assert group["complete"] is False
    assert all(r["qualified"] is False for r in group["rows"])


def test_a_tie_for_the_last_spot_leaves_everyone_unqualified():
    # Three-way cycle with identical scores (A beats B, B beats C, C beats A):
    # everything ties, so picking two of the three would be arbitrary.
    db = make_db()
    t, (a, b, c) = make_tournament_and_teams(db, codes=("A", "B", "C"), groups=("A", "A", "A"))
    make_finished_match(db, t.id, a.id, b.id, [(15, 10), (15, 10)])
    make_finished_match(db, t.id, b.id, c.id, [(15, 10), (15, 10)])
    make_finished_match(db, t.id, c.id, a.id, [(15, 10), (15, 10)])

    (group,) = get_standings(t.id, db)

    assert group["complete"] is True
    assert all(r["tied"] for r in group["rows"])
    assert all(r["qualified"] is False for r in group["rows"])


def test_generate_final_is_disabled_until_semifinals_exist():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, _ = make_tournament_and_teams(db)

    with pytest.raises(HTTPException) as exc_info:
        generate_final(t.id, db)
    assert exc_info.value.status_code == 409
