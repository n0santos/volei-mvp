# Classificação Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a live-updating standings table on `/torneio`, computed from finished (non-final) matches via the tournament engine's `compute_standings`, with teams that haven't played yet still listed at zero.

**Architecture:** One new read-only route (`GET /api/tournaments/{id}/standings`) in `app/tournament_matches.py` that adapts `TournamentMatch`/`TournamentSetResult` rows into the plain duck-typed objects `compute_standings` (`app/services/tournament_engine.py`, untouched since sub-project 1) already expects, then pre-seeds any team with zero finished matches. A new "Classificação" section on the existing `/torneio` page, polling the route every few seconds.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-standings-design.md`

## Global Constraints

- `app/services/tournament_engine.py` is not modified — `compute_standings` is imported and used exactly as it already is.
- Only matches with `status == "encerrado"` AND `is_final == False` count toward standings — the final doesn't feed back into the table that decided it.
- Teams with zero finished matches still appear in the response, with every stat at `0` and `tied: False`, placed after the teams that have actually played (no attempt to rank an unplayed team against the tiebreak chain of teams that have real results).
- No new CSS — reuse `.panel`, `.player-grid`, `.player`, `.info`, `.name`, `.muted`, `.badge`, `.badge.wait`.
- No automatic final-match generation — out of scope per the spec.
- No type hints, no dataclasses in route code — matches the rest of `app/tournament_matches.py`.

---

### Task 1: Standings route

**Files:**
- Modify: `app/tournament_matches.py`
- Create: `tests/test_tournament_standings.py`

**Interfaces:**
- Consumes: `compute_standings` (`app/services/tournament_engine.py`, new import for this file), `get_tournament` (existing, same module), `Team`/`TournamentMatch`/`TournamentSetResult` (existing models).
- Produces: `get_standings(tournament_id, db) -> list[dict]`. Each dict has the same keys `compute_standings` already produces (`team`, `wins`, `losses`, `sets_for`, `sets_against`, `sets_balance`, `points_for`, `points_against`, `points_balance`, `tournament_points`, `tied`), where `team` is the team's `code`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tournament_standings.py
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Tournament, Team, TournamentMatch, TournamentSetResult
from app.tournament_matches import get_standings


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_tournament_and_teams(db, codes=("A", "B")):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    teams = [Team(tournament_id=t.id, code=code) for code in codes]
    db.add_all(teams)
    db.flush()
    return t, teams


def make_finished_match(db, tournament_id, team_a_id, team_b_id, sets, is_final=False):
    m = TournamentMatch(
        tournament_id=tournament_id, team_a_id=team_a_id, team_b_id=team_b_id,
        scheduled_at=datetime(2026, 11, 28, 13, 0), status="encerrado", is_final=is_final,
    )
    db.add(m)
    db.flush()
    for i, (pa, pb) in enumerate(sets, start=1):
        db.add(TournamentSetResult(match_id=m.id, set_number=i, points_a=pa, points_b=pb, closed=True))
    db.commit()
    return m


def test_standings_from_a_finished_match():
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)])

    standings = get_standings(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 3
    assert by_team["A"]["wins"] == 1
    assert by_team["B"]["tournament_points"] == 0


def test_teams_with_no_finished_match_still_appear_at_zero():
    db = make_db()
    t, (team_a, team_b, team_c) = make_tournament_and_teams(db, codes=("A", "B", "C"))
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)])

    standings = get_standings(t.id, db)

    assert len(standings) == 3
    by_team = {row["team"]: row for row in standings}
    assert by_team["C"]["tournament_points"] == 0
    assert by_team["C"]["wins"] == 0
    assert by_team["C"]["tied"] is False


def test_final_match_does_not_count_toward_standings():
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    make_finished_match(db, t.id, team_a.id, team_b.id, [(18, 10), (18, 12)], is_final=True)

    standings = get_standings(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 0
    assert by_team["B"]["tournament_points"] == 0


def test_unfinished_match_does_not_count_toward_standings():
    db = make_db()
    t, (team_a, team_b) = make_tournament_and_teams(db)
    m = TournamentMatch(
        tournament_id=t.id, team_a_id=team_a.id, team_b_id=team_b.id,
        scheduled_at=datetime(2026, 11, 28, 13, 0), status="em_andamento",
    )
    db.add(m)
    db.flush()
    db.add(TournamentSetResult(match_id=m.id, set_number=1, points_a=18, points_b=10, closed=True))
    db.commit()

    standings = get_standings(t.id, db)

    by_team = {row["team"]: row for row in standings}
    assert by_team["A"]["tournament_points"] == 0
    assert by_team["B"]["tournament_points"] == 0
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_standings.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_standings' from 'app.tournament_matches'`

- [ ] **Step 3: Write the implementation**

