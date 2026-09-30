# Motor do Torneio (Regras Puras) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `app/services/tournament_engine.py`, a set of pure functions implementing the tournament's set/match/standings rules (I Torneio de Verão – Vôlei Misto – TOC), with no persistence or UI.

**Architecture:** One flat module, matching the existing `app/services/teams.py`/`selection.py` convention: plain functions, no type hints, no dataclasses, duck-typed inputs (accept anything with the right attributes — plain objects in tests today, ORM rows from a future persistence sub-project later without any translation layer). Three independent-but-layered pieces: set-level rules, match-level aggregation, and tournament-level standings (which is built on top of match-level aggregation).

**Tech Stack:** Python 3.11+, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-30-tournament-engine-design.md`

## Global Constraints

- No type hints, no dataclasses — plain functions and dicts, matching `app/services/teams.py` and `app/services/selection.py`.
- No persistence, no I/O, no FastAPI/SQLAlchemy imports in `tournament_engine.py` — pure functions only.
- Functions accept duck-typed objects (attribute access, e.g. `match.team_a`), not dict indexing, so future ORM rows work without adapting.
- Set target scores: 18 (sets 1–2), 15 (set 3). Match points: 2-0=3, 2-1=2, 1-2=1, 0-2=0.
- Standings primary sort key is `tournament_points`; the regulation's chain (wins → sets_balance → points_balance → points_for) is a secondary tiebreak used only when `tournament_points` is tied. No confronto direto. Teams still tied after the full chain are marked `tied=True`, not auto-resolved.

---

### Task 1: Set rules

**Files:**
- Create: `app/services/tournament_engine.py`
- Test: `tests/test_tournament_engine.py`

**Interfaces:**
- Produces: `SET_TARGETS` (dict `{1: 18, 2: 18, 3: 15}`), `is_set_over(a, b, target) -> bool`, `set_winner(a, b, target) -> "A" | "B" | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tournament_engine.py
from app.services.tournament_engine import SET_TARGETS, is_set_over, set_winner


def test_set_targets():
    assert SET_TARGETS == {1: 18, 2: 18, 3: 15}


def test_set_not_over_at_17_17():
    assert is_set_over(17, 17, 18) is False


def test_set_over_at_19_17():
    assert is_set_over(19, 17, 18) is True


def test_set_winner_none_when_not_over():
    assert set_winner(17, 17, 18) is None


def test_set_winner_at_19_17():
    assert set_winner(19, 17, 18) == "A"


def test_set_winner_b_side():
    assert set_winner(14, 18, 18) == "B"


def test_third_set_not_over_at_14_14():
    assert is_set_over(14, 14, 15) is False


def test_third_set_not_over_at_15_14_one_point_diff():
    assert is_set_over(15, 14, 15) is False


def test_third_set_over_at_16_14():
    assert is_set_over(16, 14, 15) is True
    assert set_winner(16, 14, 15) == "A"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.tournament_engine'` (the file doesn't exist yet).

- [ ] **Step 3: Write the implementation**

```python
# app/services/tournament_engine.py
SET_TARGETS = {1: 18, 2: 18, 3: 15}


def is_set_over(a, b, target):
    return max(a, b) >= target and abs(a - b) >= 2


def set_winner(a, b, target):
    if not is_set_over(a, b, target):
        return None
    return "A" if a > b else "B"
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_engine.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/tournament_engine.py tests/test_tournament_engine.py
git commit -m "Motor do torneio: regras de set (is_set_over, set_winner)"
```

---

### Task 2: Match result and match points

