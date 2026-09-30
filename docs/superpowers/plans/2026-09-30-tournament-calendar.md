# Calendário de Jogos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manually-maintained match schedule to the tournament: which team plays which, when, a simple status (agendado/em_andamento/encerrado), and a "Jogos" section on `/torneio` to manage it.

**Architecture:** A new `TournamentMatch` model (distinct from the pickup-night `Match` already in `app/models.py` — same table space, different concept, different name to avoid confusion), new CRUD routes on the existing `app/tournament.py` router, and a new section on the existing `/torneio` page. No new persistence patterns, no new services module — this sub-project is pure CRUD plus a client-side "what's next" view, no algorithm.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-tournament-calendar-design.md`

## Global Constraints

- `TournamentMatch` (not `Match`) — the codebase already has a `Match` model for pickup-night matches with an unrelated shape; reusing that name would be ambiguous across `app/models.py`.
- No hard validation of "only one `em_andamento` match at a time" — same trust-the-organizer philosophy as the rest of the tournament cadastro.
- No result/score capture in this sub-project — `status` only. That's the next sub-project's (placar ao vivo) job.
- No automatic schedule generation — matches are created one at a time via the API/UI, by the organizer.
- No dedicated "edit match" flow beyond `PATCH` on individual fields — the UI doesn't need an inline edit form; delete-and-recreate is acceptable, matching `Team.code`'s existing lack of an edit UI.
- No new CSS — reuse `static/style.css`'s existing classes, including `.status-arrived` (already styled as a highlight) for the "next match" indicator.
- No type hints, no dataclasses in the router/model code — matches the rest of `app/tournament.py`/`app/models.py`.

---

### Task 1: Data model and schemas

**Files:**
- Modify: `app/models.py`
- Modify: `app/schemas.py`
- Test: `tests/test_tournament_matches.py`

**Interfaces:**
- Produces: `TournamentMatch` (`id`, `tournament_id`, `team_a_id`, `team_b_id`, `scheduled_at`, `court`, `status` default `"agendado"`, `is_final` default `False`) in `app/models.py`. `TournamentMatchCreate` (`team_a_id`, `team_b_id`, `scheduled_at`, `court` optional, `is_final` default `False`), `TournamentMatchUpdate` (all fields optional: `team_a_id`, `team_b_id`, `scheduled_at`, `court`, `status`, `is_final`) in `app/schemas.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tournament_matches.py
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_tournament_and_teams(db):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    team_a = Team(tournament_id=t.id, code="A")
    team_b = Team(tournament_id=t.id, code="B")
    db.add_all([team_a, team_b])
    db.flush()
    return t, team_a, team_b


def test_tournament_match_roundtrip():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    m = TournamentMatch(
        tournament_id=t.id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
        court="Quadra 1",
    )
    db.add(m)
    db.commit()

    saved = db.query(TournamentMatch).filter_by(tournament_id=t.id).one()
    assert saved.team_a_id == team_a.id
    assert saved.team_b_id == team_b.id
    assert saved.scheduled_at == datetime(2026, 11, 28, 13, 0)
    assert saved.court == "Quadra 1"


def test_tournament_match_defaults():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    m = TournamentMatch(
        tournament_id=t.id,
        team_a_id=team_a.id,
        team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0),
    )
    db.add(m)
    db.commit()

    assert m.status == "agendado"
    assert m.is_final is False
    assert m.court is None
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_matches.py -v`
Expected: FAIL — `ImportError: cannot import name 'TournamentMatch' from 'app.models'`

- [ ] **Step 3: Write the implementation**

In `app/models.py`, `DateTime`, `String`, `Boolean`, `ForeignKey` and `datetime` are already imported (used by earlier models) — no import line changes needed. Append at the end of the file:

```python
class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    court: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="agendado")  # agendado/em_andamento/encerrado
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
```

In `app/schemas.py`, change:

```python
from datetime import date

from pydantic import BaseModel
```

to:

```python
from datetime import date, datetime

from pydantic import BaseModel
```

Then append at the end of the file:

```python
class TournamentMatchCreate(BaseModel):
    team_a_id: int
    team_b_id: int
    scheduled_at: datetime
    court: str | None = None
    is_final: bool = False


