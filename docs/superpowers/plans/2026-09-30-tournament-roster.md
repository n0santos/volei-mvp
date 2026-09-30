# Cadastro do Torneio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tournament/team/roster registration to the app: new ORM models, a self-contained API router, and a standalone `/torneio` page — so an organizer can create a tournament, add teams, and assign players (with role and captain) from the existing player pool.

**Architecture:** A parallel module, not a modification of the pickup-night flow. `Tournament`/`Team`/`TeamPlayer` join `app/models.py` (same file, no new subpackage — matches the existing convention). All tournament routes live in a new `app/tournament.py` `APIRouter`, mounted into `app/main.py` with two lines; `main.py`'s 550+ existing lines are otherwise untouched. The UI is its own template/script pair (`templates/torneio.html` + `static/torneio.js`), served at `GET /torneio`, reusing the existing `static/style.css` design system rather than introducing new styles. No WebSocket, no real-time sync — this page is a single organizer filling out rosters before the event, not a multi-device live view.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-tournament-roster-design.md`

## Global Constraints

- `Tournament`, `Team`, `TeamPlayer` are added to `app/models.py` — no new subpackage for models.
- Tournament routes live in `app/tournament.py` (a new `APIRouter`), mounted into `main.py` — `main.py` itself is only touched to add the mount (2 lines) and the `GET /torneio` page route (mirroring the existing `GET /`).
- No hard validation of roster size (6 titulares + 1–2 reservas) or gender composition — display counts only, never block. Same philosophy as the tournament engine's mixed-volleyball decision.
- `Team.code` is free text, not constrained to exactly 5 teams or the letters A–E.
- `TeamPlayer.is_captain` is a boolean; only one captain per team is enforced by the update route (marking a new captain unmarks the previous one), not by a DB constraint.
- New tables only — `Base.metadata.create_all(bind=engine)` (already called in `main.py`) creates them automatically in any DB, new or existing. No `add_missing_columns()` migration needed (that's only for new columns on an existing table).
- No WebSocket, no new CSS file — reuse `static/style.css`'s existing classes (`.panel`, `.inline`, `.player-grid`, `.player`, `.info`, `.name`, `.muted`, `.actions`, `.badge`, `.hidden`, `button`, `.primary`, `.danger`).
- No type hints, no dataclasses in the router/model code — matches `app/main.py`'s existing style.

---

### Task 1: Data model and schemas

**Files:**
- Modify: `app/models.py`
- Modify: `app/schemas.py`
- Test: `tests/test_tournament_models.py`

**Interfaces:**
- Produces: `Tournament` (`id`, `name`, `start_date`, `end_date`, `active`), `Team` (`id`, `tournament_id`, `code`), `TeamPlayer` (`id`, `team_id`, `player_id`, `role`, `is_captain`, `.player` relationship) — all SQLAlchemy ORM models in `app/models.py`. `TournamentCreate` (`name`, `start_date`, `end_date`), `TeamCreate` (`code`), `TeamPlayerAdd` (`player_id`, `role="titular"`), `TeamPlayerUpdate` (`role: str | None`, `is_captain: bool | None`) — Pydantic schemas in `app/schemas.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tournament_models.py
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TeamPlayer, Player


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_tournament_team_teamplayer_roundtrip():
    db = make_db()
    t = Tournament(name="Torneio de Verão", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()

    team = Team(tournament_id=t.id, code="A")
    db.add(team)
    db.flush()

    p = Player(name="Ana", score=70, gender="F")
    db.add(p)
    db.flush()

    tp = TeamPlayer(team_id=team.id, player_id=p.id, role="titular", is_captain=True)
    db.add(tp)
    db.commit()

    saved = db.query(TeamPlayer).filter_by(team_id=team.id).one()
    assert saved.player.name == "Ana"
    assert saved.role == "titular"
    assert saved.is_captain is True


def test_tournament_defaults_to_active():
    db = make_db()
    t = Tournament(name="X", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.commit()
    assert t.active is True


def test_team_player_defaults():
    db = make_db()
    t = Tournament(name="X", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    team = Team(tournament_id=t.id, code="A")
    db.add(team)
    db.flush()
    p = Player(name="B", score=70, gender="M")
    db.add(p)
    db.flush()

    tp = TeamPlayer(team_id=team.id, player_id=p.id)
    db.add(tp)
    db.commit()

    assert tp.role == "titular"
    assert tp.is_captain is False
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Tournament' from 'app.models'`

- [ ] **Step 3: Write the implementation**

In `app/models.py`, change the top of the file:

```python
from datetime import datetime, date
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base
```

Then append at the end of the file (after the `Event` class):

```python
class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    code: Mapped[str] = mapped_column(String(20))


class TeamPlayer(Base):
    __tablename__ = "team_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    role: Mapped[str] = mapped_column(String(20), default="titular")  # titular/reserva
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)

    player: Mapped["Player"] = relationship()
```

In `app/schemas.py`, change the top of the file:

```python
from datetime import date

from pydantic import BaseModel
```

Then append at the end of the file:

```python
class TournamentCreate(BaseModel):
    name: str
    start_date: date
    end_date: date


class TeamCreate(BaseModel):
    code: str


class TeamPlayerAdd(BaseModel):
    player_id: int
    role: str = "titular"


class TeamPlayerUpdate(BaseModel):
    role: str | None = None
    is_captain: bool | None = None
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/schemas.py tests/test_tournament_models.py
git commit -m "Cadastro do torneio: modelos Tournament/Team/TeamPlayer e schemas"
```

---

### Task 2: Tournament and team routes, router mounted

**Files:**
- Create: `app/tournament.py`
- Modify: `app/main.py`
- Test: `tests/test_tournament_roster.py`

**Interfaces:**
- Consumes: `Tournament`, `Team`, `TeamPlayer`, `Player` (Task 1, `app/models.py`), `TournamentCreate`, `TeamCreate` (Task 1, `app/schemas.py`), `get_db` (`app/database.py`).
- Produces: `router` (a FastAPI `APIRouter`, `app/tournament.py`) with `create_tournament(data, db)`, `active_tournament(db)`, `get_tournament(db, tournament_id)` (plain helper, not a route), `create_team(tournament_id, data, db)`, `tournament_state(tournament_id, db)`. These are called directly as plain functions in tests (passing a real `db` session positionally), the same way `tests/test_attendance.py` calls `app.main.attendance` directly — the `Depends(get_db)` default is irrelevant outside a real request.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tournament_roster.py
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.tournament import create_tournament, active_tournament, create_team, tournament_state
from app.schemas import TournamentCreate, TeamCreate


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_tournament_activates_it():
    db = make_db()
    t = create_tournament(
        TournamentCreate(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29)), db
    )
    assert t.active is True

    active = active_tournament(db)
    assert active["id"] == t.id
    assert active["name"] == "Torneio"


