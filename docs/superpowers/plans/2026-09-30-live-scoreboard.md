# Placar ao Vivo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an organizer score a tournament match live — points per set, manual set/match close, automatic match-finish — and let anyone with the link watch it update via polling.

**Architecture:** First, a pure refactor (no behavior change): split `TournamentMatch`'s existing CRUD routes out of `app/tournament.py` into a new `app/tournament_matches.py`, as recommended by the previous sub-project's final review. Then add a `TournamentSetResult` model and three scoreboard routes to that new file, finally wiring up `app/services/tournament_engine.py` (`is_set_over`, `match_result`) for real for the first time. A new standalone page (`/torneio/partidas/{match_id}`) handles the live scoring UI, reached via a link from the existing "Jogos" list.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-live-scoreboard-design.md`

## Global Constraints

- No point-event log — the set's `points_a`/`points_b` are two plain counters, mutated by +1/-1. "Desfazer" is pressing -1 on the side that was wrong. A point can never make a score go negative (400 if it would).
- Closing a set requires `is_set_over` (from `app/services/tournament_engine.py`) to be true — 400 otherwise. No automatic set-close.
- Closing the deciding set (2 sets won by one side, via `match_result`) automatically sets `TournamentMatch.status = "encerrado"`.
- No undo for a closed set.
- The server computes `is_over` for the current set and returns it in the scoreboard payload — the UI reads that boolean, it does not reimplement the volleyball rule itself.
- No WebSocket — the scoreboard page polls on a plain `setInterval`.
- `app/tournament.py` keeps only tournament/team/roster/formation routes after this plan's Task 1; everything about `TournamentMatch` (CRUD and scoreboard) lives in `app/tournament_matches.py`.
- No type hints, no dataclasses in router/model code — matches the rest of the codebase.
- New CSS for the scoreboard page's big touch targets is in scope for this sub-project specifically (the first page in this app that needs them) — everything else still reuses existing classes.

---

### Task 1: Refactor — split match routes into `app/tournament_matches.py`

**Files:**
- Create: `app/tournament_matches.py`
- Modify: `app/tournament.py`
- Modify: `app/main.py`
- Modify: `tests/test_tournament_matches.py`

**Interfaces:**
- Produces: `router` (a new `APIRouter` in `app/tournament_matches.py`) carrying `get_tournament_team`, `MATCH_STATUSES`, `create_match`, `list_matches`, `get_match`, `update_match`, `delete_match` — moved verbatim from `app/tournament.py`, same signatures, same behavior. `app/tournament_matches.py` imports `get_tournament` from `app/tournament.py` (the one cross-file dependency).
- No behavior change — this task adds no new functionality and no new tests. The existing test suite (104 backend tests before this task — wait, no: this repo's actual current total, whatever it is; don't assume a number, see Step 4) must pass identically afterward, just importing from the new module path.

- [ ] **Step 1: Create the new router file**

```python
# app/tournament_matches.py
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
```

- [ ] **Step 2: Remove the moved code from `app/tournament.py` and trim its imports**

Change:

```python
from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player, TournamentMatch
from .schemas import (
    TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamFormRequest,
    TournamentMatchCreate, TournamentMatchUpdate,
)
from .services.team_formation import form_teams
```

to:

```python
from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player
from .schemas import TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamFormRequest
from .services.team_formation import form_teams
```

Then delete this entire block from the end of `app/tournament.py` (everything from `MATCH_STATUSES = ...` to the end of `delete_match`) — it now lives in `app/tournament_matches.py`:

```python
MATCH_STATUSES = {"agendado", "em_andamento", "encerrado"}


def get_tournament_team(db, tournament_id, team_id):
    ...