class TournamentMatchUpdate(BaseModel):
    team_a_id: int | None = None
    team_b_id: int | None = None
    scheduled_at: datetime | None = None
    court: str | None = None
    status: str | None = None
    is_final: bool | None = None
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_matches.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/schemas.py tests/test_tournament_matches.py
git commit -m "Calendário: modelo TournamentMatch e schemas"
```

---

### Task 2: Match CRUD routes

**Files:**
- Modify: `app/tournament.py`
- Modify: `tests/test_tournament_matches.py`

**Interfaces:**
- Consumes: `TournamentMatch` (Task 1, `app/models.py`), `TournamentMatchCreate`, `TournamentMatchUpdate` (Task 1, `app/schemas.py`), `get_tournament` (existing, same module).
- Produces: `get_tournament_team(db, tournament_id, team_id)` (plain helper, 404s if the team doesn't belong to the tournament), `create_match(tournament_id, data, db)`, `list_matches(tournament_id, db)` (returns a list of dicts with `team_a_code`/`team_b_code` already resolved), `get_match(db, tournament_id, match_id)` (plain helper), `update_match(tournament_id, match_id, data, db)`, `delete_match(tournament_id, match_id, db)`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_tournament_matches.py
from app.tournament import create_match, list_matches, update_match, delete_match
from app.schemas import TournamentMatchCreate, TournamentMatchUpdate


def test_create_and_list_matches():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    matches = list_matches(t.id, db)
    assert len(matches) == 1
    assert matches[0]["team_a_code"] == "A"
    assert matches[0]["team_b_code"] == "B"
    assert matches[0]["status"] == "agendado"


def test_matches_are_listed_in_scheduled_order():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 15, 0)),
        db,
    )
    create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    matches = list_matches(t.id, db)
    scheduled_times = [m["scheduled_at"] for m in matches]
    assert scheduled_times == sorted(scheduled_times)


def test_create_match_rejects_same_team_twice():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)

    with pytest.raises(HTTPException):
        create_match(
            t.id,
            TournamentMatchCreate(
                team_a_id=team_a.id, team_b_id=team_a.id, scheduled_at=datetime(2026, 11, 28, 13, 0)
            ),
            db,
        )


def test_create_match_404s_on_team_from_another_tournament():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t1, team_a, _team_b = make_tournament_and_teams(db)
    _t2, _other_a, other_b = make_tournament_and_teams(db)

    with pytest.raises(HTTPException):
        create_match(
            t1.id,
            TournamentMatchCreate(
                team_a_id=team_a.id, team_b_id=other_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)
            ),
            db,
        )


def test_update_match_status():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    updated = update_match(t.id, m.id, TournamentMatchUpdate(status="em_andamento"), db)
    assert updated.status == "em_andamento"


def test_update_match_rejects_invalid_status():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    with pytest.raises(HTTPException) as exc_info:
        update_match(t.id, m.id, TournamentMatchUpdate(status="xyz"), db)
    assert exc_info.value.status_code == 400


def test_delete_match():
    db = make_db()
    t, team_a, team_b = make_tournament_and_teams(db)
    m = create_match(
        t.id,
        TournamentMatchCreate(team_a_id=team_a.id, team_b_id=team_b.id, scheduled_at=datetime(2026, 11, 28, 13, 0)),
        db,
    )

    delete_match(t.id, m.id, db)

    assert list_matches(t.id, db) == []


def test_update_missing_match_raises_404():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, _team_a, _team_b = make_tournament_and_teams(db)

    with pytest.raises(HTTPException) as exc_info:
        update_match(t.id, 999, TournamentMatchUpdate(status="encerrado"), db)
    assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_matches.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_match' from 'app.tournament'`; Task 1's 2 tests still pass.

- [ ] **Step 3: Write the implementation**

In `app/tournament.py`, change:

```python
from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player
from .schemas import TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamFormRequest
from .services.team_formation import form_teams
```

to:

```python
from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player, TournamentMatch
from .schemas import (
    TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamFormRequest,
    TournamentMatchCreate, TournamentMatchUpdate,
)
from .services.team_formation import form_teams
```

Then append at the end of the file:

```python
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
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_matches.py -v`
Expected: PASS (10 tests — 2 from Task 1 + 8 new)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/tournament.py tests/test_tournament_matches.py
git commit -m "Calendário: rotas de CRUD de jogos"
```

---

### Task 3: UI — "Jogos" section

**Files:**
- Modify: `app/templates/torneio.html`
- Modify: `app/static/torneio.js`

**Interfaces:**
- Consumes: `POST/GET /api/tournaments/{id}/matches`, `PATCH/DELETE /api/tournaments/{id}/matches/{match_id}` (Task 2).
- Produces: nothing for a later task — this is the sub-project's last task.

No pytest tests — same reasoning as the other UI tasks in this feature (no JS test harness in this repo). Verification is a manual smoke check plus the full pytest suite.

- [ ] **Step 1: Add the "Jogos" section to the template**

In `app/templates/torneio.html`, change:

```html
    <section id="formTeamsSection" class="panel hidden">
      <h2>Sortear times</h2>
      <div class="inline">
        <input id="playerPoolSearch" placeholder="Buscar jogador...">
        <label><input type="checkbox" id="selectAllPlayers"> Selecionar todos</label>
        <span id="poolCount" class="muted">0 selecionado(s)</span>
      </div>
      <div id="playerPool" class="player-grid"></div>
      <button id="formTeamsBtn" class="primary">Sortear times</button>
    </section>
  </main>
