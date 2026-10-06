from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player
from .schemas import TournamentCreate, TeamCreate, TeamUpdate, TeamPlayerAdd, TeamPlayerUpdate

router = APIRouter()

GROUPS = ("A", "B")


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


@router.patch("/api/teams/{team_id}")
def update_team(team_id: int, data: TeamUpdate, db: DBSession = Depends(get_db)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Time não encontrado")

    # Explicit null clears the group, so tell "sent null" from "not sent".
    if "group_name" in data.model_fields_set:
        if data.group_name is not None and data.group_name not in GROUPS:
            raise HTTPException(400, "Grupo precisa ser A ou B")
        team.group_name = data.group_name

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
            "group_name": team.group_name,
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


@router.post("/api/teams/{team_id}/players")
def add_team_player(team_id: int, data: TeamPlayerAdd, db: DBSession = Depends(get_db)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Time não encontrado")
    player = db.get(Player, data.player_id)
    if not player:
        raise HTTPException(404, "Jogador não encontrado")

    existing = db.execute(
        select(TeamPlayer).where(
            TeamPlayer.team_id == team_id,
            TeamPlayer.player_id == data.player_id,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Jogador já está no time")

    # No player swaps between teams in this tournament's regulation - a
    # player already on another team here can't be added to this one either.
    in_other_team = db.execute(
        select(TeamPlayer)
        .join(Team, Team.id == TeamPlayer.team_id)
        .where(
            Team.tournament_id == team.tournament_id,
            TeamPlayer.player_id == data.player_id,
        )
    ).scalar_one_or_none()
    if in_other_team:
        raise HTTPException(409, "Jogador já está em outro time deste torneio")

    tp = TeamPlayer(team_id=team_id, player_id=data.player_id, role=data.role)
    db.add(tp)
    db.commit()
    db.refresh(tp)
    return tp


def get_team_player(db, team_id, player_id):
    tp = db.execute(
        select(TeamPlayer).where(
            TeamPlayer.team_id == team_id,
            TeamPlayer.player_id == player_id,
        )
    ).scalar_one_or_none()
    if not tp:
        raise HTTPException(404, "Jogador não está neste time")
    return tp


@router.patch("/api/teams/{team_id}/players/{player_id}")
def update_team_player(team_id: int, player_id: int, data: TeamPlayerUpdate, db: DBSession = Depends(get_db)):
    tp = get_team_player(db, team_id, player_id)

    if data.role is not None:
        tp.role = data.role

    if data.is_captain is True:
        # Only one captain per team - unmark whoever had it before.
        others = db.execute(
            select(TeamPlayer).where(
                TeamPlayer.team_id == team_id,
                TeamPlayer.id != tp.id,
            )
        ).scalars().all()
        for other in others:
            other.is_captain = False
        tp.is_captain = True
    elif data.is_captain is False:
        tp.is_captain = False

    db.commit()
    db.refresh(tp)
    return tp


@router.delete("/api/teams/{team_id}/players/{player_id}")
def remove_team_player(team_id: int, player_id: int, db: DBSession = Depends(get_db)):
    tp = get_team_player(db, team_id, player_id)
    db.delete(tp)
    db.commit()
    return {"ok": True}


