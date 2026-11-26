from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.arbitro import needs_referee
from app.database import Base
from app.models import Player, Team, TeamPlayer, Tournament
from app.tournament_awards import AwardWinner, list_awards, set_award
from test_arbitro import request


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    t = Tournament(name="Torneio", start_date=date(2026, 11, 27), end_date=date(2026, 11, 29))
    s.add(t)
    s.flush()
    team = Team(tournament_id=t.id, code="BOLEIRO")
    s.add_all([team, Player(name="Ana", gender="F"), Player(name="Beto", gender="M"), Player(name="Fora", gender="M")])
    s.flush()
    for name in ("Ana", "Beto"):
        pid = s.query(Player).filter_by(name=name).one().id
        s.add(TeamPlayer(team_id=team.id, player_id=pid))
    s.commit()
    return s


def pid(db, name):
    return db.query(Player).filter_by(name=name).one().id


def by_key(awards):
    return {a["key"]: a for a in awards}


def test_four_awards_start_undecided(db):
    awards = list_awards(1, db)
    assert [a["key"] for a in awards] == ["mvp_m", "mvp_f", "raca_m", "raca_f"]
    assert all(a["winner"] is None for a in awards)


def test_set_change_and_clear_a_winner(db):
    set_award(1, "mvp_f", AwardWinner(player_id=pid(db, "Ana")), db)
    assert by_key(list_awards(1, db))["mvp_f"]["winner"] == {"player_id": pid(db, "Ana"), "name": "Ana", "team": "BOLEIRO"}

    set_award(1, "mvp_f", AwardWinner(player_id=None), db)
    assert by_key(list_awards(1, db))["mvp_f"]["winner"] is None


def test_same_player_can_win_two_awards(db):
    set_award(1, "mvp_m", AwardWinner(player_id=pid(db, "Beto")), db)
    set_award(1, "raca_m", AwardWinner(player_id=pid(db, "Beto")), db)
    awards = by_key(list_awards(1, db))
    assert awards["mvp_m"]["winner"]["name"] == awards["raca_m"]["winner"]["name"] == "Beto"


@pytest.mark.parametrize("key,name,why", [
    ("mvp_m", "Ana", "naipe"),        # wrong gender
    ("mvp_m", "Fora", "equipe"),      # not on any team of the tournament
])
def test_invalid_winner_is_refused(db, key, name, why):
    with pytest.raises(HTTPException) as e:
        set_award(1, key, AwardWinner(player_id=pid(db, name)), db)
    assert e.value.status_code == 400 and why in e.value.detail


def test_unknown_award_is_404(db):
    with pytest.raises(HTTPException) as e:
        set_award(1, "melhor_torcida", AwardWinner(player_id=None), db)
    assert e.value.status_code == 404


def test_choosing_a_winner_needs_a_referee():
    assert needs_referee(request("PUT", "/api/tournaments/2/awards/mvp_f"))
    assert not needs_referee(request("GET", "/api/tournaments/2/awards"))