```

(the full block being deleted is exactly the content Step 1 shows, minus the `router = APIRouter()` line and imports — `app/tournament.py` keeps its own `router` for the routes still defined above this deleted block).

- [ ] **Step 3: Mount the new router in `app/main.py`**

Change:

```python
from .services.fairness import history
from .tournament import router as tournament_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Vôlei MVP")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(tournament_router)
```

to:

```python
from .services.fairness import history
from .tournament import router as tournament_router
from .tournament_matches import router as tournament_matches_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Vôlei MVP")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(tournament_router)
app.include_router(tournament_matches_router)
```

- [ ] **Step 4: Update the test file's import**

In `tests/test_tournament_matches.py`, change:

```python
from app.tournament import create_match, list_matches, update_match, delete_match
```

to:

```python
from app.tournament_matches import create_match, list_matches, update_match, delete_match
```

- [ ] **Step 5: Run the full suite and confirm the count is unchanged from before this task**

Run: `pytest` (or `python -m pytest` if the bare binary doesn't resolve the `app` package in this environment — check both, use whichever works, same as prior sub-projects hit this same environment quirk)
Expected: PASS, same total test count as on `main` before this task — this is a pure move, no tests added or removed. Note the count for reference in later steps of this plan.

- [ ] **Step 6: Commit**

```bash
git add app/tournament.py app/tournament_matches.py app/main.py tests/test_tournament_matches.py
git commit -m "Placar: move rotas de TournamentMatch para app/tournament_matches.py"
```

---

### Task 2: `TournamentSetResult` model and point-request schema

**Files:**
- Modify: `app/models.py`
- Modify: `app/schemas.py`
- Modify: `tests/test_tournament_matches.py`

**Interfaces:**
- Produces: `TournamentSetResult` (`id`, `match_id`, `set_number`, `points_a` default `0`, `points_b` default `0`, `closed` default `False`) in `app/models.py`. `SetPointRequest` (`team: str`, `delta: int`) in `app/schemas.py`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_tournament_matches.py
# Add TournamentSetResult to the existing "from app.models import Tournament, Team, TournamentMatch" line.


def test_set_result_roundtrip():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
    )
    db.add(m)
    db.flush()

    s = TournamentSetResult(match_id=m.id, set_number=1, points_a=18, points_b=16, closed=True)
    db.add(s)
    db.commit()

    saved = db.query(TournamentSetResult).filter_by(match_id=m.id).one()
    assert saved.set_number == 1
    assert saved.points_a == 18
    assert saved.points_b == 16
    assert saved.closed is True


def test_set_result_defaults():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
    )
    db.add(m)
    db.flush()

    s = TournamentSetResult(match_id=m.id, set_number=1)
    db.add(s)
    db.commit()

    assert s.points_a == 0
    assert s.points_b == 0
    assert s.closed is False
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_matches.py -v` (or `python -m pytest ...`)
Expected: FAIL — `ImportError: cannot import name 'TournamentSetResult' from 'app.models'`

- [ ] **Step 3: Write the implementation**

In `app/models.py`, `Integer`, `Boolean`, `ForeignKey` are already imported — no import line changes needed. Append at the end of the file:

```python
class TournamentSetResult(Base):
    __tablename__ = "tournament_set_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("tournament_matches.id"))
    set_number: Mapped[int]
    points_a: Mapped[int] = mapped_column(Integer, default=0)
    points_b: Mapped[int] = mapped_column(Integer, default=0)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
```

In `app/schemas.py`, append at the end of the file:

```python
class SetPointRequest(BaseModel):
    team: str
    delta: int
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_matches.py -v`
Expected: PASS (2 new tests, plus all the pre-existing ones in this file still passing)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests — Task 1's noted count + 2)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/schemas.py tests/test_tournament_matches.py
git commit -m "Placar: modelo TournamentSetResult e schema SetPointRequest"
```

---

### Task 3: Scoreboard routes

**Files:**
- Modify: `app/tournament_matches.py`
- Modify: `tests/test_tournament_matches.py`

**Interfaces:**
- Consumes: `TournamentSetResult` (Task 2), `SetPointRequest` (Task 2), `get_match` (Task 1, same module), `SET_TARGETS`/`is_set_over`/`match_result` (`app/services/tournament_engine.py`, unmodified).
- Produces: `get_scoreboard(tournament_id, match_id, db)`, `add_point(tournament_id, match_id, data, db)`, `close_set(tournament_id, match_id, db)`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_tournament_matches.py
# Update the existing "from app.tournament_matches import ..." line to also bring in
# get_scoreboard, add_point, close_set. Update the existing "from app.schemas import ..."
# line to also bring in SetPointRequest.


def make_match(db, tournament_id, team_a_id, team_b_id):
    return create_match(
        tournament_id,
        TournamentMatchCreate(team_a_id=team_a_id, team_b_id=team_b_id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )


def test_first_point_creates_set_one():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)

    board = get_scoreboard(t.id, m.id, db)
    assert len(board["sets"]) == 1
    assert board["sets"][0]["set_number"] == 1
    assert board["sets"][0]["points_a"] == 1
    assert board["current_set"]["points_a"] == 1
    assert board["current_set"]["target"] == 18
    assert board["current_set"]["is_over"] is False


def test_point_cannot_go_negative():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    with pytest.raises(HTTPException) as exc_info:
        add_point(t.id, m.id, SetPointRequest(team="a", delta=-1), db)
    assert exc_info.value.status_code == 400


def test_close_set_requires_set_to_be_over():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)
    add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)

    with pytest.raises(HTTPException) as exc_info:
        close_set(t.id, m.id, db)
    assert exc_info.value.status_code == 400


def test_close_set_and_start_next():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)

    closed = close_set(t.id, m.id, db)
    assert closed["closed"] is True
    assert closed["set_number"] == 1

    add_point(t.id, m.id, SetPointRequest(team="b", delta=1), db)
    board = get_scoreboard(t.id, m.id, db)
    assert board["current_set"]["set_number"] == 2
    assert board["current_set"]["points_b"] == 1


def test_match_finishes_and_status_updates_after_two_sets():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    close_set(t.id, m.id, db)

    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    close_set(t.id, m.id, db)

    board = get_scoreboard(t.id, m.id, db)
    assert board["result"]["winner"] == "A"
    assert board["result"]["sets_a"] == 2
    assert board["current_set"] is None

    db.refresh(m)
    assert m.status == "encerrado"


def test_cannot_add_point_after_match_decided():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    close_set(t.id, m.id, db)
    for _ in range(18):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    close_set(t.id, m.id, db)

    with pytest.raises(HTTPException) as exc_info:
        add_point(t.id, m.id, SetPointRequest(team="a", delta=1), db)
    assert exc_info.value.status_code == 400


def test_invalid_team_and_delta_rejected():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = make_match(db, t.id, team_a.id, team_b.id)

    with pytest.raises(HTTPException):
        add_point(t.id, m.id, SetPointRequest(team="c", delta=1), db)
    with pytest.raises(HTTPException):
        add_point(t.id, m.id, SetPointRequest(team="a", delta=2), db)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_matches.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_scoreboard' from 'app.tournament_matches'`; Tasks 1-2's tests in this file still pass.

- [ ] **Step 3: Write the implementation**

In `app/tournament_matches.py`, change:

```python
from .database import get_db
from .models import Team, TournamentMatch
from .schemas import TournamentMatchCreate, TournamentMatchUpdate
from .tournament import get_tournament
```

to:

```python
from .database import get_db
from .models import Team, TournamentMatch, TournamentSetResult
from .schemas import TournamentMatchCreate, TournamentMatchUpdate, SetPointRequest
from .services.tournament_engine import SET_TARGETS, is_set_over, match_result
from .tournament import get_tournament
```

Then append at the end of the file:

