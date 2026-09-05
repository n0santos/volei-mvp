import random
from itertools import combinations
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from ..models import Attendance, Player, Match
from .fairness import history


def eligible_players(db: DBSession, session_id: int):
    rows = db.execute(
        select(Attendance, Player)
        .join(Player, Player.id == Attendance.player_id)
        .where(
            Attendance.session_id == session_id,
            Attendance.status == "arrived"
        )
        .order_by(Attendance.arrival_order)
    ).all()
    return [(a, p) for a, p in rows]


def select_players(db: DBSession, session_id: int, target: int = 12):
    available = eligible_players(db, session_id)
    if not available:
        return []

    n = min(target, len(available))
    if n < 2:
        return [p for _, p in available]

    hist = history(db, session_id)

    # Before the first match, everyone is tied at zero wait/played/minutes -
    # whoever checked in earliest gets the opening spots. Once matches start
    # happening, ties are resolved by a random draw each time a match is
    # generated instead - like the group's usual "adedonha" - rather than
    # always favoring the same person (e.g. whoever arrived earliest).
    is_first_match = not db.execute(
        select(Match.id).where(Match.session_id == session_id, Match.status == "finished")
    ).first()

    raffle = {p.id: random.random() for _, p in available}

    def tiebreak(a, p):
        return (a.arrival_order or 9999) * 0.01 if is_first_match else raffle[p.id]

    def priority(pair):
        a, p = pair
        h = hist[p.id]
        # Lower priority score is better.
        # Large reward for having waited multiple matches.
        wait = h["outside_streak"]
        played = h["playing_streak"]
        minutes = h["minutes"]
        return (
            -wait * 1000
            + played * 180
            + minutes * 0.25
            + tiebreak(a, p)
        )

    ranked = sorted(available, key=priority)

    # For fairness, start with the best candidates but evaluate nearby
    # combinations so the result is not simply a static queue.
    pool = ranked[:min(len(ranked), n + 6)]

    if len(pool) <= n:
        return [p for _, p in pool]

    # Hard-ish fairness rule: if someone has waited >= 2 completed matches,
    # include them whenever mathematically possible.
    forced = [x for x in pool if hist[x[1].id]["outside_streak"] >= 2]
    forced_ids = {p.id for _, p in forced}
    if len(forced) > n:
        forced = forced[:n]
        forced_ids = {p.id for _, p in forced}

    best = None
    best_cost = float("inf")

    for combo in combinations(pool, n):
        ids = {p.id for _, p in combo}
        if not forced_ids.issubset(ids):
            continue

        cost = 0
        for a, p in combo:
            h = hist[p.id]
            # Favor waiting, penalize consecutive playing.
            cost += h["playing_streak"] * 180
            cost -= h["outside_streak"] * 1000
            cost += h["minutes"] * 0.25
            cost += tiebreak(a, p)

        # Penalize selecting too many people who just played.
        cost += sum(120 for _, p in combo if hist[p.id]["playing_streak"] >= 2)

        if cost < best_cost:
            best_cost = cost
            best = combo

    if best is None:
        best = ranked[:n]

    return [p for _, p in best]
