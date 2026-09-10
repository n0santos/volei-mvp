from types import SimpleNamespace
from app.services.teams import balance_teams

_next_id = [0]


def p(name, score, gender="X"):
    _next_id[0] += 1
    return SimpleNamespace(id=_next_id[0], name=name, score=score, gender=gender)


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


def test_evenly_splits_a_lopsided_group():
    # Six strong players and six weak ones must not end up stacked on one side.
    strong = [p(f"s{i}", 95) for i in range(6)]
    weak = [p(f"w{i}", 45) for i in range(6)]

    a, b, diff = balance_teams(strong + weak)
    assert diff <= 10


def doze_jogadores():
    return [
        p(f"P{i}", score, gender)
        for i, (score, gender) in enumerate([
            (90, "F"), (85, "M"), (80, "F"), (80, "M"), (75, "F"), (70, "M"),
            (70, "F"), (65, "M"), (60, "F"), (60, "M"), (55, "F"), (50, "M"),
        ])
    ]


def test_same_group_does_not_always_split_the_same_way():
    # When the same twelve come back to the court, always computing the single
    # best split put them against exactly the same faces every time. Any split
    # of near-equal balance does the job, so the choice is drawn instead.
    jogadores = doze_jogadores()

    seen = set()
    for _ in range(30):
        a, _b, _diff = balance_teams(jogadores)
        seen.add(frozenset(x.name for x in a))

    assert len(seen) > 1, "a mesma divisão saiu 30 vezes seguidas"


def test_mixing_keeps_the_teams_balanced():
    jogadores = doze_jogadores()

    for _ in range(30):
        a, b, diff = balance_teams(jogadores)
        assert len(a) == len(b) == 6
        assert diff <= 25, f"times ficaram desequilibrados: diferença {diff}"
