import pytest
from app.services.tournament_engine import SET_TARGETS, is_set_over, set_winner, match_points, match_result


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
