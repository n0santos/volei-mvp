from itertools import combinations

# Scores are assigned comparing players within their own gender group, not on
# one shared scale - a men's 80 and a women's 80 aren't the same level.
# Calibrated against the group: a men's 80 plays like a women's 90, so add
# this back only when comparing skill across genders for team balance.
MALE_ADJUSTMENT = 10


def effective_score(p):
    return p.score + (MALE_ADJUSTMENT if p.gender == "M" else 0)


def team_score(players):
    return sum(effective_score(p) for p in players)


def gender_penalty(a, b):
    # Preference, not a hard constraint.
    # Penalize imbalance in number of M/F.
    af = sum(1 for p in a if p.gender == "F")
    am = sum(1 for p in a if p.gender == "M")
    bf = sum(1 for p in b if p.gender == "F")
    bm = sum(1 for p in b if p.gender == "M")
    return abs(af - bf) * 8 + abs(am - bm) * 8


def balance_teams(players):
    if len(players) < 2:
        return players, [], 0.0

    # Teams should be as even as possible.
    a_size = len(players) // 2
    if len(players) % 2:
        a_size = len(players) // 2

    best = None
    best_cost = float("inf")
    total = team_score(players)

    for idxs in combinations(range(len(players)), a_size):
        idxs = set(idxs)
        a = [p for i, p in enumerate(players) if i in idxs]
        b = [p for i, p in enumerate(players) if i not in idxs]

        # Avoid duplicate A/B partition evaluations.
        if a and b and min(i for i in idxs) != 0:
            continue

        diff = abs(team_score(a) - team_score(b))
        # Normalize gender penalty by expected team size.
        cost = diff + gender_penalty(a, b)

        # Small penalty for uneven average score when sizes differ.
        if len(a) and len(b):
            cost += abs((team_score(a) / len(a)) - (team_score(b) / len(b))) * 2

        if cost < best_cost:
            best_cost = cost
            best = (a, b)

    a, b = best
    return a, b, abs(team_score(a) - team_score(b))
