SET_TARGETS = {1: 15, 2: 15, 3: 18}


def is_set_over(a, b, target):
    return max(a, b) >= target and abs(a - b) >= 2


def set_winner(a, b, target):
    if not is_set_over(a, b, target):
        return None
    return "A" if a > b else "B"


def match_points(sets_a, sets_b):
    table = {(2, 0): 3, (2, 1): 2, (1, 2): 1, (0, 2): 0}
    if (sets_a, sets_b) not in table:
        raise ValueError(f"placar de sets inválido para pontuação: {sets_a}x{sets_b}")
    return table[(sets_a, sets_b)]


def match_result(sets):
    sets_a = sum(1 for a, b in sets if a > b)
    sets_b = sum(1 for a, b in sets if b > a)
    points_a = sum(a for a, b in sets)
    points_b = sum(b for a, b in sets)

    if sets_a == 2:
        winner = "A"
    elif sets_b == 2:
        winner = "B"
    else:
        winner = None

    return {
        "winner": winner,
        "sets_a": sets_a,
        "sets_b": sets_b,
        "points_a": points_a,
        "points_b": points_b,
    }


def _new_team_row(name):
    return {
        "team": name,
        "wins": 0,
        "losses": 0,
        "sets_for": 0,
        "sets_against": 0,
        "points_for": 0,
        "points_against": 0,
        "tournament_points": 0,
    }


def _standings_sort_key(row):
    return (
        -row["tournament_points"],
        -row["wins"],
        -row["sets_balance"],
        -row["points_balance"],
        -row["points_for"],
    )


def mark_qualified(standings, slots=2):
    """Flag the top `slots` rows as qualified, unless the last slot is tied
    with the first team left out - picking one of them would be arbitrary.
    Call only once the group is complete: with games still to play the order
    isn't final."""
    for s in standings:
        s["qualified"] = False
    cut_is_tied = (
        len(standings) > slots
        and _standings_sort_key(standings[slots - 1]) == _standings_sort_key(standings[slots])
    )
    if not cut_is_tied:
        for s in standings[:slots]:
            s["qualified"] = True


def compute_standings(matches):
    teams = {}

    def row(name):
        return teams.setdefault(name, _new_team_row(name))

    for match in matches:
        result = match_result(match.sets)
        a = row(match.team_a)
        b = row(match.team_b)

        a["sets_for"] += result["sets_a"]
        a["sets_against"] += result["sets_b"]
        a["points_for"] += result["points_a"]
        a["points_against"] += result["points_b"]

        b["sets_for"] += result["sets_b"]
        b["sets_against"] += result["sets_a"]
        b["points_for"] += result["points_b"]
        b["points_against"] += result["points_a"]

        if result["winner"] == "A":
            a["wins"] += 1
            b["losses"] += 1
        elif result["winner"] == "B":
            b["wins"] += 1
            a["losses"] += 1

        a["tournament_points"] += match_points(result["sets_a"], result["sets_b"])
        b["tournament_points"] += match_points(result["sets_b"], result["sets_a"])

    standings = list(teams.values())
    for s in standings:
        s["sets_balance"] = s["sets_for"] - s["sets_against"]
        s["points_balance"] = s["points_for"] - s["points_against"]

    standings.sort(key=_standings_sort_key)

    for s in standings:
        s["tied"] = False
    for i in range(len(standings) - 1):
        if _standings_sort_key(standings[i]) == _standings_sort_key(standings[i + 1]):
            standings[i]["tied"] = True
            standings[i + 1]["tied"] = True

    return standings
