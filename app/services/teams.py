from itertools import combinations

# Scores are assigned comparing players within their own gender group, not on
# one shared scale - a men's 80 and a women's 80 aren't the same level.
# Calibrated against the group: a men's 80 plays like a women's 90, so add
# this back only when comparing skill across genders for team balance.
MALE_ADJUSTMENT = 10

# How much worse a continuity-preserving split is allowed to be than the
# best possible full reshuffle before we give up on preserving teams.
CONTINUITY_TOLERANCE = 20


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

    best = None
    best_cost = float("inf")

    for idxs in combinations(range(len(players)), a_size):
        idxs = set(idxs)
        a = [p for i, p in enumerate(players) if i in idxs]
        b = [p for i, p in enumerate(players) if i not in idxs]

        # Avoid duplicate A/B partition evaluations.
        if a and b and min(idxs) != 0:
            continue

        cost = _split_cost(a, b)
        if cost < best_cost:
            best_cost = cost
            best = (a, b)

    return best[0], best[1], best_cost


def _continuity_split(players, previous_teams):
    """Try to keep whoever was on team A/B last match on the same team,
    only deciding where newcomers go. Returns None when that isn't even
    possible without bumping someone who stayed (e.g. a team shrank)."""
    a_size = len(players) // 2
    b_size = len(players) - a_size

    kept_a = [p for p in players if previous_teams.get(p.id) == "A"]
    kept_b = [p for p in players if previous_teams.get(p.id) == "B"]
    newcomers = [p for p in players if p.id not in previous_teams]

    if len(kept_a) > a_size or len(kept_b) > b_size:
        return None

    a_needed = a_size - len(kept_a)
    b_needed = b_size - len(kept_b)
    if a_needed + b_needed != len(newcomers):
        return None

    if not newcomers:
        return kept_a, kept_b, _split_cost(kept_a, kept_b)

    best = None
    best_cost = float("inf")
    for combo in combinations(newcomers, a_needed):
        a = kept_a + list(combo)
        b = kept_b + [p for p in newcomers if p not in combo]
        cost = _split_cost(a, b)
        if cost < best_cost:
            best_cost = cost
            best = (a, b)

    return best[0], best[1], best_cost


def balance_teams(players, previous_teams=None):
    if len(players) < 2:
        return players, [], 0.0

    full_a, full_b, full_cost = _best_full_split(players)

    if previous_teams:
        continuity = _continuity_split(players, previous_teams)
        if continuity is not None:
            cont_a, cont_b, cont_cost = continuity
            if cont_cost <= full_cost + CONTINUITY_TOLERANCE:
                return cont_a, cont_b, abs(team_score(cont_a) - team_score(cont_b))

    return full_a, full_b, abs(team_score(full_a) - team_score(full_b))
