import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, delete
from sqlalchemy.orm import Session as DBSession

from .database import Base, engine, get_db, SessionLocal
from .models import Player, Session as GameSession, Attendance, Match, MatchPlayer, Event
from .schemas import PlayerCreate, SessionCreate, AttendanceUpdate, SubstituteRequest, SwapRequest
from .services.selection import select_players, eligible_players, BLOCK_AFTER, SHARE_WEIGHT
from .services.teams import balance_teams
from .services.fairness import history

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Vôlei MVP")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.get("/__health")
def health():
    return {"status": "ok"}

connections: dict[int, set[WebSocket]] = {}


async def broadcast(session_id: int):
    dead = []
    for ws in connections.get(session_id, set()):
        try:
            await ws.send_json({"type": "refresh"})
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.get(session_id, set()).discard(ws)


def get_session(db, session_id):
    s = db.get(GameSession, session_id)
    if not s:
        raise HTTPException(404, "Sessão não encontrada")
    return s


def event(db, session_id, typ, player_id=None, match_id=None, payload=None):
    db.add(Event(
        session_id=session_id,
        type=typ,
        player_id=player_id,
        match_id=match_id,
        payload=json.dumps(payload or {}, ensure_ascii=False),
    ))


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "templates" / "index.html").read_text()


@app.get("/api/players")
def players(db: DBSession = Depends(get_db)):
    return db.execute(select(Player).where(Player.active == True).order_by(Player.name)).scalars().all()


@app.post("/api/players")
def create_player(data: PlayerCreate, db: DBSession = Depends(get_db)):
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Nome obrigatório")
    exists = db.execute(select(Player).where(Player.name == name)).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "Jogador já cadastrado")
    p = Player(name=name, score=data.score, gender=data.gender.upper())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.patch("/api/players/{player_id}")
def update_player(player_id: int, data: PlayerCreate, db: DBSession = Depends(get_db)):
    p = db.get(Player, player_id)
    if not p:
        raise HTTPException(404, "Jogador não encontrado")
    p.name = data.name.strip()
    p.score = data.score
    p.gender = data.gender.upper()
    db.commit()
    return p


@app.post("/api/sessions")
async def create_session(data: SessionCreate, db: DBSession = Depends(get_db)):
    # Only one active session in the MVP.
    old = db.execute(select(GameSession).where(GameSession.active == True)).scalars().all()
    for s in old:
        s.active = False

    s = GameSession(name=data.name)
    db.add(s)
    db.flush()

    if data.player_ids is not None:
        players = db.execute(
            select(Player).where(Player.id.in_(data.player_ids), Player.active == True)
        ).scalars().all()
    else:
        players = db.execute(
            select(Player).where(Player.active == True).order_by(Player.name)
        ).scalars().all()

    for p in players:
        db.add(Attendance(session_id=s.id, player_id=p.id, status="expected"))

    db.commit()
    await broadcast(s.id)
    return {"id": s.id}


@app.get("/api/sessions/active")
def active_session(db: DBSession = Depends(get_db)):
    s = db.execute(
        select(GameSession).where(GameSession.active == True).order_by(GameSession.id.desc())
    ).scalar_one_or_none()
    return {"id": s.id, "name": s.name} if s else None


