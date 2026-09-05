from types import SimpleNamespace
from app.services.teams import balance_teams


def p(name, score, gender="X"):
    return SimpleNamespace(name=name, score=score, gender=gender)


def test_balanced_scores():
    players = [p(str(i), s) for i, s in enumerate([90, 89, 80, 79, 70, 69, 60, 59, 50, 49, 40, 39])]
    a, b, diff = balance_teams(players)
    assert len(a) == 6
    assert len(b) == 6
    assert diff <= 2


def test_gender_adjustment_treats_men_as_stronger():
    # Calibrated against the group: a men's 80 plays like a women's 90, so
    # pairing them should read as balanced despite the raw 10-point gap.
    a, b, diff = balance_teams([p("M1", 80, "M"), p("F1", 90, "F")])
    assert diff == 0
