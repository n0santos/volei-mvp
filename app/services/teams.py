import random
from itertools import combinations

# Scores are assigned comparing players within their own gender group, not on
# one shared scale - a men's 80 and a women's 80 aren't the same level.
# Calibrated against the group: a men's 80 first looked like a women's 90 (+10),
# but a 2026-10-27 poll of 35 players, using ~14 woman-vs-man equivalences, put
# it nearer +5 (median +5, mean ~+1). Add this back only when comparing skill
# across genders for team balance.
MALE_ADJUSTMENT = 5

# How much worse than the best possible split a split may be and still be drawn
# from. Dozens of splits usually tie for practically the same balance, and
# always taking the first one put the same people against each other every
# single match of the night.
MIX_TOLERANCE = 10

# Tournament affinity: players who share a tournament team prefer the same side.
# Each teammate pair split across sides costs this much - above the gender
# penalty (8), so affinity usually wins. AFFINITY_MAX_DIFF is the guard rail:
# splits whose score gap exceeds it are dropped (unless nothing is closer), so
# keeping a tournament team together never produces a lopsided match.
AFFINITY_WEIGHT = 10
AFFINITY_MAX_DIFF = 20


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


def affinity_penalty(a, b, groups):
    # Teammate pairs (same tournament team) that end up on opposite sides.
    split = 0
    for g in {groups.get(p.id) for p in a} - {None}:
        split += sum(1 for p in a if groups.get(p.id) == g) * sum(1 for p in b if groups.get(p.id) == g)
    return split * AFFINITY_WEIGHT


def _best_full_split(players, groups):
    a_size = len(players) // 2

    splits = []

    for idxs in combinations(range(len(players)), a_size):
        idxs = set(idxs)
        a = [p for i, p in enumerate(players) if i in idxs]
        b = [p for i, p in enumerate(players) if i not in idxs]

        # Avoid duplicate A/B partition evaluations.
        if a and b and min(idxs) != 0:
            continue

        cost = _split_cost(a, b)
        if groups:
            cost += affinity_penalty(a, b, groups)
        splits.append((cost, a, b))

    if groups:
        gap = lambda s: abs(team_score(s[1]) - team_score(s[2]))
        limit = max(AFFINITY_MAX_DIFF, min(gap(s) for s in splits))
        splits = [s for s in splits if gap(s) <= limit]
    best_cost = min(s[0] for s in splits)

    close_enough = [s for s in splits if s[0] <= best_cost + MIX_TOLERANCE]
    cost, a, b = random.choice(close_enough)
    return a, b, cost


def balance_teams(players, groups=None):
    # groups: optional {player_id: tournament team id}; see AFFINITY_* above.
    if len(players) < 2:
        return players, [], 0.0

    a, b, _cost = _best_full_split(players, groups or {})
    return a, b, abs(team_score(a) - team_score(b))