In `app/tournament_matches.py`, change:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Team, TournamentMatch, TournamentSetResult
from .schemas import TournamentMatchCreate, TournamentMatchUpdate, SetPointRequest
from .services.tournament_engine import SET_TARGETS, is_set_over, match_result
from .tournament import get_tournament
```

to:

```python
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Team, TournamentMatch, TournamentSetResult
from .schemas import TournamentMatchCreate, TournamentMatchUpdate, SetPointRequest
from .services.tournament_engine import SET_TARGETS, is_set_over, match_result, compute_standings
from .tournament import get_tournament
```

Then append at the end of the file:

```python
@router.get("/api/tournaments/{tournament_id}/standings")
def get_standings(tournament_id: int, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    teams = db.execute(select(Team).where(Team.tournament_id == tournament_id)).scalars().all()
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
        sets = db.execute(
            select(TournamentSetResult)
            .where(TournamentSetResult.match_id == m.id, TournamentSetResult.closed == True)
            .order_by(TournamentSetResult.set_number)
        ).scalars().all()
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
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_standings.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add app/tournament_matches.py tests/test_tournament_standings.py
git commit -m "Classificação: rota GET /api/tournaments/{id}/standings"
```

---

### Task 2: UI — "Classificação" section

**Files:**
- Modify: `app/templates/torneio.html`
- Modify: `app/static/torneio.js`

**Interfaces:**
- Consumes: `GET /api/tournaments/{id}/standings` (Task 1).
- Produces: nothing for a later task — this is the sub-project's last task.

No pytest tests — same reasoning as every other UI task in this feature (no JS test harness in this repo). Verification is a manual smoke check plus the full pytest suite.

- [ ] **Step 1: Add the section to the template**

In `app/templates/torneio.html`, change:

```html
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

to:

```html
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

    <section id="standingsSection" class="panel hidden">
      <h2>Classificação</h2>
      <div id="standingsBody" class="player-grid"></div>
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
    $("standingsSection").classList.remove("hidden");
    await loadState();
    await loadPlayerPool();
    await loadMatches();
    await loadStandings();
  } else {
    tournamentId = null;
    $("tournamentName").textContent = "Nenhum torneio ativo";
    $("newTournament").classList.remove("hidden");
    $("tournamentPanel").classList.add("hidden");
    $("formTeamsSection").classList.add("hidden");
    $("matchesSection").classList.add("hidden");
    $("standingsSection").classList.add("hidden");
  }
}
```

Then change:

```javascript
loadActiveTournament().catch(err => toast(err.message));
```

to:

```javascript
async function loadStandings() {
  const standings = await api(`/api/tournaments/${tournamentId}/standings`);
  renderStandings(standings);
}

function renderStandings(standings) {
  $("standingsBody").innerHTML = standings.map((row, i) => `
    <div class="player">
      <div class="info">
        <div class="name">
          ${i + 1}º ${esc(row.team)}
          ${row.tied ? '<span class="badge wait">empate</span>' : ""}
          <span class="badge">${row.tournament_points} pts</span>
        </div>
        <div class="muted">V: ${row.wins} · Saldo sets: ${row.sets_balance} · Saldo pontos: ${row.points_balance} · PP: ${row.points_for}</div>
      </div>
    </div>
  `).join("");
}

setInterval(() => {
  if (tournamentId) loadStandings().catch(err => toast(err.message));
}, 8000);

loadActiveTournament().catch(err => toast(err.message));
```

- [ ] **Step 3: Manual smoke check**

```bash
.venv/bin/uvicorn app.main:app --port 8131 &
sleep 1
curl -s -X POST http://127.0.0.1:8131/api/tournaments -H 'Content-Type: application/json' \
  -d '{"name":"Smoke","start_date":"2026-11-28","end_date":"2026-11-29"}'
curl -s -X POST http://127.0.0.1:8131/api/tournaments/1/teams -H 'Content-Type: application/json' -d '{"code":"A"}'
curl -s -X POST http://127.0.0.1:8131/api/tournaments/1/teams -H 'Content-Type: application/json' -d '{"code":"B"}'
curl -s http://127.0.0.1:8131/api/tournaments/1/standings
curl -s http://127.0.0.1:8131/torneio | grep -o 'id="standingsSection"'
kill %1
```

Expected: the standings GET returns a list with both teams `A` and `B` at `tournament_points: 0` (no matches played yet); the page grep finds the section id; no tracebacks. (Ids may differ against a non-empty `volei.db` — adjust from actual create responses if so.)

- [ ] **Step 4: Run the full suite to confirm nothing broke**

Run: `pytest`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add app/templates/torneio.html app/static/torneio.js
git commit -m "Classificação: seção Classificação em /torneio"
```

---

## Self-Review Notes

- **Spec coverage:** the route (only encerrado+non-final matches, zero-seeded unplayed teams, engine untouched) → Task 1. The UI section (reuses existing classes, polls every 8s) → Task 2. Out-of-scope items (automatic final generation, per-criterion tiebreak explanation) are not touched by either task.
- **Type consistency:** `get_standings`'s returned list-of-dicts shape (`team`, `wins`, `sets_balance`, `points_balance`, `points_for`, `tournament_points`, `tied`) is used identically by Task 1's tests and Task 2's `renderStandings`.
- **No placeholders:** every step has complete, runnable code.
