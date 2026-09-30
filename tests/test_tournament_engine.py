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