```

to:

```html
    <section id="formTeamsSection" class="panel hidden">
      <h2>Sortear times</h2>
      <div class="inline">
        <input id="playerPoolSearch" placeholder="Buscar jogador...">
        <label><input type="checkbox" id="selectAllPlayers"> Selecionar todos</label>
        <span id="poolCount" class="muted">0 selecionado(s)</span>
      </div>
      <div id="playerPool" class="player-grid"></div>
      <button id="formTeamsBtn" class="primary">Sortear times</button>
    </section>

    <section id="matchesSection" class="panel hidden">
      <h2>Jogos</h2>
      <form id="matchForm" class="inline">
        <select id="matchTeamA" required></select>
        <span>×</span>
        <select id="matchTeamB" required></select>
        <input id="matchScheduledAt" type="datetime-local" required>
        <input id="matchCourt" placeholder="Quadra (opcional)">
        <label><input type="checkbox" id="matchIsFinal"> Final</label>
        <button class="primary">+ Jogo</button>
      </form>
      <div id="matches"></div>
    </section>
  </main>
```

- [ ] **Step 2: Wire it up in the script**

In `app/static/torneio.js`, change:

```javascript
async function loadActiveTournament() {
  const t = await api("/api/tournaments/active");
  if (t) {
    tournamentId = t.id;
    $("tournamentName").textContent = `${t.name} (${t.start_date} a ${t.end_date})`;
    $("newTournament").classList.add("hidden");
    $("tournamentPanel").classList.remove("hidden");
    $("formTeamsSection").classList.remove("hidden");
    await loadState();
    await loadPlayerPool();
  } else {
    tournamentId = null;
    $("tournamentName").textContent = "Nenhum torneio ativo";
    $("newTournament").classList.remove("hidden");
    $("tournamentPanel").classList.add("hidden");
    $("formTeamsSection").classList.add("hidden");
  }
}

async function loadState() {
  const state = await api(`/api/tournaments/${tournamentId}`);
  $("teams").innerHTML = state.teams.map(renderTeam).join("");

  const anyOccupied = state.teams.some(team => team.players.length > 0);
  $("formTeamsBtn").disabled = anyOccupied;
  $("formTeamsBtn").title = anyOccupied
    ? "Remova os jogadores dos times antes de sortear de novo"
    : "";
}
```

to:

```javascript
async function loadActiveTournament() {
  const t = await api("/api/tournaments/active");
  if (t) {
    tournamentId = t.id;
    $("tournamentName").textContent = `${t.name} (${t.start_date} a ${t.end_date})`;
    $("newTournament").classList.add("hidden");
    $("tournamentPanel").classList.remove("hidden");
    $("formTeamsSection").classList.remove("hidden");
    $("matchesSection").classList.remove("hidden");
    await loadState();
    await loadPlayerPool();
    await loadMatches();
  } else {
    tournamentId = null;
    $("tournamentName").textContent = "Nenhum torneio ativo";
    $("newTournament").classList.remove("hidden");
    $("tournamentPanel").classList.add("hidden");
    $("formTeamsSection").classList.add("hidden");
    $("matchesSection").classList.add("hidden");
  }
}

async function loadState() {
  const state = await api(`/api/tournaments/${tournamentId}`);
  $("teams").innerHTML = state.teams.map(renderTeam).join("");

  const anyOccupied = state.teams.some(team => team.players.length > 0);
  $("formTeamsBtn").disabled = anyOccupied;
  $("formTeamsBtn").title = anyOccupied
    ? "Remova os jogadores dos times antes de sortear de novo"
    : "";

  populateTeamSelect($("matchTeamA"), state.teams);
  populateTeamSelect($("matchTeamB"), state.teams);
}
```

Then change:

```javascript
loadActiveTournament().catch(err => toast(err.message));
```

to:

```javascript
function populateTeamSelect(select, teams) {
  const previous = select.value;
  select.innerHTML = teams.map(t => `<option value="${t.id}">${esc(t.code)}</option>`).join("");
  if (teams.some(t => String(t.id) === previous)) select.value = previous;
}

async function loadMatches() {
  const matches = await api(`/api/tournaments/${tournamentId}/matches`);
  renderMatches(matches);
}

function renderMatches(matches) {
  const next = matches.find(m => m.status !== "encerrado");
  $("matches").innerHTML = matches.map(m => renderMatch(m, next && m.id === next.id)).join("");
}