**Files:**
- Modify: `app/services/tournament_engine.py`
- Modify: `tests/test_tournament_engine.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent functions in the same module).
- Produces: `match_points(sets_a, sets_b) -> int` (raises `ValueError` on any combo other than 2-0, 2-1, 1-2, 0-2), `match_result(sets) -> dict` with keys `winner` (`"A"|"B"|None`), `sets_a`, `sets_b`, `points_a`, `points_b`. `sets` is a list of `(points_a, points_b)` tuples, one per already-decided set.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_tournament_engine.py
import pytest
from app.services.tournament_engine import match_points, match_result


def test_match_points_win_2_0():
    assert match_points(2, 0) == 3


def test_match_points_win_2_1():
    assert match_points(2, 1) == 2


def test_match_points_loss_1_2():
    assert match_points(1, 2) == 1


def test_match_points_loss_0_2():
    assert match_points(0, 2) == 0


def test_match_points_invalid_combo_raises():
    with pytest.raises(ValueError):
        match_points(2, 2)


def test_match_result_finished_team_a_wins():
    result = match_result([(18, 16), (12, 18), (15, 10)])
    assert result == {
        "winner": "A",
        "sets_a": 2,
        "sets_b": 1,
        "points_a": 45,
        "points_b": 44,
    }


def test_match_result_finished_team_b_wins():
    result = match_result([(16, 18), (18, 12)])
    assert result["winner"] is None  # 1-1, not finished yet
    assert result["sets_a"] == 1
    assert result["sets_b"] == 1


def test_match_result_incomplete_returns_no_winner():
    result = match_result([(18, 16)])
    assert result["winner"] is None
    assert result["sets_a"] == 1
    assert result["sets_b"] == 0
```

Note: move the `from app.services.tournament_engine import ...` for Task 1's names and this task's names into a single import line at the top of the file when writing this step — keep the test file's imports on one line per module, not duplicated.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_engine.py -v`
Expected: FAIL — `ImportError: cannot import name 'match_points'` for the new tests; Task 1's tests still pass.

- [ ] **Step 3: Write the implementation**

```python
# append to app/services/tournament_engine.py
def match_points(sets_a, sets_b):
    table = {(2, 0): 3, (2, 1): 2, (1, 2): 1, (0, 2): 0}
    if (sets_a, sets_b) not in table:
        raise ValueError(f"placar de sets inválido para pontuação: {sets_a}x{sets_b}")
    return table[(sets_a, sets_b)]


def match_result(sets):
    sets_a = sum(1 for a, b in sets if a > b)
    sets_b = sum(1 for a, b in sets if b > a)
    points_a = sum(a for a, b in sets)
    points_b = sum(b for a, b in sets)

    if sets_a == 2:
        winner = "A"
    elif sets_b == 2:
        winner = "B"
    else:
        winner = None

    return {
        "winner": winner,
        "sets_a": sets_a,
        "sets_b": sets_b,
        "points_a": points_a,
        "points_b": points_b,
    }
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_engine.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/tournament_engine.py tests/test_tournament_engine.py
git commit -m "Motor do torneio: match_result e match_points"
```

---

### Task 3: Standings with tiebreak chain

**Files:**
- Modify: `app/services/tournament_engine.py`
- Modify: `tests/test_tournament_engine.py`

**Interfaces:**
- Consumes: `match_result(sets) -> dict`, `match_points(sets_a, sets_b) -> int` (both from Task 2, same module — call directly, no import needed).
- Produces: `compute_standings(matches) -> list[dict]`. `matches` is an iterable of finished-match objects with `.team_a`, `.team_b`, `.sets` (list of `(points_a, points_b)` tuples). Each returned dict has keys: `team`, `wins`, `losses`, `sets_for`, `sets_against`, `sets_balance`, `points_for`, `points_against`, `points_balance`, `tournament_points`, `tied` (bool). List is sorted best-to-worst.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_tournament_engine.py
from types import SimpleNamespace
from app.services.tournament_engine import compute_standings


def m(team_a, team_b, sets):
    return SimpleNamespace(team_a=team_a, team_b=team_b, sets=sets)


def test_compute_standings_orders_by_tournament_points():
    matches = [
        m("A", "B", [(18, 10), (18, 12)]),               # A wins 2-0 (A:3, B:0)
        m("A", "C", [(18, 16), (14, 18), (15, 10)]),      # A wins 2-1 (A:2, C:1)
        m("B", "C", [(18, 10), (18, 12)]),                # B wins 2-0 (B:3, C:0)
    ]
    standings = compute_standings(matches)
    order = [s["team"] for s in standings]
    assert order == ["A", "B", "C"]
    by_team = {s["team"]: s for s in standings}
    assert by_team["A"]["tournament_points"] == 5
    assert by_team["B"]["tournament_points"] == 3
    assert by_team["C"]["tournament_points"] == 1