```python
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
        target = SET_TARGETS.get(open_set.set_number, 15)
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
    if not open_set:
        closed_count = len(get_closed_sets(db, match_id))
        next_number = closed_count + 1
        if next_number > 3:
            raise HTTPException(400, "Partida já teve 3 sets")
        open_set = TournamentSetResult(match_id=match_id, set_number=next_number)
        db.add(open_set)
        db.flush()

    field = "points_a" if data.team == "a" else "points_b"
    new_value = getattr(open_set, field) + data.delta
    if new_value < 0:
        raise HTTPException(400, "Placar não pode ficar negativo")
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

    target = SET_TARGETS.get(open_set.set_number, 15)
    if not is_set_over(open_set.points_a, open_set.points_b, target):
        raise HTTPException(400, "O set ainda não terminou")

    open_set.closed = True
    db.flush()

    if decided_result(db, match_id) is not None:
        m.status = "encerrado"

    db.commit()
    db.refresh(open_set)
    return serialize_set(open_set)
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_matches.py -v`
Expected: PASS (7 new tests, plus all pre-existing ones in this file)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/tournament_matches.py tests/test_tournament_matches.py
git commit -m "Placar: rotas de placar ao vivo (ponto, fechar set)"
```

---

### Task 4: UI — live scoreboard page

**Files:**
- Modify: `app/main.py`
- Create: `app/templates/partida.html`
- Create: `app/static/partida.js`
- Modify: `app/static/torneio.js`
- Modify: `app/static/style.css`

**Interfaces:**
- Consumes: `GET/POST` scoreboard routes (Task 3), `GET /api/tournaments/active`, `GET /api/tournaments/{id}/matches` (existing).
- Produces: nothing for a later task — this is the sub-project's last task.

No pytest tests — same reasoning as every other UI task in this feature (no JS test harness in this repo). Verification is a manual smoke check plus the full pytest suite.

- [ ] **Step 1: Add the page route**

In `app/main.py`, change:

```python
@app.get("/torneio", response_class=HTMLResponse)
def torneio_page():
    return (Path(__file__).parent / "templates" / "torneio.html").read_text()
```

to:

```python
@app.get("/torneio", response_class=HTMLResponse)
def torneio_page():
    return (Path(__file__).parent / "templates" / "torneio.html").read_text()


@app.get("/torneio/partidas/{match_id}", response_class=HTMLResponse)
def partida_page(match_id: int):
    return (Path(__file__).parent / "templates" / "partida.html").read_text()
```

- [ ] **Step 2: Create the template**

```html
<!-- app/templates/partida.html -->
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Placar — Vôlei</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header class="site-header">
  <div class="inner">
    <div>
      <h1>🏐 Placar</h1>
      <div id="matchTitle" class="muted">Carregando…</div>
    </div>
    <div class="actions">
      <a href="/torneio"><button>← Jogos</button></a>
    </div>
  </div>
</header>
<div class="app">
  <main>
    <section class="panel scoreboard">
      <div id="setsHistory" class="sets-history"></div>
      <div id="currentSetLabel" class="muted"></div>
      <div class="score-row">
        <div class="score-side">
          <div id="teamALabel" class="muted"></div>
          <div id="scoreA" class="score-value">0</div>
          <div class="inline">
            <button class="danger score-btn" data-team="a" data-delta="-1">-1</button>
            <button class="primary score-btn" data-team="a" data-delta="1">+1</button>
          </div>
        </div>
        <div class="score-side">
          <div id="teamBLabel" class="muted"></div>
          <div id="scoreB" class="score-value">0</div>
          <div class="inline">
            <button class="danger score-btn" data-team="b" data-delta="-1">-1</button>
            <button class="primary score-btn" data-team="b" data-delta="1">+1</button>
          </div>
        </div>
      </div>
      <button id="closeSetBtn" class="primary" disabled>Fechar set</button>
      <div id="resultBanner" class="muted hidden"></div>
    </section>
  </main>
</div>
<div id="toast"></div>
<script src="/static/partida.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create the script**

