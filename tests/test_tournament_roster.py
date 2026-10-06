from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.tournament import (
    create_tournament, active_tournament, create_team, tournament_state,
    add_team_player, update_team_player, remove_team_player, update_team,
)
from app.schemas import (
    TournamentCreate, TeamCreate, TeamPlayerAdd, TeamPlayerUpdate, TeamUpdate,
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


def make_team_with_players(db, n):
    team, _ = make_team_with_player(db)
    players = []
    for i in range(n):
        player = Player(name=f"Jogador {i}", score=70, gender="F")
        db.add(player)
        players.append(player)
    db.commit()
    return team, players


def test_a_team_cannot_have_more_than_seven_players():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, players = make_team_with_players(db, 8)
    for player in players[:7]:
        add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)

    with pytest.raises(HTTPException) as exc_info:
        add_team_player(team.id, TeamPlayerAdd(player_id=players[7].id), db)
    assert exc_info.value.status_code == 409


def test_a_team_with_seven_can_free_a_spot_by_removing_someone():
    db = make_db()
    team, players = make_team_with_players(db, 8)
    for player in players[:7]:
        add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)

    remove_team_player(team.id, players[0].id, db)
    add_team_player(team.id, TeamPlayerAdd(player_id=players[7].id), db)  # no error


def test_a_team_cannot_have_two_reserves():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, players = make_team_with_players(db, 2)
    add_team_player(team.id, TeamPlayerAdd(player_id=players[0].id, role="reserva"), db)

    with pytest.raises(HTTPException) as exc_info:
        add_team_player(team.id, TeamPlayerAdd(player_id=players[1].id, role="reserva"), db)
    assert exc_info.value.status_code == 409


def test_cannot_turn_a_second_player_into_a_reserve():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, players = make_team_with_players(db, 2)
    add_team_player(team.id, TeamPlayerAdd(player_id=players[0].id, role="reserva"), db)
    add_team_player(team.id, TeamPlayerAdd(player_id=players[1].id), db)

    with pytest.raises(HTTPException) as exc_info:
        update_team_player(team.id, players[1].id, TeamPlayerUpdate(role="reserva"), db)
    assert exc_info.value.status_code == 409


def test_the_current_reserve_can_be_set_to_reserve_again():
    db = make_db()
    team, players = make_team_with_players(db, 1)
    add_team_player(team.id, TeamPlayerAdd(player_id=players[0].id, role="reserva"), db)

    update_team_player(team.id, players[0].id, TeamPlayerUpdate(role="reserva"), db)  # no error


def test_a_team_starts_with_the_regulation_limit_of_seven():
    db = make_db()
    team, _ = make_team_with_player(db)
    assert team.max_players == 7
    assert tournament_state(team.tournament_id, db)["teams"][0]["max_players"] == 7


def test_a_team_allowed_eight_takes_eight_but_not_nine():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, players = make_team_with_players(db, 9)
    update_team(team.id, TeamUpdate(max_players=8), db)
    for player in players[:8]:
        add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)

    with pytest.raises(HTTPException) as exc_info:
        add_team_player(team.id, TeamPlayerAdd(player_id=players[8].id), db)
    assert exc_info.value.status_code == 409


def test_raising_one_teams_limit_does_not_raise_the_others():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, players = make_team_with_players(db, 8)
    other = create_team(team.tournament_id, TeamCreate(code="B"), db)
    update_team(team.id, TeamUpdate(max_players=8), db)
    for player in players[:7]:
        add_team_player(other.id, TeamPlayerAdd(player_id=player.id), db)

    with pytest.raises(HTTPException) as exc_info:
        add_team_player(other.id, TeamPlayerAdd(player_id=players[7].id), db)
    assert exc_info.value.status_code == 409


def test_two_reserves_need_a_limit_of_eight():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, players = make_team_with_players(db, 2)
    add_team_player(team.id, TeamPlayerAdd(player_id=players[0].id, role="reserva"), db)
    with pytest.raises(HTTPException):
        add_team_player(team.id, TeamPlayerAdd(player_id=players[1].id, role="reserva"), db)

    update_team(team.id, TeamUpdate(max_players=8), db)
    add_team_player(team.id, TeamPlayerAdd(player_id=players[1].id, role="reserva"), db)  # no error


def test_team_limit_only_accepts_seven_or_eight():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, _ = make_team_with_player(db)
    for bad in (6, 9, 100):
        with pytest.raises(HTTPException) as exc_info:
            update_team(team.id, TeamUpdate(max_players=bad), db)
        assert exc_info.value.status_code == 400


def test_cannot_lower_the_limit_below_the_current_roster():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, players = make_team_with_players(db, 8)
    update_team(team.id, TeamUpdate(max_players=8), db)
    for player in players[:8]:
        add_team_player(team.id, TeamPlayerAdd(player_id=player.id), db)

    with pytest.raises(HTTPException) as exc_info:
        update_team(team.id, TeamUpdate(max_players=7), db)
    assert exc_info.value.status_code == 409
    assert team.max_players == 8


def test_cannot_lower_the_limit_while_the_team_has_two_reserves():
    import pytest
    from fastapi import HTTPException

    db = make_db()
    team, players = make_team_with_players(db, 2)
    update_team(team.id, TeamUpdate(max_players=8), db)
    for player in players:
        add_team_player(team.id, TeamPlayerAdd(player_id=player.id, role="reserva"), db)

    with pytest.raises(HTTPException) as exc_info:
        update_team(team.id, TeamUpdate(max_players=7), db)
    assert exc_info.value.status_code == 409

