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


def test_preserves_teams_when_composition_barely_changes():
    players = [p(str(i), 70) for i in range(12)]
    a1, b1, _ = balance_teams(players)

    previous_teams = {pl.id: "A" for pl in a1}
    previous_teams.update({pl.id: "B" for pl in b1})

    # One player from team A leaves, a newcomer with the same score joins.
    outgoing = a1[0]
    newcomer = p("newcomer", outgoing.score)
    next_group = [pl for pl in players if pl.id != outgoing.id] + [newcomer]

    a2, b2, diff2 = balance_teams(next_group, previous_teams)

    ids = lambda players: {pl.id for pl in players}
    assert ids(b2) == ids(b1), "team B had no reason to change but got reshuffled"
    assert ids(a2) == ids(a1[1:]) | {newcomer.id}


def test_falls_back_to_full_reshuffle_when_continuity_too_unbalanced():
    # Deliberately construct a badly balanced "previous" assignment (every
    # strong player on one side). If the roster is unchanged, blindly
    # preserving it would keep a huge gap that a full reshuffle would fix.
    strong = [p(f"s{i}", 95) for i in range(6)]
    weak = [p(f"w{i}", 45) for i in range(6)]
    previous_teams = {pl.id: "A" for pl in strong}
    previous_teams.update({pl.id: "B" for pl in weak})

    a, b, diff = balance_teams(strong + weak, previous_teams)
    assert diff <= 10