@app.get("/api/sessions/{session_id}")
def session_state(session_id: int, db: DBSession = Depends(get_db)):
    s = get_session(db, session_id)
    attendance = db.execute(
        select(Attendance, Player)
        .join(Player, Player.id == Attendance.player_id)
        .where(Attendance.session_id == session_id)
        .order_by(Attendance.arrival_order.nullslast(), Player.name)
    ).all()

    hist = history(db, session_id)
    players_data = []
    for a, p in attendance:
        h = hist[p.id]
        players_data.append({
            "id": p.id,
            "name": p.name,
            "score": p.score,
            "gender": p.gender,
            "status": a.status,
            "arrival_order": a.arrival_order,
            "matches": h["matches"],
            "minutes": round(h["minutes"], 1),
            "outside_streak": h["outside_streak"],
            "playing_streak": h["playing_streak"],
        })

    matches = db.execute(
        select(Match).where(Match.session_id == session_id).order_by(Match.number.desc())
    ).scalars().all()

    current = None
    if matches:
        m = matches[0]
        if m.status in ("proposed", "running"):
            mps = db.execute(
                select(MatchPlayer, Player)
                .join(Player, Player.id == MatchPlayer.player_id)
                .where(MatchPlayer.match_id == m.id)
            ).all()
            current = {
                "id": m.id,
                "number": m.number,
                "status": m.status,
                "started_at": m.started_at.isoformat() if m.started_at else None,
                "teams": {"A": [], "B": []},
            }
            for mp, p in mps:
                current["teams"][mp.team].append({
                    "id": p.id,
                    "name": p.name,
                    "score": p.score,
                    "gender": p.gender,
                    "role": mp.role,
                    "exited": mp.exited_at is not None,
                })

    return {
        "session": {"id": s.id, "name": s.name},
        "players": players_data,
        "current_match": current,
        "match_count": len(matches),
    }


@app.patch("/api/sessions/{session_id}/attendance/{player_id}")
async def attendance(session_id: int, player_id: int, data: AttendanceUpdate, db: DBSession = Depends(get_db)):
    get_session(db, session_id)
    a = db.execute(
        select(Attendance).where(
            Attendance.session_id == session_id,
            Attendance.player_id == player_id
        )
    ).scalar_one_or_none()
    if not a:
        # Allow adding a player outside the pre-list.
        if not db.get(Player, player_id):
            raise HTTPException(404, "Jogador não encontrado")
        a = Attendance(session_id=session_id, player_id=player_id)
        db.add(a)

    status = data.status
    if status not in {"expected", "arrived", "absent", "left"}:
        raise HTTPException(400, "Status inválido")

    a.status = status
    if status == "expected":
        # "Expected" means not here yet, so a check-in marked by mistake has to
        # be undone - otherwise the wrong arrival time keeps defining both the
        # opening line-up and the presence window fairness.history() works from.
        a.arrived_at = None
        a.arrival_order = None
    if status == "arrived" and a.arrived_at is None:
        max_order = db.execute(
            select(Attendance.arrival_order)
            .where(Attendance.session_id == session_id)
        ).scalars().all()
        a.arrival_order = max([x for x in max_order if x is not None], default=0) + 1
        a.arrived_at = datetime.utcnow()
    # Only meaningful while the player is actually gone: a left_at left behind
    # after they check in again puts every later match outside their presence
    # window, freezing both streaks at zero so selection never stops picking them.
    a.left_at = datetime.utcnow() if status == "left" else None

    event(db, session_id, f"attendance_{status}", player_id)
    db.commit()
    await broadcast(session_id)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/add-player")
