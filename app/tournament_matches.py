from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Team, TournamentMatch
from .schemas import TournamentMatchCreate, TournamentMatchUpdate
from .tournament import get_tournament

router = APIRouter()

MATCH_STATUSES = {"agendado", "em_andamento", "encerrado"}


def get_tournament_team(db, tournament_id, team_id):
    team = db.execute(
        select(Team).where(Team.id == team_id, Team.tournament_id == tournament_id)
    ).scalar_one_or_none()
    if not team:
        raise HTTPException(404, "Time não encontrado neste torneio")
    return team


@router.post("/api/tournaments/{tournament_id}/matches")
def create_match(tournament_id: int, data: TournamentMatchCreate, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    get_tournament_team(db, tournament_id, data.team_a_id)
    get_tournament_team(db, tournament_id, data.team_b_id)
    if data.team_a_id == data.team_b_id:
        raise HTTPException(400, "Os dois times não podem ser o mesmo")

    m = TournamentMatch(
        tournament_id=tournament_id,
        team_a_id=data.team_a_id,
        team_b_id=data.team_b_id,
        scheduled_at=data.scheduled_at,
        court=data.court,
        is_final=data.is_final,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.get("/api/tournaments/{tournament_id}/matches")
def list_matches(tournament_id: int, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    matches = db.execute(
        select(TournamentMatch)
        .where(TournamentMatch.tournament_id == tournament_id)
        .order_by(TournamentMatch.scheduled_at, TournamentMatch.id)
    ).scalars().all()

    team_codes = {
        team.id: team.code
        for team in db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars()
    }

    return [
        {
            "id": m.id,
            "team_a_id": m.team_a_id,
            "team_a_code": team_codes.get(m.team_a_id),
            "team_b_id": m.team_b_id,
            "team_b_code": team_codes.get(m.team_b_id),
            "scheduled_at": m.scheduled_at,
            "court": m.court,
            "status": m.status,
            "is_final": m.is_final,
        }
        for m in matches
    ]


def get_match(db, tournament_id, match_id):
    m = db.execute(
        select(TournamentMatch).where(
            TournamentMatch.id == match_id,
            TournamentMatch.tournament_id == tournament_id,
        )
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Jogo não encontrado")
    return m


@router.patch("/api/tournaments/{tournament_id}/matches/{match_id}")
def update_match(tournament_id: int, match_id: int, data: TournamentMatchUpdate, db: DBSession = Depends(get_db)):
    m = get_match(db, tournament_id, match_id)

    if data.team_a_id is not None:
        get_tournament_team(db, tournament_id, data.team_a_id)
        m.team_a_id = data.team_a_id
    if data.team_b_id is not None:
        get_tournament_team(db, tournament_id, data.team_b_id)
        m.team_b_id = data.team_b_id
    if m.team_a_id == m.team_b_id:
        raise HTTPException(400, "Os dois times não podem ser o mesmo")

    if data.scheduled_at is not None:
        m.scheduled_at = data.scheduled_at
    if data.court is not None:
        m.court = data.court
    if data.status is not None:
        if data.status not in MATCH_STATUSES:
            raise HTTPException(400, "Status inválido")
        m.status = data.status
    if data.is_final is not None:
        m.is_final = data.is_final

    db.commit()
    db.refresh(m)
    return m


@router.delete("/api/tournaments/{tournament_id}/matches/{match_id}")
def delete_match(tournament_id: int, match_id: int, db: DBSession = Depends(get_db)):
    m = get_match(db, tournament_id, match_id)
    db.delete(m)
    db.commit()
    return {"ok": True}
