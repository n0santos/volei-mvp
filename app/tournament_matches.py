from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Team, TournamentMatch, TournamentSetResult
from .schemas import (
    TournamentMatchCreate, TournamentMatchUpdate, SetPointRequest,
    GenerateSemifinalsRequest, GenerateFinalRequest, WalkoverRequest, DrawRequest,
)
from .services.tournament_engine import (
    SET_TARGETS, DRAW_SLOTS, DRAW_FIXTURES, QUALIFIED,
    is_set_over, match_result, compute_standings, mark_qualified,
)
from .tournament import get_tournament

router = APIRouter()

MATCH_STATUSES = {"agendado", "em_andamento", "encerrado"}

# "grupos" is the qualifying round (all teams in one table); the name is kept because it is stored in existing rows.
STAGES = {"grupos", "semifinal_1", "semifinal_2", "final"}
# Knockout stages happen once per tournament; qualifying games repeat.
KNOCKOUT_STAGES = STAGES - {"grupos"}
# Position in the tournament: a stage can't be undone once a later one exists.
STAGE_ORDER = {"grupos": 0, "semifinal_1": 1, "semifinal_2": 1, "final": 2}

WALKOVER_POINTS = 15  # regulation: a W.O. is 2x0 with partials of 15x0 and 15x0


def get_tournament_team(db, tournament_id, team_id):
    team = db.execute(
        select(Team).where(Team.id == team_id, Team.tournament_id == tournament_id)
    ).scalar_one_or_none()
    if not team:
        raise HTTPException(404, "Time não encontrado neste torneio")
    return team


def check_stage_free(db, tournament_id, stage, ignore_match_id=None):
    if stage not in STAGES:
        raise HTTPException(400, "Fase inválida")
    if stage not in KNOCKOUT_STAGES:
        return
    query = select(TournamentMatch).where(
        TournamentMatch.tournament_id == tournament_id,
        TournamentMatch.stage == stage,
    )
    if ignore_match_id is not None:
        query = query.where(TournamentMatch.id != ignore_match_id)
    if db.execute(query).first():
        raise HTTPException(409, "Essa fase já tem um jogo cadastrado")


