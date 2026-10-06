from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Team, TournamentMatch, TournamentSetResult
from .schemas import TournamentMatchCreate, TournamentMatchUpdate, SetPointRequest, GenerateFinalRequest
from .services.tournament_engine import SET_TARGETS, is_set_over, match_result, compute_standings
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
    db.execute(delete(TournamentSetResult).where(TournamentSetResult.match_id == m.id))
    db.delete(m)
    db.commit()
    return {"ok": True}


def get_open_set(db, match_id):
    return db.execute(
        select(TournamentSetResult).where(
            TournamentSetResult.match_id == match_id,
            TournamentSetResult.closed == False,
        )
    ).scalar_one_or_none()


def get_closed_sets(db, match_id):
    return db.execute(
        select(TournamentSetResult)
        .where(TournamentSetResult.match_id == match_id, TournamentSetResult.closed == True)
        .order_by(TournamentSetResult.set_number)
    ).scalars().all()


def decided_result(db, match_id):
    closed = get_closed_sets(db, match_id)
    if len(closed) < 2:
        return None
    result = match_result([(s.points_a, s.points_b) for s in closed])
    return result if result["winner"] else None


def serialize_set(s):
    return {"set_number": s.set_number, "points_a": s.points_a, "points_b": s.points_b, "closed": s.closed}


@router.get("/api/tournaments/{tournament_id}/matches/{match_id}/scoreboard")
def get_scoreboard(tournament_id: int, match_id: int, db: DBSession = Depends(get_db)):
    m = get_match(db, tournament_id, match_id)
    all_sets = db.execute(
        select(TournamentSetResult)
        .where(TournamentSetResult.match_id == match_id)
        .order_by(TournamentSetResult.set_number)
    ).scalars().all()
    open_set = next((s for s in all_sets if not s.closed), None)
    result = decided_result(db, match_id)

    current_set = None
    if open_set and result is None:
        target = SET_TARGETS.get(open_set.set_number, 18)
        current_set = {
            **serialize_set(open_set),
            "target": target,
            "is_over": is_set_over(open_set.points_a, open_set.points_b, target),
        }

    return {
        "match": {"id": m.id, "status": m.status, "is_final": m.is_final},
        "sets": [serialize_set(s) for s in all_sets],
        "current_set": current_set,
        "result": result,
    }


@router.post("/api/tournaments/{tournament_id}/matches/{match_id}/scoreboard/point")
def add_point(tournament_id: int, match_id: int, data: SetPointRequest, db: DBSession = Depends(get_db)):
    get_match(db, tournament_id, match_id)

    if data.team not in ("a", "b"):
        raise HTTPException(400, "team precisa ser 'a' ou 'b'")
    if data.delta not in (1, -1):
        raise HTTPException(400, "delta precisa ser 1 ou -1")

    if decided_result(db, match_id) is not None:
        raise HTTPException(400, "Partida já está decidida")

    open_set = get_open_set(db, match_id)

    field = "points_a" if data.team == "a" else "points_b"
    new_value = (getattr(open_set, field) if open_set else 0) + data.delta
    if new_value < 0:
        raise HTTPException(400, "Placar não pode ficar negativo")

    if not open_set:
        closed_count = len(get_closed_sets(db, match_id))
        next_number = closed_count + 1
        if next_number > 3:
            raise HTTPException(400, "Partida já teve 3 sets")
        open_set = TournamentSetResult(match_id=match_id, set_number=next_number)
        db.add(open_set)
        db.flush()

    setattr(open_set, field, new_value)

    db.commit()
    db.refresh(open_set)
    return serialize_set(open_set)


@router.post("/api/tournaments/{tournament_id}/matches/{match_id}/scoreboard/close-set")
def close_set(tournament_id: int, match_id: int, db: DBSession = Depends(get_db)):
    m = get_match(db, tournament_id, match_id)
    open_set = get_open_set(db, match_id)
    if not open_set:
        raise HTTPException(400, "Não há set em aberto")

    target = SET_TARGETS.get(open_set.set_number, 18)
    if not is_set_over(open_set.points_a, open_set.points_b, target):
        raise HTTPException(400, "O set ainda não terminou")

    open_set.closed = True
    db.flush()

    if decided_result(db, match_id) is not None:
        m.status = "encerrado"

    db.commit()
    db.refresh(open_set)
    return serialize_set(open_set)


@router.get("/api/tournaments/{tournament_id}/standings")
def get_standings(tournament_id: int, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    teams = db.execute(
        select(Team).where(Team.tournament_id == tournament_id).order_by(Team.code)
    ).scalars().all()
    team_codes = {team.id: team.code for team in teams}

    finished_matches = db.execute(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.status == "encerrado",
            TournamentMatch.is_final == False,
        )
    ).scalars().all()

    engine_matches = []
    for m in finished_matches:
        if decided_result(db, m.id) is None:
            continue
        sets = get_closed_sets(db, m.id)
        engine_matches.append(SimpleNamespace(
            team_a=team_codes.get(m.team_a_id),
            team_b=team_codes.get(m.team_b_id),
            sets=[(s.points_a, s.points_b) for s in sets],
        ))

    standings = compute_standings(engine_matches)

    present_codes = {row["team"] for row in standings}
    for code in team_codes.values():
        if code not in present_codes:
            standings.append({
                "team": code,
                "wins": 0, "losses": 0,
                "sets_for": 0, "sets_against": 0, "sets_balance": 0,
                "points_for": 0, "points_against": 0, "points_balance": 0,
                "tournament_points": 0, "tied": False,
            })

    return standings


@router.post("/api/tournaments/{tournament_id}/generate-final")
def generate_final(tournament_id: int, data: GenerateFinalRequest, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)

    existing_final = db.execute(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.is_final == True,
        )
    ).scalar_one_or_none()
    if existing_final:
        raise HTTPException(409, "A final já foi cadastrada")

    group_matches = db.execute(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.is_final == False,
        )
    ).scalars().all()
    if not group_matches:
        raise HTTPException(400, "Nenhum jogo de fase de grupos cadastrado")
    # A match can be marked "encerrado" by hand (the Encerrar button) with no
    # real decided result - checking the status alone isn't enough, since
    # get_standings silently drops such a match and the standings below
    # wouldn't reflect it. Require every group match to actually be decided.
    if any(decided_result(db, m.id) is None for m in group_matches):
        raise HTTPException(400, "Ainda há jogos da fase de grupos sem resultado decidido")

    standings = get_standings(tournament_id, db)
    if len(standings) < 2:
        raise HTTPException(400, "É preciso pelo menos 2 times na classificação")
    # standings[0]["tied"] catches a tie for 1st; standings[1]["tied"] catches
    # a tie for 2nd (e.g. two teams tied with each other, both behind a clear
    # 1st) - either way, picking a runner-up would be arbitrary.
    if standings[0]["tied"] or standings[1]["tied"]:
        raise HTTPException(400, "Empate na classificação — decida manualmente e cadastre a final")

    teams_by_code = {
        team.code: team.id
        for team in db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars()
    }
    team_a_id = teams_by_code[standings[0]["team"]]
    team_b_id = teams_by_code[standings[1]["team"]]
    if team_a_id == team_b_id:
        raise HTTPException(400, "Os dois times não podem ser o mesmo")

    m = TournamentMatch(
        tournament_id=tournament_id,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        scheduled_at=data.scheduled_at,
        court=data.court,
        is_final=True,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m
