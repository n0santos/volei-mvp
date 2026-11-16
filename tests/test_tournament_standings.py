from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch, TournamentSetResult
from app.tournament_matches import get_standings


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_tournament_and_teams(db, codes=("A", "B")):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    teams = [Team(tournament_id=t.id, code=code) for code in codes]
    db.add_all(teams)
    db.flush()
    return t, teams


def standings_rows(tournament_id, db):
    return get_standings(tournament_id, db)["rows"]


def make_finished_match(db, tournament_id, team_a_id, team_b_id, sets, stage="grupos"):
    m = TournamentMatch(
        tournament_id=tournament_id, team_a_id=team_a_id, team_b_id=team_b_id,
        scheduled_at=datetime(2026, 11, 28, 13, 0), status="encerrado", stage=stage, is_final=stage == "final",
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
    # C hasn't played, so it ties B on points and wins but beats B's -2 set
    # balance from the 0x2 loss; it is ranked by the same criteria as everyone.
    assert [row["team"] for row in standings] == ["A", "C", "B"]


def test_final_match_does_not_count_toward_standings():
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)], stage="final")

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


def test_nobody_qualifies_while_games_are_still_to_play():
    db = make_db()
    t, teams = make_tournament_and_teams(db, codes=("A", "B", "C", "D", "E", "F"))
    make_finished_match(db, t.id, teams[0].id, teams[1].id, [(15, 10), (15, 12)])

    table = get_standings(t.id, db)

    assert table["complete"] is False
    assert all(r["qualified"] is False for r in table["rows"])
    assert len(table["rows"]) == 6


def test_top_four_of_the_complete_table_qualify():
    db = make_db()
    t, teams = make_tournament_and_teams(db, codes=("A", "B", "C", "D", "E", "F"))
    a, b, c, d, e, f = teams
    # nine games; wins A=3, B=2, C=2... every pairing decided 2-0 (15-10, 15-12)
    for x, y in [(a, b), (c, d), (e, f), (a, c), (b, e), (d, f), (a, d), (b, f), (c, e)]:
        make_finished_match(db, t.id, x.id, y.id, [(15, 10), (15, 12)])

    table = get_standings(t.id, db)

    assert table["complete"] is True
    qualified = [r["team"] for r in table["rows"] if r["qualified"]]
    # A 3 wins; B and C 2 each; D and E 1 each tie for the last spot -> nobody is
    # picked arbitrarily, so the cut is left to the organization
    assert qualified == []
    assert [r["tied"] for r in table["rows"]][-3:-1] == [True, True]


def test_point_adjustments_show_in_the_standings_and_can_be_removed():
    import pytest
    from fastapi import HTTPException
    from app.schemas import AdjustmentCreate
    from app.tournament_matches import create_adjustment, list_adjustments, delete_adjustment

    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    make_finished_match(db, t.id, team_a.id, team_b.id, [(21, 10), (21, 12)])

    adj = create_adjustment(t.id, AdjustmentCreate(team_id=team_a.id, points=-1, reason="Faltou à abertura"), db)
    by_team = {row["team"]: row for row in standings_rows(t.id, db)}
    assert (by_team["A"]["tournament_points"], by_team["A"]["adjustment"]) == (2, -1)
    assert [(a["team"], a["points"]) for a in get_standings(t.id, db)["adjustments"]] == [("A", -1)]
    assert [(a["team"], a["points"], a["reason"]) for a in list_adjustments(t.id, db)] == [("A", -1, "Faltou à abertura")]

    delete_adjustment(t.id, adj.id, db)
    assert standings_rows(t.id, db)[0]["tournament_points"] == 3
    assert list_adjustments(t.id, db) == []

    for bad in (dict(points=0, reason="x"), dict(points=-1, reason="  ")):
        with pytest.raises(HTTPException) as exc_info:
            create_adjustment(t.id, AdjustmentCreate(team_id=team_a.id, **bad), db)
        assert exc_info.value.status_code == 400


def six_team_table_with_semis(db):
    """Six teams; A-D in the semifinals (by hand), E and F out. Returns (t, teams by code)."""
    t, teams = make_tournament_and_teams(db, codes=("A", "B", "C", "D", "E", "F"))
    by_code = {team.code: team for team in teams}
    win = [(21, 10), (21, 10)]
    make_finished_match(db, t.id, by_code["A"].id, by_code["E"].id, win)
    make_finished_match(db, t.id, by_code["B"].id, by_code["F"].id, win)
    make_finished_match(db, t.id, by_code["C"].id, by_code["E"].id, win)
    make_finished_match(db, t.id, by_code["D"].id, by_code["F"].id, win)
    # E and F split their two games: both have 1 win; E has 4 pts (2-0 + 1-2), F 2 pts.
    make_finished_match(db, t.id, by_code["E"].id, by_code["F"].id, win)
    make_finished_match(db, t.id, by_code["F"].id, by_code["E"].id, [(21, 19), (19, 21), (18, 16)])
    for stage, (a, b) in (("semifinal_1", ("A", "D")), ("semifinal_2", ("B", "C"))):
        m = TournamentMatch(
            tournament_id=t.id, team_a_id=by_code[a].id, team_b_id=by_code[b].id,
            scheduled_at=datetime(2026, 11, 29, 13, 0), stage=stage,
        )
        db.add(m)
    db.commit()
    return t, by_code


def test_a_penalty_after_the_semifinals_keeps_the_semifinalists_on_top():
    from app.schemas import AdjustmentCreate
    from app.tournament_matches import create_adjustment

    db = make_db()
    t, by_code = six_team_table_with_semis(db)
    # D (3 pts) loses 6 after the semis: fewer points than E (2 pts), but D is
    # in a semifinal, so it stays among the four qualified rows.
    create_adjustment(t.id, AdjustmentCreate(team_id=by_code["D"].id, points=-6, reason="Conduta grave"), db)

    rows = standings_rows(t.id, db)
    assert {row["team"] for row in rows[:4]} == {"A", "B", "C", "D"}
    assert all(row["qualified"] for row in rows[:4])
    assert [row["team"] for row in rows[4:]] == ["E", "F"]
    assert not any(row["qualified"] for row in rows[4:])
    assert rows[3]["team"] == "D" and rows[3]["rank"] == 4
    assert [row["rank"] for row in rows[4:]] == [5, 6]


def test_a_penalty_after_the_semifinals_can_swap_fifth_and_sixth():
    from app.schemas import AdjustmentCreate
    from app.tournament_matches import create_adjustment, delete_adjustment

    db = make_db()
    t, by_code = six_team_table_with_semis(db)
    assert [row["team"] for row in standings_rows(t.id, db)[4:]] == ["E", "F"]

    adj = create_adjustment(t.id, AdjustmentCreate(team_id=by_code["E"].id, points=-3, reason="Simulação de lesão"), db)
    assert [row["team"] for row in standings_rows(t.id, db)[4:]] == ["F", "E"]

    delete_adjustment(t.id, adj.id, db)
    assert [row["team"] for row in standings_rows(t.id, db)[4:]] == ["E", "F"]