@router.post("/api/tournaments/{tournament_id}/matches")
def create_match(tournament_id: int, data: TournamentMatchCreate, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    get_tournament_team(db, tournament_id, data.team_a_id)
    get_tournament_team(db, tournament_id, data.team_b_id)
    if data.team_a_id == data.team_b_id:
        raise HTTPException(400, "Os dois times não podem ser o mesmo")
    check_stage_free(db, tournament_id, data.stage)

    m = TournamentMatch(
        tournament_id=tournament_id,
        team_a_id=data.team_a_id,
        team_b_id=data.team_b_id,
        scheduled_at=data.scheduled_at,
        court=data.court,
        stage=data.stage,
        is_final=data.stage == "final",
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

    results = {m.id: decided_result(db, m.id) for m in matches}

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
            "stage": m.stage,
            "walkover": m.walkover,
            "sets_a": results[m.id]["sets_a"] if results[m.id] else None,
            "sets_b": results[m.id]["sets_b"] if results[m.id] else None,
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
    if data.stage is not None:
        check_stage_free(db, tournament_id, data.stage, ignore_match_id=m.id)
        m.stage = data.stage
        m.is_final = data.stage == "final"

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


@router.post("/api/tournaments/{tournament_id}/matches/{match_id}/walkover")
def set_walkover(tournament_id: int, match_id: int, data: WalkoverRequest, db: DBSession = Depends(get_db)):
    m = get_match(db, tournament_id, match_id)
    if data.present not in ("a", "b"):
        raise HTTPException(400, "present precisa ser 'a' ou 'b'")
    if db.execute(select(TournamentSetResult).where(TournamentSetResult.match_id == m.id)).first():
        raise HTTPException(409, "O jogo já tem placar registrado")

    points_a, points_b = (WALKOVER_POINTS, 0) if data.present == "a" else (0, WALKOVER_POINTS)
    for set_number in (1, 2):
        db.add(TournamentSetResult(
            match_id=m.id, set_number=set_number, points_a=points_a, points_b=points_b, closed=True,
        ))
    m.status = "encerrado"
    m.walkover = True
    db.commit()
    db.refresh(m)
    return m


@router.delete("/api/tournaments/{tournament_id}/matches/{match_id}/walkover")
def undo_walkover(tournament_id: int, match_id: int, db: DBSession = Depends(get_db)):
    m = get_match(db, tournament_id, match_id)
    if not m.walkover:
        raise HTTPException(409, "Este jogo não foi decidido por W.O.")

    later = db.execute(
        select(TournamentMatch).where(TournamentMatch.tournament_id == tournament_id)
    ).scalars().all()
    if any(STAGE_ORDER[other.stage] > STAGE_ORDER[m.stage] for other in later):
        raise HTTPException(409, "Já existem jogos de fases seguintes; não dá para desfazer este W.O.")

    db.execute(delete(TournamentSetResult).where(TournamentSetResult.match_id == m.id))
    m.status = "agendado"
    m.walkover = False
    db.commit()
    db.refresh(m)
    return m


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
        "match": {"id": m.id, "status": m.status, "is_final": m.is_final, "stage": m.stage, "walkover": m.walkover},
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


def qualifying_standings(db, tournament_id, teams):
    """The overall table over all `teams`. Returns (rows, complete), where
    complete means every game of the draw (len(DRAW_FIXTURES)) is decided."""
    team_codes = {team.id: team.code for team in teams}

    finished_matches = db.execute(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.status == "encerrado",
            TournamentMatch.stage == "grupos",
        )
    ).scalars().all()

    engine_matches = []
    for m in finished_matches:
        if m.team_a_id not in team_codes or m.team_b_id not in team_codes:
            continue
        if decided_result(db, m.id) is None:
            continue
        sets = get_closed_sets(db, m.id)
        engine_matches.append(SimpleNamespace(
            team_a=team_codes[m.team_a_id],
            team_b=team_codes[m.team_b_id],
            sets=[(s.points_a, s.points_b) for s in sets],
        ))

    standings = compute_standings(engine_matches, teams=team_codes.values())
    return standings, len(engine_matches) >= len(DRAW_FIXTURES)


@router.get("/api/tournaments/{tournament_id}/standings")
def get_standings(tournament_id: int, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    teams = db.execute(
        select(Team).where(Team.tournament_id == tournament_id).order_by(Team.code)
    ).scalars().all()

    rows, complete = qualifying_standings(db, tournament_id, teams)
    if complete:
        mark_qualified(rows, QUALIFIED)
    else:
        for row in rows:
            row["qualified"] = False
    return {"complete": complete, "rows": rows}


def stage_match(db, tournament_id, stage):
    return db.execute(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.stage == stage,
        )
    ).scalar_one_or_none()


def winner_and_loser(db, m):
    """(winner_team_id, loser_team_id) of a decided match, else None."""
    result = decided_result(db, m.id)
    if result is None:
        return None
    if result["winner"] == "A":
        return m.team_a_id, m.team_b_id
    return m.team_b_id, m.team_a_id


@router.post("/api/tournaments/{tournament_id}/draw")
def register_draw(tournament_id: int, data: DrawRequest, db: DBSession = Depends(get_db)):
    """Turn the draw (slot A-F -> team) into the qualifying games. Replaces
    qualifying games that haven't started; refuses if any has a result."""
    get_tournament(db, tournament_id)
    if set(data.slots) != set(DRAW_SLOTS):
        raise HTTPException(400, "O sorteio precisa definir as posições A, B, C, D, E e F")
    if len(set(data.slots.values())) != len(DRAW_SLOTS):
        raise HTTPException(400, "Cada equipe só pode aparecer uma vez no sorteio")
    if len(data.times) != len(DRAW_FIXTURES):
        raise HTTPException(400, f"Informe os {len(DRAW_FIXTURES)} horários dos jogos")

    teams = list(db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars())
    if len({team.id for team in teams} & set(data.slots.values())) != len(DRAW_SLOTS):
        raise HTTPException(404, "Equipe do sorteio não encontrada neste torneio")
    if len(teams) != len(DRAW_SLOTS):
        raise HTTPException(409, "Este formato precisa de exatamente 6 equipes no torneio")

    existing = db.execute(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.stage == "grupos",
        )
    ).scalars().all()
    for m in existing:
        started = db.execute(
            select(TournamentSetResult).where(TournamentSetResult.match_id == m.id)
        ).first() is not None
        if m.status != "agendado" or started or m.walkover:
            raise HTTPException(409, "Já há jogo da classificatória iniciado ou encerrado")
    for m in existing:
        db.execute(delete(TournamentSetResult).where(TournamentSetResult.match_id == m.id))
        db.delete(m)

    created = [
        TournamentMatch(
            tournament_id=tournament_id,
            team_a_id=data.slots[a], team_b_id=data.slots[b],
            scheduled_at=when, stage="grupos",
        )
        for (a, b), when in zip(DRAW_FIXTURES, data.times)
    ]
    db.add_all(created)
    db.commit()
    for m in created:
        db.refresh(m)
    return created


