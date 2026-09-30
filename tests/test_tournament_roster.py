from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.tournament import (
    create_tournament, active_tournament, create_team, tournament_state,
    add_team_player, update_team_player, remove_team_player,
    form_tournament_teams,
)
from app.schemas import (
    TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamFormRequest,
)
from app.models import Player


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


def test_adding_player_already_on_another_team_of_same_tournament_raises_conflict():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team_a, player = make_team_with_player(db)
    team_b = create_team(team_a.tournament_id, TeamCreate(code="B"), db)
    add_team_player(team_a.id, TeamPlayerAdd(player_id=player.id), db)

    with pytest.raises(HTTPException) as exc_info:
        add_team_player(team_b.id, TeamPlayerAdd(player_id=player.id), db)
    assert exc_info.value.detail == "Jogador já está em outro time deste torneio"


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

    with pytest.raises(HTTPException) as exc_info:
        form_tournament_teams(t.id, TeamFormRequest(player_ids=[player.id]), db)
    assert exc_info.value.status_code == 400


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

    with pytest.raises(HTTPException) as exc_info:
        form_tournament_teams(t.id, TeamFormRequest(player_ids=[p2.id]), db)
    assert exc_info.value.status_code == 409


def test_form_teams_404s_on_missing_player():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, teams = make_tournament_with_teams(db, ["A", "B"])
    known = Player(name="Known", score=70, gender="X")
    db.add(known)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        form_tournament_teams(t.id, TeamFormRequest(player_ids=[known.id, 999]), db)
    assert exc_info.value.status_code == 404


def test_form_teams_requires_at_least_one_player_per_team():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, teams = make_tournament_with_teams(db, ["A", "B"])
    p1 = Player(name="P1", score=70, gender="X")
    db.add(p1)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        form_tournament_teams(t.id, TeamFormRequest(player_ids=[p1.id]), db)
    assert exc_info.value.status_code == 400


def test_form_teams_rejects_duplicate_player_ids():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    t, teams = make_tournament_with_teams(db, ["A", "B"])
    p1 = Player(name="P1", score=70, gender="X")
    p2 = Player(name="P2", score=70, gender="X")
    db.add_all([p1, p2])
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        form_tournament_teams(t.id, TeamFormRequest(player_ids=[p1.id, p1.id]), db)
    assert exc_info.value.status_code == 400
