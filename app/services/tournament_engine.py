SET_TARGETS = {1: 18, 2: 18, 3: 15}


def is_set_over(a, b, target):
    return max(a, b) >= target and abs(a - b) >= 2


def set_winner(a, b, target):
    if not is_set_over(a, b, target):
        return None
    return "A" if a > b else "B"
