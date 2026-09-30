# Formação Balanceada de Times Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Sortear times" button to the `/torneio` page that distributes a chosen pool of players into the tournament's already-created (empty) teams, balanced by score and gender.

**Architecture:** A pure algorithm module (`app/services/team_formation.py`, deterministic snake draft + hill-climbing, reusing `teams.py`'s score calibration), one new route on the existing `app/tournament.py` router, and an addition to the existing `/torneio` page (`templates/torneio.html` + `static/torneio.js`) — no new page, no new persistence beyond writing into the `Team`/`TeamPlayer` tables that already exist.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-team-formation-design.md`

## Global Constraints

- `app/services/team_formation.py` is a new flat module (no subpackage), plain functions, no type hints, no dataclasses, duck-typed inputs (`.score`/`.gender`) — matches `teams.py`/`tournament_engine.py`.
- Reuses `effective_score` from `app/services/teams.py` by import — does not redefine or duplicate the `MALE_ADJUSTMENT` calibration.
- The algorithm is fully deterministic — no `random`, unlike `teams.py`'s pelada draw (which intentionally varies). Same input always produces the same output.
- The route requires ALL of the tournament's teams to be empty before running — 409 otherwise. It never overwrites or discards an existing manual roster.
- Formed players are all written as `role="titular"`; deciding reservas stays a manual step via the existing `PATCH /api/teams/{id}/players/{player_id}`.
- No new CSS — reuse `static/style.css`'s existing classes (`.panel`, `.hidden`, `.inline`, `.player-grid`, `.player`, `.info`, `.name`, `.muted`).
- No pair constraints ("juntar"/"separar"), no multiple proposals, no simulated annealing — out of scope per the spec.

---

### Task 1: Balanced formation algorithm (pure function)

**Files:**
- Create: `app/services/team_formation.py`
- Test: `tests/test_team_formation.py`

**Interfaces:**
- Consumes: `effective_score` (from `app/services/teams.py`, same import style as any other cross-module reuse — no changes to `teams.py`).
- Produces: `form_teams(players, num_teams) -> list[list]` — a list of `num_teams` lists of player objects, deterministic, raises `ValueError` if `num_teams < 2` or `len(players) < num_teams`. Also exposes `team_score(players)`, `_snake_draft(players, num_teams)`, `_hill_climb(teams)`, `_cost(teams)` as module-level names (the leading underscore ones are internals the tests call directly to verify the algorithm's properties, same pattern `tournament_engine.py` doesn't need but this task's tests do for the local-optimum check).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_team_formation.py
from types import SimpleNamespace

from app.services.team_formation import form_teams, _cost, _hill_climb

_next_id = [0]


def p(name, score, gender="X"):
    _next_id[0] += 1
    return SimpleNamespace(id=_next_id[0], name=name, score=score, gender=gender)


def test_even_pool_splits_into_equal_team_sizes():
    players = [p(f"P{i}", 70, "X") for i in range(10)]
    teams = form_teams(players, 5)
    assert [len(t) for t in teams] == [2, 2, 2, 2, 2]


def test_uneven_pool_distributes_remainder_balanced():
    players = [p(f"P{i}", 70, "X") for i in range(12)]
    teams = form_teams(players, 5)
    sizes = sorted(len(t) for t in teams)
    assert sum(sizes) == 12
    assert max(sizes) - min(sizes) <= 1


def test_form_teams_is_deterministic():
    players = [p(f"P{i}", 100 - i * 3, "M" if i % 2 == 0 else "F") for i in range(14)]
    first = form_teams(players, 4)
    second = form_teams(players, 4)
    assert [sorted(pl.name for pl in team) for team in first] == \
        [sorted(pl.name for pl in team) for team in second]


def test_hill_climbing_improves_a_lopsided_split():
    men = [p(f"M{i}", 80, "M") for i in range(4)]
    women = [p(f"F{i}", 40, "F") for i in range(4)]
    lopsided = [men, women]  # deliberately bad: all men on one team, all women on the other

    cost_before = _cost(lopsided)
    improved = _hill_climb(lopsided)
    cost_after = _cost(improved)

    assert cost_after < cost_before


def test_hill_climb_result_is_a_local_optimum():
    players = [p(f"P{i}", 60 + i * 5, "M" if i % 3 == 0 else "F") for i in range(15)]
    teams = form_teams(players, 3)
    cost = _cost(teams)

    for i in range(len(teams)):
        for j in range(len(teams)):
            if i == j:
                continue
            for a in range(len(teams[i])):
                for b in range(len(teams[j])):
                    swapped = [list(t) for t in teams]
                    swapped[i][a], swapped[j][b] = swapped[j][b], swapped[i][a]
                    assert _cost(swapped) >= cost


def test_gender_balance_with_realistic_pool():
    men = [p(f"M{i}", 60 + i, "M") for i in range(20)]
    women = [p(f"F{i}", 60 + i, "F") for i in range(20)]
    teams = form_teams(men + women, 5)

    assert [len(t) for t in teams] == [8, 8, 8, 8, 8]
    for team in teams:
        f_count = sum(1 for pl in team if pl.gender == "F")
        m_count = sum(1 for pl in team if pl.gender == "M")
        assert abs(f_count - 4) <= 1
        assert abs(m_count - 4) <= 1


def test_form_teams_requires_at_least_two_teams():
    import pytest

    players = [p("A", 70, "X"), p("B", 70, "X")]
    with pytest.raises(ValueError):
        form_teams(players, 1)


def test_form_teams_requires_enough_players():
    import pytest

    players = [p("A", 70, "X")]
    with pytest.raises(ValueError):
        form_teams(players, 2)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_team_formation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.team_formation'`

- [ ] **Step 3: Write the implementation**

```python
# app/services/team_formation.py
from .teams import effective_score

GENDER_WEIGHT = 8
MAX_HILL_CLIMB_ITERATIONS = 500


def team_score(players):
    return sum(effective_score(p) for p in players)


def _gender_imbalance(teams):
    counts_f = [sum(1 for p in t if p.gender == "F") for t in teams]
    counts_m = [sum(1 for p in t if p.gender == "M") for t in teams]
    avg_f = sum(counts_f) / len(teams)
    avg_m = sum(counts_m) / len(teams)
    return (
        sum(abs(c - avg_f) for c in counts_f) * GENDER_WEIGHT
        + sum(abs(c - avg_m) for c in counts_m) * GENDER_WEIGHT
    )


def _cost(teams):
    scores = [team_score(t) for t in teams]
    return (max(scores) - min(scores)) + _gender_imbalance(teams)


def _snake_draft(players, num_teams):
    ordered = sorted(players, key=effective_score, reverse=True)
    teams = [[] for _ in range(num_teams)]
    order = list(range(num_teams))
    i = 0
    for player in ordered:
        teams[order[i]].append(player)
        i += 1
        if i == len(order):
            order.reverse()
            i = 0
    return teams


def _hill_climb(teams):
    teams = [list(t) for t in teams]
    best_cost = _cost(teams)
    improved = True
    iterations = 0
    while improved and iterations < MAX_HILL_CLIMB_ITERATIONS:
        improved = False
        iterations += 1
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                for a in range(len(teams[i])):
                    for b in range(len(teams[j])):
                        teams[i][a], teams[j][b] = teams[j][b], teams[i][a]
                        cost = _cost(teams)
                        if cost < best_cost:
                            best_cost = cost
                            improved = True
                        else:
                            teams[i][a], teams[j][b] = teams[j][b], teams[i][a]
    return teams


def form_teams(players, num_teams):
    if num_teams < 2:
        raise ValueError("form_teams precisa de pelo menos 2 times")
    if len(players) < num_teams:
        raise ValueError("menos jogadores do que times")
    return _hill_climb(_snake_draft(players, num_teams))
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_team_formation.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/services/team_formation.py tests/test_team_formation.py
git commit -m "Formação de times: motor puro (snake draft + hill-climbing)"
```

---

### Task 2: Route to form teams for a tournament

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/tournament.py`
- Modify: `tests/test_tournament_roster.py`

**Interfaces:**
- Consumes: `form_teams(players, num_teams)` (Task 1, `app/services/team_formation.py`); `get_tournament`, `tournament_state`, `add_team_player` (existing, same module, same file, no import needed); `Team`, `TeamPlayer`, `Player` (existing models).
- Produces: `TeamFormRequest` (`app/schemas.py`, `player_ids: list[int]`); `form_tournament_teams(tournament_id, data, db)` (`app/tournament.py`) — returns the same shape as `tournament_state`.

- [ ] **Step 1: Write the failing tests**

In `app/schemas.py`, change:

```python
class TeamPlayerUpdate(BaseModel):
    role: str | None = None
    is_captain: bool | None = None
```

to:

```python
class TeamPlayerUpdate(BaseModel):
    role: str | None = None
    is_captain: bool | None = None


class TeamFormRequest(BaseModel):
    player_ids: list[int]
```

In `tests/test_tournament_roster.py`, change the existing import block:

```python
from app.tournament import (
    create_tournament, active_tournament, create_team, tournament_state,
    add_team_player, update_team_player, remove_team_player,
)
from app.schemas import TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate
from app.models import Player
```

to:

```python
from app.tournament import (
    create_tournament, active_tournament, create_team, tournament_state,
    add_team_player, update_team_player, remove_team_player,
    form_tournament_teams,
)
from app.schemas import (
    TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamFormRequest,
)
from app.models import Player
```

Then append at the end of the file:

```python
def make_tournament_with_teams(db, codes):
    t = create_tournament(
        TournamentCreate(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29)), db
    )
    teams = [create_team(t.id, TeamCreate(code=code), db) for code in codes]
    return t, teams


def test_form_teams_distributes_players_and_marks_them_titular():
    db = make_db()
    t, teams = make_tournament_with_teams(db, ["A", "B"])
    players = [Player(name=f"P{i}", score=70 - i, gender="X") for i in range(6)]
    db.add_all(players)
    db.commit()

    result = form_tournament_teams(
        t.id, TeamFormRequest(player_ids=[pl.id for pl in players]), db
    )

    total_players = sum(len(team["players"]) for team in result["teams"])
    assert total_players == 6
    for team in result["teams"]:
        assert all(pl["role"] == "titular" for pl in team["players"])


def test_form_tournament_teams_requires_at_least_two_teams():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, teams = make_tournament_with_teams(db, ["A"])
    player = Player(name="Solo", score=70, gender="X")
    db.add(player)
    db.commit()

    with pytest.raises(HTTPException):
        form_tournament_teams(t.id, TeamFormRequest(player_ids=[player.id]), db)


def test_form_teams_refuses_when_a_team_already_has_a_player():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, teams = make_tournament_with_teams(db, ["A", "B"])
    p1 = Player(name="Already", score=70, gender="X")
    p2 = Player(name="New", score=70, gender="X")
    db.add_all([p1, p2])
    db.commit()
    add_team_player(teams[0].id, TeamPlayerAdd(player_id=p1.id), db)

    with pytest.raises(HTTPException):
        form_tournament_teams(t.id, TeamFormRequest(player_ids=[p2.id]), db)


def test_form_teams_404s_on_missing_player():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, teams = make_tournament_with_teams(db, ["A", "B"])

    with pytest.raises(HTTPException):
        form_tournament_teams(t.id, TeamFormRequest(player_ids=[999]), db)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_roster.py -v`
Expected: FAIL — `ImportError: cannot import name 'form_tournament_teams'`

- [ ] **Step 3: Write the implementation**

Append to `app/tournament.py` (add the import at the top alongside the existing ones, then the route at the end of the file):

Change:

```python
from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player
from .schemas import TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate
```

to:

```python
from .database import get_db
from .models import Tournament, Team, TeamPlayer, Player
from .schemas import TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamFormRequest
from .services.team_formation import form_teams
```

Then append at the end of the file:

```python
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
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_roster.py -v`
Expected: PASS (17 tests — 13 pre-existing + 4 new)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/schemas.py app/tournament.py tests/test_tournament_roster.py
git commit -m "Formação de times: rota POST /api/tournaments/{id}/form-teams"
```

---

### Task 3: UI — player pool and "Sortear times" button

**Files:**
- Modify: `app/templates/torneio.html`
- Modify: `app/static/torneio.js`

**Interfaces:**
- Consumes: `POST /api/tournaments/{id}/form-teams` (Task 2, body `{player_ids: [...]}`), `GET /api/players` (pre-existing).
- Produces: nothing for a later task — this is the sub-project's last task.

No pytest tests for this task — same reasoning as the cadastro sub-project's UI task: no JS test harness exists in this repo. Verification is a manual smoke check plus the full pytest suite.

- [ ] **Step 1: Add the pool-selection section to the template**

In `app/templates/torneio.html`, change:

```html
    <section id="tournamentPanel" class="panel hidden">
      <h2>Times</h2>
      <form id="teamForm" class="inline">
        <input id="teamCode" placeholder="Código do time (ex.: A)" required>
        <button class="primary">+ Time</button>
      </form>
      <div id="teams"></div>
    </section>
  </main>
```

to:

```html
    <section id="tournamentPanel" class="panel hidden">
      <h2>Times</h2>
      <form id="teamForm" class="inline">
        <input id="teamCode" placeholder="Código do time (ex.: A)" required>
        <button class="primary">+ Time</button>
      </form>
      <div id="teams"></div>
    </section>

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

Then change:

```javascript
loadActiveTournament().catch(err => toast(err.message));
```

to:

```javascript
let selectedPoolIds = new Set();
let allPlayers = [];

async function loadPlayerPool() {
  allPlayers = await api("/api/players");
  renderPlayerPool();
}

function filteredPoolPlayers() {
  const search = normalize($("playerPoolSearch").value.trim());
  return allPlayers.filter(p => normalize(p.name).includes(search));
}

function renderPlayerPool() {
  $("playerPool").innerHTML = filteredPoolPlayers().map(p => `
    <label class="player">
      <div class="info">
        <div class="name">${esc(p.name)}</div>
        <div class="muted">${p.gender} · score ${p.score}</div>
      </div>
      <input type="checkbox" data-player-id="${p.id}" ${selectedPoolIds.has(p.id) ? "checked" : ""}>
    </label>
  `).join("");
  $("poolCount").textContent = `${selectedPoolIds.size} selecionado(s)`;
}

$("playerPoolSearch").addEventListener("input", renderPlayerPool);

$("playerPool").addEventListener("change", e => {
  const checkbox = e.target.closest("input[type=checkbox]");
  if (!checkbox) return;
  const id = Number(checkbox.dataset.playerId);
  if (checkbox.checked) selectedPoolIds.add(id);
  else selectedPoolIds.delete(id);
  $("poolCount").textContent = `${selectedPoolIds.size} selecionado(s)`;
});

$("selectAllPlayers").addEventListener("change", e => {
  const ids = filteredPoolPlayers().map(p => p.id);
  if (e.target.checked) {
    ids.forEach(id => selectedPoolIds.add(id));
  } else {
    ids.forEach(id => selectedPoolIds.delete(id));
  }
  renderPlayerPool();
});

$("formTeamsBtn").addEventListener("click", async () => {
  if (selectedPoolIds.size === 0) {
    toast("Selecione pelo menos um jogador");
    return;
  }
  try {
    await api(`/api/tournaments/${tournamentId}/form-teams`, {
      method: "POST",
      body: JSON.stringify({ player_ids: Array.from(selectedPoolIds) }),
    });
    selectedPoolIds.clear();
    await loadState();
  } catch (err) {
    toast(err.message);
  }
});

loadActiveTournament().catch(err => toast(err.message));
```

- [ ] **Step 3: Manual smoke check**

```bash
.venv/bin/uvicorn app.main:app --port 8124 &
sleep 1
curl -s -X POST http://127.0.0.1:8124/api/tournaments -H 'Content-Type: application/json' \
  -d '{"name":"Smoke","start_date":"2026-11-28","end_date":"2026-11-29"}'
curl -s -X POST http://127.0.0.1:8124/api/tournaments/1/teams -H 'Content-Type: application/json' -d '{"code":"A"}'
curl -s -X POST http://127.0.0.1:8124/api/tournaments/1/teams -H 'Content-Type: application/json' -d '{"code":"B"}'
curl -s -X POST http://127.0.0.1:8124/api/players -H 'Content-Type: application/json' -d '{"name":"Smoke1","score":70,"gender":"F"}'
curl -s -X POST http://127.0.0.1:8124/api/players -H 'Content-Type: application/json' -d '{"name":"Smoke2","score":80,"gender":"M"}'
curl -s -X POST http://127.0.0.1:8124/api/tournaments/1/form-teams -H 'Content-Type: application/json' -d '{"player_ids":[1,2]}'
curl -s http://127.0.0.1:8124/torneio | grep -o 'id="formTeamsBtn"'
kill %1
```

Expected: the `form-teams` POST returns the tournament state with both players distributed across the two teams (one each, most likely, given the balancing), all `"role":"titular"`; the page grep finds the button id; no tracebacks in the server output. (Player/team ids may differ if run against a non-empty `volei.db` — adjust ids from the actual create responses if so.)

- [ ] **Step 4: Run the full suite to confirm nothing broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add app/templates/torneio.html app/static/torneio.js
git commit -m "Formação de times: seleção de pool e botão Sortear times em /torneio"
```

---

## Self-Review Notes

- **Spec coverage:** the algorithm (snake draft + hill-climbing, deterministic, reusing `effective_score`) → Task 1. The route (validates ≥2 teams, all-empty precondition, 404 on missing player, writes `titular` rows, reuses `tournament_state`'s response shape) → Task 2. The UI (pool with search/select-all/count, disabled button when occupied) → Task 3. Out-of-scope items (pair constraints, 3 proposals, simulated annealing, auto titular/reserva) are not touched by any task.
- **Type consistency:** `form_teams(players, num_teams)`'s return shape (list of lists of player-like objects with `.id`/`.name`/`.score`/`.gender`) is used identically by Task 2's route (`zip(teams, formed)`, then `player.id`) and by Task 1's own tests. The route's response shape matches `tournament_state`'s, which `torneio.js`'s `loadState()` (unchanged by this plan) already knows how to render — Task 3 doesn't need to parse the `form-teams` response at all, it just calls `loadState()` afterward.
- **No placeholders:** every step has complete, runnable code.
