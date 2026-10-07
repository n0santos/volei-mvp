SET_TARGETS = {1: 15, 2: 15, 3: 18}

# One overall table of 6 teams, 3 games each: the draw assigns the teams to
# slots A-F, and these 9 pairings are played in this order.
DRAW_SLOTS = ("A", "B", "C", "D", "E", "F")
DRAW_FIXTURES = (
    ("A", "B"), ("C", "D"), ("E", "F"),
    ("A", "C"), ("B", "E"), ("D", "F"),
    ("A", "D"), ("B", "F"), ("C", "E"),
)
QUALIFIED = 4  # the top 4 go to the semifinals


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
    # Regulation, in order: points, wins, set balance, point balance. What's
    # still equal after this goes to head-to-head, then to a draw by the
    # organization (_resolve_ties).
    return (
        -row["tournament_points"],
        -row["wins"],
        -row["sets_balance"],
        -row["points_balance"],
    )


def _resolve_ties(standings, head_to_head):
    """Reorder `standings` (already sorted by _standings_sort_key) and set
    each row's `rank` and `tied`.

    Head-to-head only breaks a tie between exactly two teams, by who won the
    match(es) between them. With three or more tied it doesn't apply (it can
    be a cycle), and a two-way tie with no winner between them stays a tie -
    both are left for the organization's draw. Rows still tied share a rank.
    """
    resolved = []
    i = 0
    while i < len(standings):
        j = i
        while j + 1 < len(standings) and _standings_sort_key(standings[j + 1]) == _standings_sort_key(standings[i]):
            j += 1
        run = standings[i:j + 1]

        if len(run) == 2:
            x, y = run
            x_wins = head_to_head.get((x["team"], y["team"]), 0)
            y_wins = head_to_head.get((y["team"], x["team"]), 0)
            if x_wins != y_wins:
                run = [x, y] if x_wins > y_wins else [y, x]
                for offset, row in enumerate(run):
                    row["rank"] = i + 1 + offset
                    row["tied"] = False
                resolved += run
                i = j + 1
                continue

        # Teams that haven't played yet are all equal but not "tied" in any
        # meaningful sense, so don't flag them (they still share a rank).
        any_played = any(row["wins"] + row["losses"] > 0 for row in run)
        for row in run:
            row["rank"] = i + 1
            row["tied"] = len(run) > 1 and any_played
        resolved += run
        i = j + 1

    standings[:] = resolved


def mark_qualified(standings, slots):
    """Flag the top `slots` rows as qualified, unless the last slot is tied
    with the first team left out - picking one of them would be arbitrary.
    Call only once the table is complete: with games still to play the order
    isn't final."""
    for s in standings:
        s["qualified"] = False
    cut_is_tied = len(standings) > slots and standings[slots - 1]["rank"] == standings[slots]["rank"]
    if not cut_is_tied:
        for s in standings[:slots]:
            s["qualified"] = True


def compute_standings(matches, teams=()):
    """`teams` lists names that must appear even with no match played (kept
    first-come order among equals)."""
    rows = {}
    head_to_head = {}  # (winner, loser) -> how many times winner beat loser

    def row(name):
        return rows.setdefault(name, _new_team_row(name))

    for name in teams:
        row(name)

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
            head_to_head[(match.team_a, match.team_b)] = head_to_head.get((match.team_a, match.team_b), 0) + 1
        elif result["winner"] == "B":
            b["wins"] += 1
            a["losses"] += 1
            head_to_head[(match.team_b, match.team_a)] = head_to_head.get((match.team_b, match.team_a), 0) + 1

        a["tournament_points"] += match_points(result["sets_a"], result["sets_b"])
        b["tournament_points"] += match_points(result["sets_b"], result["sets_a"])

    standings = list(rows.values())
    for s in standings:
        s["sets_balance"] = s["sets_for"] - s["sets_against"]
        s["points_balance"] = s["points_for"] - s["points_against"]

    standings.sort(key=_standings_sort_key)
    _resolve_ties(standings, head_to_head)

    return standings
