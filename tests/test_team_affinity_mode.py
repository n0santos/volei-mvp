import asyncio
from datetime import date, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import create_session, generate_match, session_state
from app.models import Player, Attendance, MatchPlayer, Tournament, Team, TeamPlayer
from app.schemas import SessionCreate

ARRIVAL = datetime(2026, 11, 4, 19, 0)


def make_night(team_affinity=None):
    """12 equally-rated arrivals, split 6/6 into two tournament teams."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    players = [Player(name=f"P{i:02d}", score=70, gender="X") for i in range(12)]
    db.add_all(players)
    db.flush()

    t = Tournament(name="T", start_date=date(2026, 11, 1), end_date=date(2026, 11, 30), active=True)
    db.add(t)
    db.flush()
    teams = [Team(tournament_id=t.id, code="Azul"), Team(tournament_id=t.id, code="Verde")]
    db.add_all(teams)
    db.flush()
    for i, p in enumerate(players):
        db.add(TeamPlayer(team_id=teams[i // 6].id, player_id=p.id))

    kwargs = {} if team_affinity is None else {"team_affinity": team_affinity}
    created = asyncio.run(create_session(
        SessionCreate(name="Vôlei", player_ids=[p.id for p in players], **kwargs), db
    ))
    for order, att in enumerate(db.execute(select(Attendance)).scalars(), start=1):
        att.status, att.arrival_order, att.arrived_at = "arrived", order, ARRIVAL
    db.commit()
    team_of = {p.id: i // 6 for i, p in enumerate(players)}
    return db, created["id"], team_of


def draw(db, sid):
    match_id = asyncio.run(generate_match(sid, db))["match_id"]
    rows = db.execute(select(MatchPlayer).where(MatchPlayer.match_id == match_id)).scalars().all()
    # leave no open match behind so the next draw is allowed
    from app.models import Match
    db.get(Match, match_id).status = "finished"
    db.commit()
    return rows


def sides_keep_tournament_teams(rows, team_of):
    return all(len({r.team for r in rows if team_of[r.player_id] == t}) == 1 for t in (0, 1))


def test_affinity_is_off_by_default():
    db, sid, _ = make_night()
    assert session_state(sid, db)["session"]["team_affinity"] is False


def test_the_option_is_saved_and_exposed():
    db, sid, _ = make_night(team_affinity=True)
    assert session_state(sid, db)["session"]["team_affinity"] is True


def test_with_affinity_on_tournament_teams_stay_together():
    db, sid, team_of = make_night(team_affinity=True)
    for _ in range(10):
        assert sides_keep_tournament_teams(draw(db, sid), team_of)


def test_with_affinity_off_the_draw_ignores_tournament_teams():
    # Twelve equal players: dozens of splits tie, so without affinity the
    # tournament teams get split in most draws.
    db, sid, team_of = make_night(team_affinity=False)
    kept = [sides_keep_tournament_teams(draw(db, sid), team_of) for _ in range(12)]
    assert not all(kept)