def test_creating_a_new_tournament_deactivates_the_previous_one():
    db = make_db()
    first = create_tournament(
        TournamentCreate(name="Primeiro", start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)), db
    )
    second = create_tournament(
        TournamentCreate(name="Segundo", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29)), db
    )

    db.refresh(first)
    assert first.active is False
    assert second.active is True

    active = active_tournament(db)
    assert active["id"] == second.id


def test_active_tournament_returns_none_when_there_is_none():
    db = make_db()
    assert active_tournament(db) is None


def test_create_team_and_read_tournament_state():
    db = make_db()
    t = create_tournament(
        TournamentCreate(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29)), db
    )
    create_team(t.id, TeamCreate(code="A"), db)
    create_team(t.id, TeamCreate(code="B"), db)

    state = tournament_state(t.id, db)
    assert state["tournament"]["name"] == "Torneio"
    codes = sorted(team["code"] for team in state["teams"])
    assert codes == ["A", "B"]
    assert all(team["players"] == [] for team in state["teams"])


def test_create_team_for_missing_tournament_raises_404():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    with pytest.raises(HTTPException):
        create_team(999, TeamCreate(code="A"), db)


def test_tournament_state_for_missing_tournament_raises_404():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    with pytest.raises(HTTPException):
        tournament_state(999, db)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_roster.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tournament'`

- [ ] **Step 3: Write the implementation**

```python
# app/tournament.py
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
```

In `app/main.py`, change:

```python
from .services.fairness import history

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Vôlei MVP")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
```

to:

```python
from .services.fairness import history
from .tournament import router as tournament_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Vôlei MVP")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(tournament_router)
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_roster.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Sanity-check the app still imports and mounts cleanly**

Run: `python3 -c "from app.main import app; print([r.path for r in app.routes if '/tournaments' in r.path])"`
Expected: prints a list including `/api/tournaments`, `/api/tournaments/active`, `/api/tournaments/{tournament_id}/teams`, `/api/tournaments/{tournament_id}` — no import errors.

- [ ] **Step 6: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add app/tournament.py app/main.py tests/test_tournament_roster.py
git commit -m "Cadastro do torneio: rotas de torneio e time, router montado"
```

