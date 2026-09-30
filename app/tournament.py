from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player
from .schemas import TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate

router = APIRouter()


@router.post("/api/tournaments")
def create_tournament(data: TournamentCreate, db: DBSession = Depends(get_db)):
    # Only one active tournament in the MVP - same rule as Session.
    old = db.execute(select(Tournament).where(Tournament.active == True)).scalars().all()
    for t in old:
        t.active = False

    t = Tournament(name=data.name, start_date=data.start_date, end_date=data.end_date)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.get("/api/tournaments/active")
def active_tournament(db: DBSession = Depends(get_db)):
    t = db.execute(
        select(Tournament).where(Tournament.active == True).order_by(Tournament.id.desc())
    ).scalar_one_or_none()
    if not t:
        return None
    return {"id": t.id, "name": t.name, "start_date": t.start_date, "end_date": t.end_date}


def get_tournament(db, tournament_id):
    t = db.get(Tournament, tournament_id)
    if not t:
        raise HTTPException(404, "Torneio não encontrado")
    return t


@router.post("/api/tournaments/{tournament_id}/teams")
def create_team(tournament_id: int, data: TeamCreate, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    team = Team(tournament_id=tournament_id, code=data.code)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@router.get("/api/tournaments/{tournament_id}")
def tournament_state(tournament_id: int, db: DBSession = Depends(get_db)):
    t = get_tournament(db, tournament_id)
    teams = db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars().all()

    teams_data = []
    for team in teams:
        roster = db.execute(
            select(TeamPlayer, Player)
            .join(Player, Player.id == TeamPlayer.player_id)
            .where(TeamPlayer.team_id == team.id)
        ).all()
        teams_data.append({
            "id": team.id,
            "code": team.code,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "score": p.score,
                    "gender": p.gender,
                    "role": tp.role,
                    "is_captain": tp.is_captain,
                }
                for tp, p in roster
            ],
        })

    return {
        "tournament": {"id": t.id, "name": t.name, "start_date": t.start_date, "end_date": t.end_date},
        "teams": teams_data,
    }
