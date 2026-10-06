from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.models import Tournament, Team
from app.schemas import TeamUpdate
from app.tournament import update_team, tournament_state


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_team(db):
    t = Tournament(name="Torneio", start_date=date(2026, 11, 28), end_date=date(2026, 11, 29))
    db.add(t)
    db.flush()
    team = Team(tournament_id=t.id, code="A")
    db.add(team)
    db.commit()
    return t, team


def test_team_starts_without_a_group():
    db = make_db()
    t, team = make_team(db)
    assert team.group_name is None


def test_update_team_sets_and_clears_group():
    db = make_db()
    t, team = make_team(db)

    update_team(team.id, TeamUpdate(group_name="B"), db)
    assert team.group_name == "B"

    update_team(team.id, TeamUpdate(group_name=None), db)
    assert team.group_name is None


def test_update_team_without_group_field_leaves_it_alone():
    db = make_db()
    t, team = make_team(db)
    update_team(team.id, TeamUpdate(group_name="A"), db)

    update_team(team.id, TeamUpdate(), db)

    assert team.group_name == "A"


def test_update_team_rejects_unknown_group():
    db = make_db()
    t, team = make_team(db)

    with pytest.raises(HTTPException) as exc_info:
        update_team(team.id, TeamUpdate(group_name="C"), db)
    assert exc_info.value.status_code == 400


def test_update_team_404s_on_missing_team():
    db = make_db()
    with pytest.raises(HTTPException) as exc_info:
        update_team(999, TeamUpdate(group_name="A"), db)
    assert exc_info.value.status_code == 404


def test_tournament_state_includes_group_name():
    db = make_db()
    t, team = make_team(db)
    update_team(team.id, TeamUpdate(group_name="B"), db)

    state = tournament_state(t.id, db)

    assert state["teams"][0]["group_name"] == "B"


def test_add_missing_columns_alters_an_old_teams_table(tmp_path, monkeypatch):
    # A DB created before group_name existed: create_all() won't touch it.
    old_engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old_engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE teams (id INTEGER PRIMARY KEY, tournament_id INTEGER NOT NULL, code VARCHAR(20) NOT NULL)"
        )
        conn.exec_driver_sql("INSERT INTO teams (tournament_id, code) VALUES (1, 'A')")
    monkeypatch.setattr(database, "engine", old_engine)

    database.add_missing_columns()
    database.add_missing_columns()  # idempotent

    with old_engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(teams)")}
        row = conn.exec_driver_sql("SELECT code, group_name FROM teams").one()
    assert "group_name" in cols
    assert row == ("A", None)


def test_add_missing_columns_skips_a_table_that_does_not_exist_yet(tmp_path, monkeypatch):
    empty_engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(database, "engine", empty_engine)

    database.add_missing_columns()  # must not raise
