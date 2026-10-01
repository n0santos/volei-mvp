from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch, TournamentSetResult
from app.schemas import GenerateFinalRequest
from app.tournament_matches import get_standings, generate_final


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

    standings = get_standings(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 3
    assert by_team["A"]["wins"] == 1
    assert by_team["B"]["tournament_points"] == 0


def test_teams_with_no_finished_match_still_appear_at_zero():
    db = make_db()
    t, (team_a, team_b, team_c) = make_tournament_and_teams(db, codes=("A", "B", "C"))
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)])

    standings = get_standings(t.id, db)

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

    standings = get_standings(t.id, db)

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

    standings = get_standings(t.id, db)

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

    standings = get_standings(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 0
    assert by_team["B"]["tournament_points"] == 0


def test_generate_final_creates_match_from_top_two():
    db = make_db()
    t, (team_a, team_b, team_c) = make_tournament_and_teams(db, codes=("A", "B", "C"))
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)])  # A beats B: A+3
    make_finished_match(db, t.id, team_a.id, team_c.id, [(18, 10), (18, 12)])  # A beats C: A+3 -> A=6
    make_finished_match(db, t.id, team_b.id, team_c.id, [(18, 10), (18, 12)])  # B beats C: B+3 -> B=3, C=0

    final = generate_final(
        t.id, GenerateFinalRequest(scheduled_at=datetime(2026, 11, 29, 16, 20)), db
    )

    assert final.is_final is True
    assert final.team_a_id == team_a.id
    assert final.team_b_id == team_b.id


def test_generate_final_rejects_when_group_stage_incomplete():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0), status="agendado",
    )
    db.add(m)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        generate_final(t.id, GenerateFinalRequest(scheduled_at=datetime(2026, 11, 29, 16, 20)), db)
    assert exc_info.value.status_code == 400


def test_generate_final_rejects_when_no_group_matches():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)

    with pytest.raises(HTTPException) as exc_info:
        generate_final(t.id, GenerateFinalRequest(scheduled_at=datetime(2026, 11, 29, 16, 20)), db)
    assert exc_info.value.status_code == 400


def test_generate_final_rejects_if_final_already_exists():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)])
    make_finished_match(db, t.id, team_a.id, team_b.id, [(10, 18), (12, 18)], is_final=True)

    with pytest.raises(HTTPException) as exc_info:
        generate_final(t.id, GenerateFinalRequest(scheduled_at=datetime(2026, 11, 29, 16, 20)), db)
    assert exc_info.value.status_code == 409


def test_generate_final_rejects_when_first_place_is_tied():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, (team_a, team_b, team_c) = make_tournament_and_teams(db, codes=("A", "B", "C"))
    make_finished_match(db, t.id, team_a.id, team_c.id, [(18, 10), (18, 10)])
    make_finished_match(db, t.id, team_b.id, team_c.id, [(18, 10), (18, 10)])

    with pytest.raises(HTTPException) as exc_info:
        generate_final(t.id, GenerateFinalRequest(scheduled_at=datetime(2026, 11, 29, 16, 20)), db)
    assert exc_info.value.status_code == 400


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

    standings = get_standings(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 0
    assert by_team["B"]["tournament_points"] == 0
