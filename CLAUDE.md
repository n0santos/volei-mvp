# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Vôlei MVP: a local session manager for pickup volleyball nights (Portuguese UI/docs). Tracks a pre-list of players, check-in by arrival order, fair rotation into matches, score-balanced teams, and in-match substitutions, with real-time sync across devices on the same Wi-Fi via WebSocket. No auth, not meant to be exposed to the internet — see README.md "Limitações deliberadas do MVP" for the full list of intentional non-goals.

## Commands

```bash
# setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# run (serves on all interfaces so phones on the same Wi-Fi can connect)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# tests
pytest
pytest tests/test_teams.py::test_name   # single test
```

There is no lint/format tooling configured in pyproject.toml.

## Architecture

FastAPI monolith, server-rendered single page (`app/templates/index.html` + `app/static/app.js`) that polls state through a REST API and gets invalidated by a WebSocket "refresh" push (`/ws/{session_id}`) — the client refetches full state on that signal rather than receiving deltas. `app/main.py` holds every route; there's no router split.

Persistence is SQLite (`volei.db`) via SQLAlchemy ORM (`app/models.py`), one `get_db()` session per request.

Domain model: `Player` (persistent, with a `score` skill rating and `gender`) → `Session` (one night; only one can be `active` at a time — creating a new session deactivates the rest) → `Attendance` (per-session per-player status: `expected`/`arrived`/`absent`/`left`, plus arrival order) → `Match` (`proposed`/`running`/`finished`, only one non-finished match per session allowed at a time) → `MatchPlayer` (a player's stint in a match: team, `starter`/`substitute` role, entered/exited timestamps). `Event` is an append-only audit log of everything that happens, written alongside each state change but not currently read back by the app.

The core logic lives in `app/services/`, deliberately split from persistence and skill score:

- `fairness.py` (`history()`) — derives per-player stats for the current session from `MatchPlayer`/`Match` rows: total matches, minutes played, and *consecutive* outside/playing streaks (computed by walking finished match numbers backward per player). This is the shared input to both selection and substitution ranking — always recomputed from event/match data, never stored.
- `selection.py` (`select_players()`) — picks who plays the next match from `arrived` players. Ranks by a priority score that heavily rewards wait streak and penalizes recent playing streak, then brute-forces over `combinations()` of a small candidate pool (top N+6) to find the lowest-cost subset, honoring a hard-ish rule that anyone with `outside_streak >= 2` must be included when mathematically possible. This is O(C(n+6, n)) — fine for pool sizes in this MVP's range, but don't grow the pool window without reconsidering the approach.
- `ranking.py` (`ranking()`) — the "ranking do dia": per-player wins over finished matches with a `Match.winner` recorded, ordered by win rate (not total wins, so staying longer doesn't win by volume). Starters only, consistent with substitutes not counting as a match played. `Match.winner` was added after launch; `add_missing_columns()` in `database.py` ALTERs it into existing DBs since `create_all()` won't.
- `teams.py` (`balance_teams()`) — splits a chosen set of players into two teams by brute-forcing all bipartitions (`combinations()` again) to minimize score-sum difference plus a gender-balance penalty. Same combinatorial-blowup caveat applies.

Key invariants enforced in `main.py` rather than at the DB layer: only one active `Session`; only one `proposed`/`running` `Match` per session; substitution (`/api/matches/{id}/substitute`) fills the most recently vacated slot (last `MatchPlayer` with `exited_at` set) rather than a specified one.

Fairness explicitly separates **skill score** (used only to balance team strength) from **playing-time fairness** (used only to decide who plays next) — don't conflate the two when touching selection logic.
