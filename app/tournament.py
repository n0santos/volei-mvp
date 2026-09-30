from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player, TournamentMatch
from .schemas import (
    TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamFormRequest,
    TournamentMatchCreate, TournamentMatchUpdate,
)
from .services.team_formation import form_teams

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


@router.post("/api/tournaments/{tournament_id}/form-teams")
def form_tournament_teams(tournament_id: int, data: TeamFormRequest, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    teams = db.execute(
        select(Team).where(Team.tournament_id == tournament_id).order_by(Team.code)
    ).scalars().all()
    if len(teams) < 2:
        raise HTTPException(400, "É preciso pelo menos 2 times para sortear")

    occupied = db.execute(
        select(TeamPlayer)
        .join(Team, Team.id == TeamPlayer.team_id)
        .where(Team.tournament_id == tournament_id)
    ).scalars().all()
    if occupied:
        raise HTTPException(409, "Times já têm jogadores — remova antes de sortear de novo")

    if len(data.player_ids) < len(teams):
        raise HTTPException(400, "É preciso pelo menos um jogador por time")

    if len(set(data.player_ids)) != len(data.player_ids):
        raise HTTPException(400, "player_ids não pode ter jogador repetido")

    players = []
    for player_id in data.player_ids:
        player = db.get(Player, player_id)
        if not player:
            raise HTTPException(404, f"Jogador {player_id} não encontrado")
        players.append(player)

    formed = form_teams(players, len(teams))

    for team, roster in zip(teams, formed):
        for player in roster:
            db.add(TeamPlayer(team_id=team.id, player_id=player.id, role="titular"))

    db.commit()
    return tournament_state(tournament_id, db)


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
        .order_by(TournamentMatch.scheduled_at)
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
