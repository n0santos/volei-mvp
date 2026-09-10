import random
from itertools import combinations

# Scores are assigned comparing players within their own gender group, not on
# one shared scale - a men's 80 and a women's 80 aren't the same level.
# Calibrated against the group: a men's 80 plays like a women's 90, so add
# this back only when comparing skill across genders for team balance.
MALE_ADJUSTMENT = 10

# How much worse than the best possible split a split may be and still be drawn
# from. Dozens of splits usually tie for practically the same balance, and
# always taking the first one put the same people against each other every
# single match of the night.
MIX_TOLERANCE = 10


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


def _split_cost(a, b):
    diff = abs(team_score(a) - team_score(b))
    cost = diff + gender_penalty(a, b)
    # Small penalty for uneven average score when sizes differ.
    if a and b:
        cost += abs((team_score(a) / len(a)) - (team_score(b) / len(b))) * 2
    return cost


def _best_full_split(players):
    a_size = len(players) // 2

    splits = []
    best_cost = float("inf")

    for idxs in combinations(range(len(players)), a_size):
        idxs = set(idxs)
        a = [p for i, p in enumerate(players) if i in idxs]
        b = [p for i, p in enumerate(players) if i not in idxs]

        # Avoid duplicate A/B partition evaluations.
        if a and b and min(idxs) != 0:
            continue

        cost = _split_cost(a, b)
        splits.append((cost, a, b))
        if cost < best_cost:
            best_cost = cost

    close_enough = [s for s in splits if s[0] <= best_cost + MIX_TOLERANCE]
    cost, a, b = random.choice(close_enough)
    return a, b, cost


def balance_teams(players):
    if len(players) < 2:
        return players, [], 0.0

    a, b, _cost = _best_full_split(players)
    return a, b, abs(team_score(a) - team_score(b))