```javascript
// app/static/partida.js
const matchId = Number(location.pathname.split("/").filter(Boolean).pop());
let tournamentId = null;
let currentMatch = null;

const $ = id => document.getElementById(id);

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(window._toast);
  window._toast = setTimeout(() => t.style.display = "none", 2200);
}

async function api(url, options = {}) {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Erro");
  return data;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function findMatch() {
  const t = await api("/api/tournaments/active");
  if (!t) throw new Error("Nenhum torneio ativo");
  tournamentId = t.id;
  const matches = await api(`/api/tournaments/${tournamentId}/matches`);
  const m = matches.find(x => x.id === matchId);
  if (!m) throw new Error("Jogo não encontrado");
  return m;
}

function renderBoard(match, board) {
  $("matchTitle").textContent = `${esc(match.team_a_code)} × ${esc(match.team_b_code)}`;
  $("teamALabel").textContent = match.team_a_code;
  $("teamBLabel").textContent = match.team_b_code;

  $("setsHistory").innerHTML = board.sets
    .filter(s => s.closed)
    .map(s => `<span class="badge">Set ${s.set_number}: ${s.points_a}×${s.points_b}</span>`)
    .join("");

  if (board.result) {
    $("scoreA").textContent = "-";
    $("scoreB").textContent = "-";
    $("currentSetLabel").textContent = "";
    $("closeSetBtn").classList.add("hidden");
    document.querySelectorAll(".score-btn").forEach(b => b.classList.add("hidden"));
    $("resultBanner").classList.remove("hidden");
    $("resultBanner").textContent =
      `Vencedor: ${board.result.winner === "A" ? match.team_a_code : match.team_b_code} (${board.result.sets_a}×${board.result.sets_b})`;
    return;
  }

  $("resultBanner").classList.add("hidden");
  document.querySelectorAll(".score-btn").forEach(b => b.classList.remove("hidden"));
  $("closeSetBtn").classList.remove("hidden");

  const cur = board.current_set;
  $("currentSetLabel").textContent = cur ? `Set ${cur.set_number} (alvo ${cur.target})` : "";
  $("scoreA").textContent = cur ? cur.points_a : 0;
  $("scoreB").textContent = cur ? cur.points_b : 0;
  $("closeSetBtn").disabled = !cur || !cur.is_over;
}

async function refresh() {
  const board = await api(`/api/tournaments/${tournamentId}/matches/${matchId}/scoreboard`);
  renderBoard(currentMatch, board);
}

document.addEventListener("click", async e => {
  const scoreBtn = e.target.closest(".score-btn");
  if (scoreBtn) {
    try {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}/scoreboard/point`, {
        method: "POST",
        body: JSON.stringify({ team: scoreBtn.dataset.team, delta: Number(scoreBtn.dataset.delta) }),
      });
      await refresh();
    } catch (err) {
      toast(err.message);
    }
    return;
  }

  if (e.target.id === "closeSetBtn") {
    try {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}/scoreboard/close-set`, { method: "POST" });
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }
});

(async () => {
  try {
    currentMatch = await findMatch();
    await refresh();
    setInterval(() => refresh().catch(err => toast(err.message)), 4000);
  } catch (err) {
    toast(err.message);
  }
})();
```

- [ ] **Step 4: Add a "Placar" link to each match row**

In `app/static/torneio.js`, change:

```javascript
      <div class="actions">
        ${m.status === "agendado" ? `<button data-action="start" data-match-id="${m.id}">Iniciar</button>` : ""}
        ${m.status === "em_andamento" ? `<button data-action="finish" data-match-id="${m.id}">Encerrar</button>` : ""}
        <button class="danger" data-action="remove-match" data-match-id="${m.id}">Remover</button>
      </div>
```

to:

```javascript
      <div class="actions">
        <a href="/torneio/partidas/${m.id}"><button>Placar</button></a>
        ${m.status === "agendado" ? `<button data-action="start" data-match-id="${m.id}">Iniciar</button>` : ""}
        ${m.status === "em_andamento" ? `<button data-action="finish" data-match-id="${m.id}">Encerrar</button>` : ""}
        <button class="danger" data-action="remove-match" data-match-id="${m.id}">Remover</button>
      </div>
```

- [ ] **Step 5: Add the scoreboard CSS**

In `app/static/style.css`, append at the end of the file (after the closing `}` of the existing `@media(max-width:700px)` block):

```css

.scoreboard { display:flex; flex-direction:column; gap:16px; align-items:center; text-align:center; }
.score-row { display:flex; align-items:center; justify-content:center; gap:32px; flex-wrap:wrap; }
.score-side { display:flex; flex-direction:column; align-items:center; gap:10px; }
.score-value { font-family: var(--font-display); font-size: 64px; font-weight:700; font-variant-numeric: tabular-nums; }
.score-btn { font-size: 26px; padding: 16px 26px; min-width: 64px; }
.sets-history { display:flex; gap:8px; flex-wrap:wrap; justify-content:center; }
```

- [ ] **Step 6: Manual smoke check**

```bash
.venv/bin/uvicorn app.main:app --port 8129 &
sleep 1
curl -s -X POST http://127.0.0.1:8129/api/tournaments -H 'Content-Type: application/json' \
  -d '{"name":"Smoke","start_date":"2026-11-28","end_date":"2026-11-29"}'
curl -s -X POST http://127.0.0.1:8129/api/tournaments/1/teams -H 'Content-Type: application/json' -d '{"code":"A"}'
curl -s -X POST http://127.0.0.1:8129/api/tournaments/1/teams -H 'Content-Type: application/json' -d '{"code":"B"}'
curl -s -X POST http://127.0.0.1:8129/api/tournaments/1/matches -H 'Content-Type: application/json' \
  -d '{"team_a_id":1,"team_b_id":2,"scheduled_at":"2026-11-28T13:00:00"}'
curl -s -X POST http://127.0.0.1:8129/api/tournaments/1/matches/1/scoreboard/point -H 'Content-Type: application/json' -d '{"team":"a","delta":1}'
curl -s http://127.0.0.1:8129/api/tournaments/1/matches/1/scoreboard
curl -s http://127.0.0.1:8129/torneio/partidas/1 | grep -o 'id="closeSetBtn"'
kill %1
```

Expected: the point POST returns `{"set_number":1,"points_a":1,"points_b":0,"closed":false}`; the scoreboard GET shows `current_set.is_over: false`; the page grep finds the button id; no tracebacks. (Ids may differ against a non-empty `volei.db` — adjust from actual create responses if so.)

- [ ] **Step 7: Run the full suite to confirm nothing broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/templates/partida.html app/static/partida.js app/static/torneio.js app/static/style.css
git commit -m "Placar: página /torneio/partidas/{id}"
```

---

## Self-Review Notes

- **Spec coverage:** the refactor (clean split, no behavior change) → Task 1. `TournamentSetResult`/`SetPointRequest` → Task 2. The three scoreboard routes (point entry with negative/decided/invalid-input guards, close-set requiring `is_set_over`, auto-finish via `match_result`) → Task 3. The standalone page with polling, big touch targets, and the "Placar" link from the Jogos list → Task 4. Out-of-scope items (undo-close, standings) are not touched by any task.
- **Type consistency:** `get_scoreboard`'s returned shape (`match`, `sets`, `current_set` with `target`/`is_over`, `result`) is used identically by Task 3's tests and Task 4's `renderBoard`. `add_point`/`close_set`'s returned shape (`serialize_set`'s dict) matches what the tests assert. `tournament_engine.SET_TARGETS`/`is_set_over`/`match_result` are imported, never reimplemented, in both the route layer (Task 3) and — deliberately not reimplemented at all — the UI layer (Task 4 reads `is_over` from the server rather than recomputing it).
- **No placeholders:** every step has complete, runnable code, including the full moved block in Task 1 (not a "same as existing" reference).
