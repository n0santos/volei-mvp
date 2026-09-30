from .teams import effective_score

GENDER_WEIGHT = 8
MAX_HILL_CLIMB_ITERATIONS = 500


def team_score(players):
    return sum(effective_score(p) for p in players)


def _gender_imbalance(teams):
    counts_f = [sum(1 for p in t if p.gender == "F") for t in teams]
    counts_m = [sum(1 for p in t if p.gender == "M") for t in teams]
    avg_f = sum(counts_f) / len(teams)
    avg_m = sum(counts_m) / len(teams)
    return (
        sum(abs(c - avg_f) for c in counts_f) * GENDER_WEIGHT
        + sum(abs(c - avg_m) for c in counts_m) * GENDER_WEIGHT
    )


def _cost(teams):
    scores = [team_score(t) for t in teams]
    return (max(scores) - min(scores)) + _gender_imbalance(teams)


def _snake_draft(players, num_teams):
    ordered = sorted(players, key=effective_score, reverse=True)
    teams = [[] for _ in range(num_teams)]
    order = list(range(num_teams))
    i = 0
    for player in ordered:
        teams[order[i]].append(player)
        i += 1
        if i == len(order):
            order.reverse()
            i = 0
    return teams


def _hill_climb(teams):
    teams = [list(t) for t in teams]
    best_cost = _cost(teams)
    improved = True
    iterations = 0
    while improved and iterations < MAX_HILL_CLIMB_ITERATIONS:
        improved = False
        iterations += 1
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                for a in range(len(teams[i])):
                    for b in range(len(teams[j])):
                        teams[i][a], teams[j][b] = teams[j][b], teams[i][a]
                        cost = _cost(teams)
                        if cost < best_cost:
                            best_cost = cost
                            improved = True
                        else:
                            teams[i][a], teams[j][b] = teams[j][b], teams[i][a]
    return teams


def form_teams(players, num_teams):
    if num_teams < 2:
        raise ValueError("form_teams precisa de pelo menos 2 times")
    if len(players) < num_teams:
        raise ValueError("menos jogadores do que times")
    return _hill_climb(_snake_draft(players, num_teams))