def test_tournament_points_tie_broken_by_set_balance():
    matches = [
        m("D", "Z1", [(18, 10), (18, 10)]),   # D wins 2-0 (tp 3)
        m("D", "Z2", [(10, 18), (10, 18)]),   # D loses 0-2 (tp 0)
        m("D", "Z3", [(10, 18), (10, 18)]),   # D loses 0-2 (tp 0)
        m("E", "Z4", [(18, 10), (18, 10)]),   # E wins 2-0 (tp 3)
        m("F", "Z5", [(18, 16), (14, 18), (15, 10)]),  # F wins 2-1 (tp 2)
        m("F", "Z6", [(18, 10), (10, 18), (10, 15)]),  # F loses 1-2 (tp 1)
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["D"]["tournament_points"] == 3
    assert by_team["E"]["tournament_points"] == 3
    assert by_team["F"]["tournament_points"] == 3
    assert by_team["E"]["sets_balance"] == 2
    assert by_team["F"]["sets_balance"] == 0
    assert by_team["D"]["sets_balance"] == -2
    order = [s["team"] for s in standings if s["team"] in {"D", "E", "F"}]
    assert order == ["E", "F", "D"]


def test_tournament_points_tie_broken_by_wins_before_set_balance():
    matches = [
        m("G", "W1", [(18, 16), (14, 18), (15, 10)]),  # G wins 2-1 (tp 2)
        m("G", "W2", [(18, 16), (14, 18), (15, 10)]),  # G wins 2-1 (tp 2)
        m("G", "W3", [(10, 18), (10, 18)]),            # G loses 0-2 (tp 0)
        m("H", "W4", [(18, 10), (18, 10)]),            # H wins 2-0 (tp 3)
        m("H", "W5", [(18, 10), (10, 18), (10, 15)]),  # H loses 1-2 (tp 1)
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["G"]["tournament_points"] == 4
    assert by_team["H"]["tournament_points"] == 4
    assert by_team["G"]["wins"] == 2
    assert by_team["H"]["wins"] == 1
    assert by_team["G"]["sets_balance"] == 0
    assert by_team["H"]["sets_balance"] == 1
    # G has worse set balance but more wins, and wins is checked first.
    order = [s["team"] for s in standings if s["team"] in {"G", "H"}]
    assert order == ["G", "H"]


def test_tournament_points_wins_and_set_balance_tie_broken_by_point_balance():
    matches = [
        m("I", "V1", [(18, 5), (18, 5)]),
        m("J", "V2", [(18, 16), (18, 16)]),
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["I"]["tournament_points"] == by_team["J"]["tournament_points"] == 3
    assert by_team["I"]["wins"] == by_team["J"]["wins"] == 1
    assert by_team["I"]["sets_balance"] == by_team["J"]["sets_balance"] == 2
    assert by_team["I"]["points_balance"] > by_team["J"]["points_balance"]
    order = [s["team"] for s in standings if s["team"] in {"I", "J"}]
    assert order == ["I", "J"]


def test_everything_but_points_for_tied_is_broken_by_points_for():
    matches = [
        m("K", "V3", [(30, 20), (30, 20)]),
        m("L", "V4", [(25, 15), (25, 15)]),
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["K"]["points_balance"] == by_team["L"]["points_balance"] == 20
    assert by_team["K"]["points_for"] > by_team["L"]["points_for"]
    order = [s["team"] for s in standings if s["team"] in {"K", "L"}]
    assert order == ["K", "L"]


def test_full_tie_marks_teams_as_tied():
    matches = [
        m("M", "V5", [(18, 10), (18, 10)]),
        m("N", "V6", [(18, 10), (18, 10)]),
    ]
    standings = compute_standings(matches)
    by_team = {s["team"]: s for s in standings}
    assert by_team["M"]["tied"] is True
    assert by_team["N"]["tied"] is True


def test_compute_standings_raises_on_unfinished_match():
    matches = [m("O", "P", [(18, 16)])]
    with pytest.raises(ValueError):
        compute_standings(matches)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest tests/test_tournament_engine.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_standings'` for the new tests; all previous tests still pass.

- [ ] **Step 3: Write the implementation**

```python
# append to app/services/tournament_engine.py
def _new_team_row(name):
    return {
        "team": name,
        "wins": 0,
        "losses": 0,
        "sets_for": 0,
        "sets_against": 0,
        "points_for": 0,
        "points_against": 0,
        "tournament_points": 0,
    }


def _standings_sort_key(row):
    return (
        -row["tournament_points"],
        -row["wins"],
        -row["sets_balance"],
        -row["points_balance"],
        -row["points_for"],
    )


def compute_standings(matches):
    teams = {}

    def row(name):
        return teams.setdefault(name, _new_team_row(name))

    for match in matches:
        result = match_result(match.sets)
        a = row(match.team_a)
        b = row(match.team_b)

        a["sets_for"] += result["sets_a"]
        a["sets_against"] += result["sets_b"]
        a["points_for"] += result["points_a"]
        a["points_against"] += result["points_b"]

        b["sets_for"] += result["sets_b"]
        b["sets_against"] += result["sets_a"]
        b["points_for"] += result["points_b"]
        b["points_against"] += result["points_a"]

        if result["winner"] == "A":
            a["wins"] += 1
            b["losses"] += 1
        elif result["winner"] == "B":
            b["wins"] += 1
            a["losses"] += 1

        a["tournament_points"] += match_points(result["sets_a"], result["sets_b"])
        b["tournament_points"] += match_points(result["sets_b"], result["sets_a"])

    standings = list(teams.values())
    for s in standings:
        s["sets_balance"] = s["sets_for"] - s["sets_against"]
        s["points_balance"] = s["points_for"] - s["points_against"]

    standings.sort(key=_standings_sort_key)

    for s in standings:
        s["tied"] = False
    for i in range(len(standings) - 1):
        if _standings_sort_key(standings[i]) == _standings_sort_key(standings[i + 1]):
            standings[i]["tied"] = True
            standings[i + 1]["tied"] = True

    return standings
```

Note: `compute_standings` calls `match_points`, which raises `ValueError` for any match that hasn't reached 2 sets won — this is what makes `test_compute_standings_raises_on_unfinished_match` pass without any extra guard code. That's intentional: the function's contract (see the spec) is that only finished matches are passed in, and this fails loudly on a caller mistake instead of silently producing wrong standings.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_tournament_engine.py -v`
Expected: PASS (25 tests)

- [ ] **Step 5: Run the full test suite to confirm nothing else broke**

Run: `pytest`
Expected: PASS (all tests, including the pre-existing `test_teams.py` and others)

- [ ] **Step 6: Commit**

```bash
git add app/services/tournament_engine.py tests/test_tournament_engine.py
git commit -m "Motor do torneio: compute_standings com cadeia de desempate"
```

---

## Self-Review Notes

- **Spec coverage:** `SET_TARGETS`/`is_set_over`/`set_winner` → Task 1. `match_result`/`match_points` → Task 2. `compute_standings` (primary sort by `tournament_points`, secondary chain wins→sets_balance→points_balance→points_for, `tied` flag) → Task 3. All test scenarios listed in the spec's "Testes" section are covered: 17×17/19×17, 14×14/16×14 third-set boundary, the four match-points combos, triple-ish tie decided by set balance, each tiebreak criterion isolated, and a full tie marked `tied=True`.
- **Type consistency:** `match_result`'s return dict keys (`winner`, `sets_a`, `sets_b`, `points_a`, `points_b`) are used identically in Task 3's `compute_standings`. `compute_standings`'s row keys are introduced once in `_new_team_row` and referenced consistently in `_standings_sort_key` and the tests.
- **Out of scope, confirmed still out of scope:** no schedule/calendar generation, no final-match generation, no "which criterion decided" explanation string — all deferred to later sub-projects per the spec.
