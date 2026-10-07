import random
from itertools import combinations
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from ..models import Attendance, Player, Match
from .fairness import history

# How many matches in a row send someone to the bench for the next one.
BLOCK_AFTER = 2
# Matches watched from the bench while present break ties between people with
# the same wait - whoever has been skipped most goes in first. Deliberately far
# below the weight of a match spent waiting, so it orders equals without ever
# outranking them.
SHARE_WEIGHT = 300
# Cost per score point of average gap between the two sides, only used when the
# caller passes `balance` ("against a team" nights). Kept small on purpose: a gap
# of 10 points costs 15, less than the 37 that one match of difference in share
# costs on an 8-match night, so it reorders people whose turns are equal but
# never outranks waiting or the rest rule.
BALANCE_WEIGHT = 1.5
# Average gap (score points) below which two sides count as balanced enough and
# the usual draw decides who plays. Without it the single best-balanced squad
# wins every time and the same people always get the shorter end of the rotation
# (measured: with 13 present, three people played one match fewer on every
# simulated night). At 3 the spread of matches per person matches the draw
# without balancing, and the gap between the sides still halves.
BALANCE_TOLERANCE = 3.0
# ...and whatever is within this many points of the best squad on offer counts as
# balanced too. The group put matches played first: at 8 the spread of matches per
# person is the same as the plain draw's with 10, 13 and 17 present (simulated),
# and balance only rules out the worst mismatches (worst gap 13 -> 9 points with
# 13 present). A smaller margin balances better but starts favoring who plays more.
BALANCE_MARGIN = 8.0


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


def without_players_needing_a_rest(available, hist, n, raffle):
    """Drop whoever already played BLOCK_AFTER matches in a row.

    Below 18 people a full court cannot be filled without them, so the rest is
    cancelled for exactly as many as the court is short - shortest streak first,
    then the draw - and never for anyone beyond that.
    """
    resting = [x for x in available if hist[x[1].id]["playing_streak"] >= BLOCK_AFTER]
    if not resting:
        return available

    playing = [x for x in available if hist[x[1].id]["playing_streak"] < BLOCK_AFTER]
    short_by = n - len(playing)
    if short_by <= 0:
        return playing

    called_back = sorted(
        resting, key=lambda x: (hist[x[1].id]["playing_streak"], raffle[x[1].id])
    )[:short_by]
    return playing + called_back


def select_players(db: DBSession, session_id: int, target: int = 12, balance=None):
    """`balance`, if given, maps a candidate squad (list of players) to a score
    gap; among squads with equal fairness the smaller gap wins."""
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
        return (
            -wait * 1000
            + played * 180
            + h["share"] * SHARE_WEIGHT
            + tiebreak(a, p)
        )

    available = without_players_needing_a_rest(available, hist, n, raffle)

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

    # The opening squad stays decided by arrival order, as the group agreed.
    gaps = {}
    if balance is not None and not is_first_match:
        for combo in combinations(pool, n):
            if forced_ids.issubset({p.id for _, p in combo}):
                gaps[tuple(p.id for _, p in combo)] = balance([p for _, p in combo])
    free_gap = max(BALANCE_TOLERANCE, min(gaps.values()) + BALANCE_MARGIN) if gaps else 0.0

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
            cost += h["share"] * SHARE_WEIGHT
            cost += tiebreak(a, p)
        if gaps:
            cost += BALANCE_WEIGHT * max(0.0, gaps[tuple(p.id for _, p in combo)] - free_gap)

        if cost < best_cost:
            best_cost = cost
            best = combo

    if best is None:
        best = ranked[:n]

    return [p for _, p in best]