---

### Task 3: Roster management routes (add/update/remove player, captain exclusivity)

**Files:**
- Modify: `app/tournament.py`
- Modify: `tests/test_tournament_roster.py`

**Interfaces:**
- Consumes: `Team`, `TeamPlayer`, `Player` (Task 1), `TeamPlayerAdd`, `TeamPlayerUpdate` (Task 1), `tournament_state`/`create_tournament`/`create_team` (Task 2, same module — call directly, no import needed inside `tournament.py`; tests import them from Task 2's test file additions).
- Produces: `add_team_player(team_id, data, db)`, `update_team_player(team_id, player_id, data, db)`, `remove_team_player(team_id, player_id, db)`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_tournament_roster.py
# Update the existing import line for app.tournament to also bring in these three:
# from app.tournament import (
#     create_tournament, active_tournament, create_team, tournament_state,
#     add_team_player, update_team_player, remove_team_player,
# )
# And add TeamPlayerAdd, TeamPlayerUpdate to the existing app.schemas import line.
from app.models import Player


def make_team_with_player(db):
    t = create_tournament(
        TournamentCreate(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29)), db
    )
    team = create_team(t.id, TeamCreate(code="A"), db)
    player = Player(name="Ana", score=70, gender="F")
    db.add(player)
    db.commit()
    return team, player


def test_add_player_to_team():
    db = make_db()
    team, player = make_team_with_player(db)

    tp = add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)
    assert tp.role == "titular"
    assert tp.is_captain is False

    state = tournament_state(team.tournament_id, db)
    assert state["teams"][0]["players"][0]["name"] == "Ana"


def test_adding_same_player_twice_raises_conflict():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, player = make_team_with_player(db)
    add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)

    with pytest.raises(HTTPException):
        add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)


def test_marking_a_new_captain_unmarks_the_previous_one():
    db = make_db()
    team, player = make_team_with_player(db)
    add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)

    player2 = Player(name="Beto", score=70, gender="M")
    db.add(player2)
    db.commit()
    add_team_player(team.id, TeamPlayerAdd(player_id=player2.id), db)

    update_team_player(team.id, player.id, TeamPlayerUpdate(is_captain=True), db)
    update_team_player(team.id, player2.id, TeamPlayerUpdate(is_captain=True), db)

    state = tournament_state(team.tournament_id, db)
    by_name = {p["name"]: p["is_captain"] for p in state["teams"][0]["players"]}
    assert by_name["Beto"] is True
    assert by_name["Ana"] is False


def test_update_role():
    db = make_db()
    team, player = make_team_with_player(db)
    add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)

    update_team_player(team.id, player.id, TeamPlayerUpdate(role="reserva"), db)

    state = tournament_state(team.tournament_id, db)
    assert state["teams"][0]["players"][0]["role"] == "reserva"


def test_remove_player_from_team():
    db = make_db()
    team, player = make_team_with_player(db)
    add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)

    remove_team_player(team.id, player.id, db)

    state = tournament_state(team.tournament_id, db)
    assert state["teams"][0]["players"] == []


def test_update_missing_team_player_raises_404():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, player = make_team_with_player(db)

    with pytest.raises(HTTPException):
        update_team_player(team.id, player.id, TeamPlayerUpdate(role="reserva"), db)
```

Note: the commented-out import block at the top of this step is the instruction for editing the *existing* `from app.tournament import ...` and `from app.schemas import ...` lines at the top of `tests/test_tournament_roster.py` (written in Task 2) — consolidate to single import lines per name, don't leave two separate `from app.tournament import ...` lines.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_roster.py -v`
Expected: FAIL — `ImportError: cannot import name 'add_team_player'`; Task 2's tests still pass.

- [ ] **Step 3: Write the implementation**

Append to `app/tournament.py`:

```python
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
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_roster.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/tournament.py tests/test_tournament_roster.py
git commit -m "Cadastro do torneio: rotas de elenco (adicionar/atualizar/remover jogador, capitão)"
```

---

### Task 4: UI page (`/torneio`)

**Files:**
- Modify: `app/main.py`
- Create: `app/templates/torneio.html`
- Create: `app/static/torneio.js`

