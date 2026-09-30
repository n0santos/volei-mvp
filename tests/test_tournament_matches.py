from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_tournament_and_teams(db):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    team_a = Team(tournament_id=t.id, code="A")
    team_b = Team(tournament_id=t.id, code="B")
    db.add_all([team_a, team_b])
    db.flush()
    return t, team_a, team_b


def test_tournament_match_roundtrip():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    m = TournamentMatch(
        tournament_id=t.id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
        court="Quadra 1",
    )
    db.add(m)
    db.commit()

    saved = db.query(TournamentMatch).filter_by(tournament_id=t.id).one()
    assert saved.team_a_id == team_a.id
    assert saved.team_b_id == team_b.id
    assert saved.scheduled_at == datetime(2026, 11, 28, 13, 0)
    assert saved.court == "Quadra 1"


def test_tournament_match_defaults():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    m = TournamentMatch(
        tournament_id=t.id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
    )
    db.add(m)
    db.commit()

    assert m.status == "agendado"
    assert m.is_final is False
    assert m.court is None
