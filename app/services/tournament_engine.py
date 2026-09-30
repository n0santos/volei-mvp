SET_TARGETS = {1: 18, 2: 18, 3: 15}


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