**Interfaces:**
- Consumes: every route from Tasks 2–3 (`POST /api/tournaments`, `GET /api/tournaments/active`, `POST /api/tournaments/{id}/teams`, `GET /api/tournaments/{id}`, `POST /api/teams/{id}/players`, `PATCH /api/teams/{id}/players/{player_id}`, `DELETE /api/teams/{id}/players/{player_id}`), plus the existing `GET /api/players` (to resolve a typed name to a `player_id`).
- Produces: `GET /torneio` (HTML page), no new interfaces for later tasks to consume (this is the sub-project's last task).

This task has no unit tests — there's no existing JS test harness in this repo (`app/static/app.js` has none either), and the deliverable is a rendered page. Verification is a manual smoke check via `curl` against a locally-started server, plus the full pytest suite to confirm nothing broke.

- [ ] **Step 1: Add the page route**

In `app/main.py`, change:

```python
@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "templates" / "index.html").read_text()
```

to:

```python
@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "templates" / "index.html").read_text()


@app.get("/torneio", response_class=HTMLResponse)
def torneio_page():
    return (Path(__file__).parent / "templates" / "torneio.html").read_text()
```

- [ ] **Step 2: Create the template**

```html
<!-- app/templates/torneio.html -->
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Modo Torneio — Vôlei</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header class="site-header">
  <div class="inner">
    <div>
      <h1>🏆 Torneio</h1>
      <div id="tournamentName" class="muted">Nenhum torneio ativo</div>
    </div>
  </div>
</header>
<div class="app">
  <main>
    <section id="newTournament" class="panel">
      <h2>Novo torneio</h2>
      <form id="tournamentForm" class="inline">
        <input id="tournamentNameInput" placeholder="Nome do torneio" required>
        <input id="tournamentStart" type="date" required>
        <input id="tournamentEnd" type="date" required>
        <button class="primary">Criar</button>
      </form>
    </section>

    <section id="tournamentPanel" class="panel hidden">
      <h2>Times</h2>
      <form id="teamForm" class="inline">
        <input id="teamCode" placeholder="Código do time (ex.: A)" required>
        <button class="primary">+ Time</button>
      </form>
      <div id="teams"></div>
    </section>
  </main>
</div>
<div id="toast"></div>
<script src="/static/torneio.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create the script**

```javascript
// app/static/torneio.js
let tournamentId = null;

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

async function loadActiveTournament() {
  const t = await api("/api/tournaments/active");
  if (t) {
    tournamentId = t.id;
    $("tournamentName").textContent = `${t.name} (${t.start_date} a ${t.end_date})`;
    $("newTournament").classList.add("hidden");
    $("tournamentPanel").classList.remove("hidden");
    await loadState();
  } else {
    tournamentId = null;
    $("tournamentName").textContent = "Nenhum torneio ativo";
    $("newTournament").classList.remove("hidden");
    $("tournamentPanel").classList.add("hidden");
  }
}

async function loadState() {
  const state = await api(`/api/tournaments/${tournamentId}`);
  $("teams").innerHTML = state.teams.map(renderTeam).join("");
}

function renderTeam(team) {
  const titulares = team.players.filter(p => p.role === "titular").length;
  return `
    <div class="panel" data-team-id="${team.id}">
      <h3>Time ${esc(team.code)} <span class="muted">(${team.players.length} jogador(es), ${titulares} titulares)</span></h3>
      <div class="player-grid">
        ${team.players.map(p => renderPlayer(team.id, p)).join("")}
      </div>
      <form class="inline add-player-form" data-team-id="${team.id}">
        <input placeholder="Nome do jogador" class="player-search" required>
        <button class="primary">Adicionar</button>
      </form>
    </div>
  `;
}

function renderPlayer(teamId, p) {
  return `
    <div class="player">
      <div class="info">
        <div class="name">${esc(p.name)} ${p.is_captain ? '<span class="badge wait">Capitão</span>' : ""}</div>
        <div class="muted">${p.role === "titular" ? "Titular" : "Reserva"}</div>
      </div>
      <div class="actions">
        <button data-action="toggle-role" data-team-id="${teamId}" data-player-id="${p.id}">
          ${p.role === "titular" ? "Reserva" : "Titular"}
        </button>
        <button data-action="toggle-captain" data-team-id="${teamId}" data-player-id="${p.id}">
          ${p.is_captain ? "Remover capitão" : "Capitão"}
        </button>
        <button class="danger" data-action="remove" data-team-id="${teamId}" data-player-id="${p.id}">Remover</button>
      </div>
    </div>
  `;
}

$("tournamentForm").addEventListener("submit", async e => {
  e.preventDefault();
  await api("/api/tournaments", {
    method: "POST",
    body: JSON.stringify({
      name: $("tournamentNameInput").value,
      start_date: $("tournamentStart").value,
      end_date: $("tournamentEnd").value,
    }),
  });
  await loadActiveTournament();
});

$("teamForm").addEventListener("submit", async e => {
  e.preventDefault();
  await api(`/api/tournaments/${tournamentId}/teams`, {
    method: "POST",
    body: JSON.stringify({ code: $("teamCode").value }),
  });
  $("teamCode").value = "";
  await loadState();
});

$("teams").addEventListener("submit", async e => {
  if (!e.target.classList.contains("add-player-form")) return;
  e.preventDefault();
  const teamId = e.target.dataset.teamId;
  const input = e.target.querySelector(".player-search");
  const name = input.value.trim();
  if (!name) return;

  const players = await api("/api/players");
  const match = players.find(p => p.name.toLowerCase() === name.toLowerCase());
  if (!match) {
    toast("Jogador não encontrado — cadastre primeiro na pelada");
    return;
  }

  try {
    await api(`/api/teams/${teamId}/players`, {
      method: "POST",
      body: JSON.stringify({ player_id: match.id }),
    });
    await loadState();
  } catch (err) {
    toast(err.message);
  }
});

$("teams").addEventListener("click", async e => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const { action, teamId, playerId } = btn.dataset;

  try {
    if (action === "remove") {
      await api(`/api/teams/${teamId}/players/${playerId}`, { method: "DELETE" });
    } else if (action === "toggle-role") {
      const newRole = btn.textContent.trim() === "Reserva" ? "reserva" : "titular";
      await api(`/api/teams/${teamId}/players/${playerId}`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole }),
      });
    } else if (action === "toggle-captain") {
      const makeCaptain = btn.textContent.trim() === "Capitão";
      await api(`/api/teams/${teamId}/players/${playerId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_captain: makeCaptain }),
      });
    }
    await loadState();
  } catch (err) {
    toast(err.message);
  }
});

loadActiveTournament();
```

- [ ] **Step 4: Manual smoke check**

Run the server in the background and confirm the page and API respond:

```bash
.venv/bin/uvicorn app.main:app --port 8123 &
sleep 1
curl -s http://127.0.0.1:8123/torneio | grep -o '<title>[^<]*</title>'
curl -s -X POST http://127.0.0.1:8123/api/tournaments -H 'Content-Type: application/json' \
  -d '{"name":"Smoke Test","start_date":"2026-11-28","end_date":"2026-11-29"}'
curl -s http://127.0.0.1:8123/api/tournaments/active
kill %1
```

Expected: the `<title>` line prints `<title>Modo Torneio — Vôlei</title>`; the `POST` returns the created tournament as JSON with `"active":true`; the `active` check returns the same tournament. No tracebacks in the server output.

- [ ] **Step 5: Run the full suite to confirm nothing broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/templates/torneio.html app/static/torneio.js
git commit -m "Cadastro do torneio: página /torneio"
```

---

## Self-Review Notes

- **Spec coverage:** Data model (Tournament/Team/TeamPlayer, `active` single-tournament rule, free-text `code`) → Task 1. All 7 routes from the spec → Tasks 2–3. `/torneio` page with tournament creation, team creation, roster display/search/role/captain/remove → Task 4. Out-of-scope items (balanced auto-formation, calendar, live score, standings, reserve tracking, hard validation) are not touched by any task.
- **Type consistency:** `tournament_state`'s returned dict shape (`tournament: {id, name, start_date, end_date}`, `teams: [{id, code, players: [{id, name, score, gender, role, is_captain}]}]`) is used identically by Task 3's tests and Task 4's `torneio.js`. `TeamPlayerAdd`/`TeamPlayerUpdate` field names match between Task 1's schemas, Task 3's routes, and Task 4's JS request bodies.
- **CSS classes used in Task 4** (`.panel`, `.inline`, `.player-grid`, `.player`, `.info`, `.name`, `.muted`, `.actions`, `.badge`, `.badge.wait`, `.hidden`, `button`, `.primary`, `.danger`) were all confirmed to already exist in `app/static/style.css` before writing this plan — no new stylesheet needed.
- **No placeholders:** every step has complete, runnable code; no "add validation" or "similar to Task N" shortcuts.
