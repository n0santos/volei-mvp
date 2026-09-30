from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TeamPlayer, Player


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_tournament_team_teamplayer_roundtrip():
    db = make_db()
    t = Tournament(name="Torneio de Verão", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()

    team = Team(tournament_id=t.id, code="A")
    db.add(team)
    db.flush()

    p = Player(name="Ana", score=70, gender="F")
    db.add(p)
    db.flush()

    tp = TeamPlayer(team_id=team.id, player_id=p.id, role="titular", is_captain=True)
    db.add(tp)
    db.commit()

    saved = db.query(TeamPlayer).filter_by(team_id=team.id).one()
    assert saved.player.name == "Ana"
    assert saved.role == "titular"
    assert saved.is_captain is True


def test_tournament_defaults_to_active():
    db = make_db()
    t = Tournament(name="X", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.commit()
    assert t.active is True


def test_team_player_defaults():
    db = make_db()
    t = Tournament(name="X", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    team = Team(tournament_id=t.id, code="A")
    db.add(team)
    db.flush()
    p = Player(name="B", score=70, gender="M")
    db.add(p)
    db.flush()

    tp = TeamPlayer(team_id=team.id, player_id=p.id)
    db.add(tp)
    db.commit()

    assert tp.role == "titular"
    assert tp.is_captain is False