function renderMatch(m, isNext) {
  const when = new Date(m.scheduled_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  return `
    <div class="player ${isNext ? "status-arrived" : ""}" data-match-id="${m.id}">
      <div class="info">
        <div class="name">
          ${esc(m.team_a_code)} × ${esc(m.team_b_code)}
          ${m.is_final ? '<span class="badge wait">Final</span>' : ""}
        </div>
        <div class="muted">${when}${m.court ? " · " + esc(m.court) : ""} · ${m.status}</div>
      </div>
      <div class="actions">
        ${m.status === "agendado" ? `<button data-action="start" data-match-id="${m.id}">Iniciar</button>` : ""}
        ${m.status === "em_andamento" ? `<button data-action="finish" data-match-id="${m.id}">Encerrar</button>` : ""}
        <button class="danger" data-action="remove-match" data-match-id="${m.id}">Remover</button>
      </div>
    </div>
  `;
}

$("matchForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api(`/api/tournaments/${tournamentId}/matches`, {
      method: "POST",
      body: JSON.stringify({
        team_a_id: Number($("matchTeamA").value),
        team_b_id: Number($("matchTeamB").value),
        scheduled_at: $("matchScheduledAt").value,
        court: $("matchCourt").value || null,
        is_final: $("matchIsFinal").checked,
      }),
    });
    $("matchScheduledAt").value = "";
    $("matchCourt").value = "";
    $("matchIsFinal").checked = false;
    await loadMatches();
  } catch (err) {
    toast(err.message);
  }
});

$("matches").addEventListener("click", async e => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const { action, matchId } = btn.dataset;

  try {
    if (action === "start") {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "em_andamento" }),
      });
    } else if (action === "finish") {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "encerrado" }),
      });
    } else if (action === "remove-match") {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}`, { method: "DELETE" });
    }
    await loadMatches();
  } catch (err) {
    toast(err.message);
  }
});

loadActiveTournament().catch(err => toast(err.message));
```

- [ ] **Step 3: Manual smoke check**

```bash
.venv/bin/uvicorn app.main:app --port 8127 &
sleep 1
curl -s -X POST http://127.0.0.1:8127/api/tournaments -H 'Content-Type: application/json' \
  -d '{"name":"Smoke","start_date":"2026-11-28","end_date":"2026-11-29"}'
curl -s -X POST http://127.0.0.1:8127/api/tournaments/1/teams -H 'Content-Type: application/json' -d '{"code":"A"}'
curl -s -X POST http://127.0.0.1:8127/api/tournaments/1/teams -H 'Content-Type: application/json' -d '{"code":"B"}'
curl -s -X POST http://127.0.0.1:8127/api/tournaments/1/matches -H 'Content-Type: application/json' \
  -d '{"team_a_id":1,"team_b_id":2,"scheduled_at":"2026-11-28T13:00:00","court":"Quadra 1"}'
curl -s http://127.0.0.1:8127/api/tournaments/1/matches
curl -s -X PATCH http://127.0.0.1:8127/api/tournaments/1/matches/1 -H 'Content-Type: application/json' -d '{"status":"em_andamento"}'
curl -s http://127.0.0.1:8127/torneio | grep -o 'id="matchesSection"'
kill %1
```

Expected: the match POST returns the created match with `"status":"agendado"`; the list shows `team_a_code`/`team_b_code` resolved to `"A"`/`"B"`; the PATCH returns `"status":"em_andamento"`; the page grep finds the section id; no tracebacks. (Team/tournament ids may differ if run against a non-empty `volei.db` — adjust from the actual create responses if so.)

- [ ] **Step 4: Run the full suite to confirm nothing broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add app/templates/torneio.html app/static/torneio.js
git commit -m "Calendário: seção Jogos em /torneio"
```

---

## Self-Review Notes

- **Spec coverage:** `TournamentMatch` model (distinct name from the pickup-night `Match`, no hard "one em_andamento" validation, no score fields) → Task 1. All four CRUD routes (team-in-tournament validation, same-team rejection, status whitelist) → Task 2. The "Jogos" section (team dropdowns populated from current teams, scheduled/court/final inputs, status-based action buttons, "next match" highlight) → Task 3. Out-of-scope items (auto-generation, result capture, automatic final) are not touched by any task.
- **Type consistency:** `list_matches`' returned dict shape (`id`, `team_a_id`, `team_a_code`, `team_b_id`, `team_b_code`, `scheduled_at`, `court`, `status`, `is_final`) is used identically by Task 2's tests and Task 3's `renderMatch`/`renderMatches`. `get_tournament_team`'s signature (`db, tournament_id, team_id`) matches its three call sites in `create_match`/`update_match`.
- **No placeholders:** every step has complete, runnable code.
