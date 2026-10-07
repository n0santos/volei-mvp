import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.schemas import TeamUpdate
from app.tournament import update_team


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_update_team_404s_on_missing_team():
    db = make_db()
    with pytest.raises(HTTPException) as exc_info:
        update_team(999, TeamUpdate(max_players=7), db)
    assert exc_info.value.status_code == 404


def test_add_missing_columns_gives_old_teams_a_limit_of_seven(tmp_path, monkeypatch):
    old_engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old_engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE teams (id INTEGER PRIMARY KEY, tournament_id INTEGER NOT NULL, code VARCHAR(20) NOT NULL)"
        )
        conn.exec_driver_sql("INSERT INTO teams (tournament_id, code) VALUES (1, 'A')")
    monkeypatch.setattr(database, "engine", old_engine)

    database.add_missing_columns()

    with old_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT max_players FROM teams").scalar() == 7


def test_add_missing_columns_skips_a_table_that_does_not_exist_yet(tmp_path, monkeypatch):
    empty_engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(database, "engine", empty_engine)

    database.add_missing_columns()  # must not raise
