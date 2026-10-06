from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Team, TournamentMatch, TournamentSetResult
from .schemas import (
    TournamentMatchCreate, TournamentMatchUpdate, SetPointRequest,
    GenerateSemifinalsRequest, GenerateFinalsRequest,
)
from .services.tournament_engine import SET_TARGETS, is_set_over, match_result, compute_standings, mark_qualified
from .tournament import get_tournament

router = APIRouter()

MATCH_STATUSES = {"agendado", "em_andamento", "encerrado"}

STAGES = {"grupos", "semifinal_1", "semifinal_2", "terceiro_lugar", "final"}
# Knockout stages happen once per tournament; group games repeat.
KNOCKOUT_STAGES = STAGES - {"grupos"}


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
        "match": {"id": m.id, "status": m.status, "is_final": m.is_final, "stage": m.stage},
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


def group_standings(db, tournament_id, teams):
    """Standings among `teams` only (one group). Returns (rows, complete),
    where complete means every pair of teams has a decided match."""
    team_codes = {team.id: team.code for team in teams}

    finished_matches = db.execute(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == tournament_id,
            TournamentMatch.status == "encerrado",
            TournamentMatch.stage == "grupos",
        )
    ).scalars().all()

    engine_matches = []
    played_pairs = set()
    for m in finished_matches:
        if m.team_a_id not in team_codes or m.team_b_id not in team_codes:
            continue
        if decided_result(db, m.id) is None:
            continue
        sets = get_closed_sets(db, m.id)
        played_pairs.add(frozenset((m.team_a_id, m.team_b_id)))
        engine_matches.append(SimpleNamespace(
            team_a=team_codes[m.team_a_id],
            team_b=team_codes[m.team_b_id],
            sets=[(s.points_a, s.points_b) for s in sets],
        ))

    standings = compute_standings(engine_matches, teams=team_codes.values())

    n = len(teams)
    complete = n >= 2 and len(played_pairs) == n * (n - 1) // 2
    return standings, complete


@router.get("/api/tournaments/{tournament_id}/standings")
def get_standings(tournament_id: int, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    teams = db.execute(
        select(Team).where(Team.tournament_id == tournament_id).order_by(Team.code)
    ).scalars().all()

    by_group = {}
    for team in teams:
        by_group.setdefault(team.group_name, []).append(team)

    # Real groups first (A, B); teams not drawn yet go in a trailing None block.
    result = []
    for group in sorted(by_group, key=lambda g: (g is None, g or "")):
        rows, complete = group_standings(db, tournament_id, by_group[group])
        if group is not None and complete:
            mark_qualified(rows)
        else:
            for row in rows:
                row["qualified"] = False
        result.append({"group": group, "complete": complete, "rows": rows})

    return result


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


@router.post("/api/tournaments/{tournament_id}/generate-semifinals")
def generate_semifinals(tournament_id: int, data: GenerateSemifinalsRequest, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    if stage_match(db, tournament_id, "semifinal_1") or stage_match(db, tournament_id, "semifinal_2"):
        raise HTTPException(409, "As semifinais já foram cadastradas")

    groups = {g["group"]: g for g in get_standings(tournament_id, db)}
    teams_by_code = {
        team.code: team.id
        for team in db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars()
    }

    qualified = {}
    for name in ("A", "B"):
        group = groups.get(name)
        if group is None or not group["complete"]:
            raise HTTPException(400, f"O grupo {name} ainda não terminou")
        top = [teams_by_code[row["team"]] for row in group["rows"] if row["qualified"]]
        if len(top) < 2:
            raise HTTPException(
                400, f"Empate na classificação do grupo {name} — decida por sorteio e cadastre as semifinais à mão"
            )
        qualified[name] = top

    first_a, second_a = qualified["A"]
    first_b, second_b = qualified["B"]
    semis = [
        TournamentMatch(
            tournament_id=tournament_id, team_a_id=first_a, team_b_id=second_b,
            scheduled_at=data.semifinal_1_at, court=data.court, stage="semifinal_1",
        ),
        TournamentMatch(
            tournament_id=tournament_id, team_a_id=first_b, team_b_id=second_a,
            scheduled_at=data.semifinal_2_at, court=data.court, stage="semifinal_2",
        ),
    ]
    db.add_all(semis)
    db.commit()
    for m in semis:
        db.refresh(m)
    return semis


@router.post("/api/tournaments/{tournament_id}/generate-finals")
def generate_finals(tournament_id: int, data: GenerateFinalsRequest, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    if stage_match(db, tournament_id, "final") or stage_match(db, tournament_id, "terceiro_lugar"):
        raise HTTPException(409, "A final e o 3º lugar já foram cadastrados")

    outcomes = []
    for stage in ("semifinal_1", "semifinal_2"):
        m = stage_match(db, tournament_id, stage)
        outcome = winner_and_loser(db, m) if m else None
        if outcome is None:
            raise HTTPException(400, "As duas semifinais precisam estar decididas")
        outcomes.append(outcome)

    (win_1, lose_1), (win_2, lose_2) = outcomes
    third = TournamentMatch(
        tournament_id=tournament_id, team_a_id=lose_1, team_b_id=lose_2,
        scheduled_at=data.third_place_at, court=data.court, stage="terceiro_lugar",
    )
    final = TournamentMatch(
        tournament_id=tournament_id, team_a_id=win_1, team_b_id=win_2,
        scheduled_at=data.final_at, court=data.court, stage="final", is_final=True,
    )
    db.add_all([third, final])
    db.commit()
    db.refresh(third)
    db.refresh(final)
    return [third, final]


@router.get("/api/tournaments/{tournament_id}/podium")
def get_podium(tournament_id: int, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    codes = {
        team.id: team.code
        for team in db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars()
    }

    def code_of(team_id):
        return codes.get(team_id) if team_id is not None else None

    final = stage_match(db, tournament_id, "final")
    third = stage_match(db, tournament_id, "terceiro_lugar")
    final_outcome = winner_and_loser(db, final) if final else None
    third_outcome = winner_and_loser(db, third) if third else None

    return {
        "champion": code_of(final_outcome[0]) if final_outcome else None,
        "runner_up": code_of(final_outcome[1]) if final_outcome else None,
        "third_place": code_of(third_outcome[0]) if third_outcome else None,
    }