@router.post("/api/tournaments/{tournament_id}/generate-semifinals")
def generate_semifinals(tournament_id: int, data: GenerateSemifinalsRequest, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    if stage_match(db, tournament_id, "semifinal_1") or stage_match(db, tournament_id, "semifinal_2"):
        raise HTTPException(409, "As semifinais já foram cadastradas")

    table = get_standings(tournament_id, db)
    if not table["complete"]:
        raise HTTPException(400, "A classificatória ainda não terminou")
    teams_by_code = {
        team.code: team.id
        for team in db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars()
    }
    top = [teams_by_code[row["team"]] for row in table["rows"] if row["qualified"]]
    if len(top) < QUALIFIED:
        raise HTTPException(
            400, "Empate na classificação — decida por sorteio e cadastre as semifinais à mão"
        )

    first, second, third, fourth = top
    semis = [
        TournamentMatch(
            tournament_id=tournament_id, team_a_id=first, team_b_id=fourth,
            scheduled_at=data.semifinal_1_at, court=data.court, stage="semifinal_1",
        ),
        TournamentMatch(
            tournament_id=tournament_id, team_a_id=second, team_b_id=third,
            scheduled_at=data.semifinal_2_at, court=data.court, stage="semifinal_2",
        ),
    ]
    db.add_all(semis)
    db.commit()
    for m in semis:
        db.refresh(m)
    return semis


@router.post("/api/tournaments/{tournament_id}/generate-final")
def generate_final(tournament_id: int, data: GenerateFinalRequest, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    if stage_match(db, tournament_id, "final"):
        raise HTTPException(409, "A final já foi cadastrada")

    winners = []
    for stage in ("semifinal_1", "semifinal_2"):
        m = stage_match(db, tournament_id, stage)
        outcome = winner_and_loser(db, m) if m else None
        if outcome is None:
            raise HTTPException(400, "As duas semifinais precisam estar decididas")
        winners.append(outcome[0])

    final = TournamentMatch(
        tournament_id=tournament_id, team_a_id=winners[0], team_b_id=winners[1],
        scheduled_at=data.final_at, court=data.court, stage="final", is_final=True,
    )
    db.add(final)
    db.commit()
    db.refresh(final)
    return final


@router.get("/api/tournaments/{tournament_id}/podium")
def get_podium(tournament_id: int, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    codes = {
        team.id: team.code
        for team in db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars()
    }

    final = stage_match(db, tournament_id, "final")
    outcome = winner_and_loser(db, final) if final else None
    return {
        "champion": codes.get(outcome[0]) if outcome else None,
        "runner_up": codes.get(outcome[1]) if outcome else None,
    }