async def add_player_to_session(session_id: int, data: PlayerCreate, db: DBSession = Depends(get_db)):
    get_session(db, session_id)
    name = data.name.strip()
    p = db.execute(select(Player).where(Player.name == name)).scalar_one_or_none()
    if not p:
        p = Player(name=name, score=data.score, gender=data.gender.upper())
        db.add(p)
        db.flush()
    existing = db.execute(
        select(Attendance).where(
            Attendance.session_id == session_id,
            Attendance.player_id == p.id
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(Attendance(session_id=session_id, player_id=p.id, status="expected"))
    db.commit()
    await broadcast(session_id)
    return p


@app.post("/api/sessions/{session_id}/generate")
async def generate_match(session_id: int, db: DBSession = Depends(get_db)):
    get_session(db, session_id)
    # Only one proposed/running match at a time.
    current = db.execute(
        select(Match).where(
            Match.session_id == session_id,
            Match.status.in_(["proposed", "running"])
        )
    ).scalar_one_or_none()
    if current:
        raise HTTPException(409, "Já existe uma partida aberta")

    chosen = select_players(db, session_id, 12)
    if len(chosen) < 2:
        raise HTTPException(400, "É preciso ter pelo menos 2 jogadores presentes")

    a, b, diff = balance_teams(chosen)

    last_num = db.execute(
        select(Match.number).where(Match.session_id == session_id)
    ).scalars().all()
    number = max(last_num, default=0) + 1

    m = Match(session_id=session_id, number=number, status="proposed")
    db.add(m)
    db.flush()

    for p in a:
        db.add(MatchPlayer(match_id=m.id, player_id=p.id, team="A", role="starter"))
    for p in b:
        db.add(MatchPlayer(match_id=m.id, player_id=p.id, team="B", role="starter"))

    event(db, session_id, "match_generated", match_id=m.id, payload={
        "team_a_score": sum(p.score for p in a),
        "team_b_score": sum(p.score for p in b),
        "difference": diff,
    })
    db.commit()
    await broadcast(session_id)
    return {"match_id": m.id}


@app.post("/api/matches/{match_id}/start")
async def start_match(match_id: int, db: DBSession = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "Partida não encontrada")
    now = datetime.utcnow()
    m.status = "running"
    m.started_at = now
    for mp in db.execute(select(MatchPlayer).where(MatchPlayer.match_id == m.id)).scalars():
        mp.entered_at = now
    event(db, m.session_id, "match_started", match_id=m.id)
    db.commit()
    await broadcast(m.session_id)
    return {"ok": True}


@app.post("/api/matches/{match_id}/exit/{player_id}")
async def exit_player(match_id: int, player_id: int, db: DBSession = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m or m.status != "running":
        raise HTTPException(400, "Partida não está em andamento")
    mp = db.execute(
        select(MatchPlayer).where(
            MatchPlayer.match_id == match_id,
            MatchPlayer.player_id == player_id
        )
    ).scalar_one_or_none()
    if not mp:
        raise HTTPException(404, "Jogador não está na partida")
    mp.exited_at = datetime.utcnow()
    event(db, m.session_id, "player_left_match", player_id, match_id)
    db.commit()
    await broadcast(m.session_id)
    return {"ok": True}


@app.get("/api/matches/{match_id}/substitutes")
def substitutes(match_id: int, db: DBSession = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "Partida não encontrada")

    current = {
        mp.player_id for mp in db.execute(
            select(MatchPlayer).where(MatchPlayer.match_id == match_id)
        ).scalars()
    }

    candidates = []
    resting = []
    hist = history(db, m.session_id)
    for a, p in eligible_players(db, m.session_id):
        if p.id in current:
            continue
        h = hist[p.id]
        # Substitution score: prioritize waiting, then whoever has been skipped most.
        cost = h["playing_streak"] * 100 + h["share"] * SHARE_WEIGHT - h["outside_streak"] * 500
        entry = {
            "id": p.id,
            "name": p.name,
            "score": p.score,
            "outside_streak": h["outside_streak"],
            "playing_streak": h["playing_streak"],
            "matches": h["matches"],
            "cost": cost,
        }
        # Walking on would be a third match in a row, which the group rules out.
        (resting if h["playing_streak"] >= BLOCK_AFTER else candidates).append(entry)

    # Mid-match the alternative is playing a man short, so an emergency can
    # override the bench. Before the match starts there is no emergency: a
    # voluntary swap never buys anyone a third match in a row.
    if not candidates and m.status == "running":
        candidates = resting

    return sorted(candidates, key=lambda x: x["cost"])[:8]


@app.post("/api/matches/{match_id}/substitute")
async def substitute(match_id: int, data: SubstituteRequest, db: DBSession = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m or m.status != "running":
        raise HTTPException(400, "Partida não está em andamento")

    rows = db.execute(
        select(MatchPlayer).where(MatchPlayer.match_id == match_id)
    ).scalars().all()

    # A team whose replacement already walked on is back to full, so the next
    # substitute belongs to the other one - otherwise two people leaving before
    # anyone comes back would both be replaced on the same side.
    team_size = Counter(mp.team for mp in rows if mp.role == "starter")
    on_court = Counter(mp.team for mp in rows if mp.exited_at is None)
    vacancies = sorted(
        (mp for mp in rows if mp.exited_at is not None),
        key=lambda mp: mp.exited_at,
        reverse=True,
    )
    mp_exit = next(
        (mp for mp in vacancies if on_court[mp.team] < team_size[mp.team]), None
    )
    if not mp_exit:
        raise HTTPException(400, "Nenhuma vaga de substituição registrada")
    player = db.get(Player, data.player_id)
    if not player:
        raise HTTPException(404, "Jogador não encontrado")

    existing = db.execute(
        select(MatchPlayer).where(
            MatchPlayer.match_id == match_id,
            MatchPlayer.player_id == data.player_id
        )
    ).scalar_one_or_none()
    if existing and existing.exited_at is None:
        raise HTTPException(400, "Jogador já está em quadra")

    now = datetime.utcnow()
    new_mp = MatchPlayer(
        match_id=match_id,
        player_id=data.player_id,
        team=mp_exit.team,
        role="substitute",
        entered_at=now,
    )
    db.add(new_mp)
    event(db, m.session_id, "player_substituted", data.player_id, match_id, {
        "replaced_player_id": mp_exit.player_id,
        "team": mp_exit.team,
    })
    db.commit()
    await broadcast(m.session_id)
    return {"ok": True}


@app.post("/api/matches/{match_id}/swap")
async def swap_player(match_id: int, data: SwapRequest, db: DBSession = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m or m.status != "proposed":
        raise HTTPException(400, "Só dá para trocar antes da partida começar")

    slot = db.execute(
        select(MatchPlayer).where(
            MatchPlayer.match_id == match_id,
            MatchPlayer.player_id == data.out_player_id,
        )
    ).scalar_one_or_none()
    if not slot:
        raise HTTPException(404, "Jogador não está na partida")

    taken = db.execute(
        select(MatchPlayer).where(
            MatchPlayer.match_id == match_id,
            MatchPlayer.player_id == data.in_player_id,
        )
    ).scalar_one_or_none()
    if taken:
        raise HTTPException(400, "Jogador já está na partida")

    present = db.execute(
        select(Attendance).where(
            Attendance.session_id == m.session_id,
            Attendance.player_id == data.in_player_id,
            Attendance.status == "arrived",
        )
    ).scalar_one_or_none()
    if not present:
        raise HTTPException(400, "Jogador não está presente")

    if history(db, m.session_id)[data.in_player_id]["playing_streak"] >= BLOCK_AFTER:
        raise HTTPException(400, "Jogador já jogou duas seguidas e está de fora desta")

    slot.player_id = data.in_player_id
    event(db, m.session_id, "player_swapped", data.in_player_id, match_id, {
        "replaced_player_id": data.out_player_id,
        "team": slot.team,
    })
    db.commit()
    await broadcast(m.session_id)
    return {"ok": True}


@app.post("/api/matches/{match_id}/finish")
async def finish_match(match_id: int, db: DBSession = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404, "Partida não encontrada")
    now = datetime.utcnow()
    m.status = "finished"
    m.ended_at = now

    for mp in db.execute(select(MatchPlayer).where(MatchPlayer.match_id == m.id)).scalars():
        if mp.entered_at and mp.exited_at is None:
            mp.exited_at = now

    event(db, m.session_id, "match_finished", match_id=m.id)
    db.commit()
    await broadcast(m.session_id)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/reset-current")
async def reset_current(session_id: int, db: DBSession = Depends(get_db)):
    m = db.execute(
        select(Match).where(
            Match.session_id == session_id,
            Match.status.in_(["proposed", "running"])
        )
    ).scalar_one_or_none()
    if m:
        db.execute(delete(MatchPlayer).where(MatchPlayer.match_id == m.id))
        db.delete(m)
        db.commit()
    await broadcast(session_id)
    return {"ok": True}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: int):
    await websocket.accept()
    connections.setdefault(session_id, set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections.get(session_id, set()).discard(websocket)
