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
