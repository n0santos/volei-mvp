"""Score balance for "against a team" nights.

The opponent is a fixed team, so what we can balance is the average skill of the
side the app drafts against the opponent's. It is only a tiebreak inside the
draft (see selection.BALANCE_WEIGHT): who plays is still decided by waiting
turns and the rest rule, never by score.
"""
import random
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from ..models import Player, Team, TeamPlayer
from .teams import effective_score

TEAM_SIZE = 6


def opponent_average(db: DBSession, opponent: str):
    """Average effective score of the whole roster of the team named `opponent`
    (reserves included: it is the team's level, not tonight's lineup). The
    newest tournament's team wins if the name repeats. None if unknown or empty."""
    team = db.execute(
        select(Team).where(Team.code == opponent).order_by(Team.id.desc())
    ).scalars().first()
    if not team:
        return None
    scores = [
        effective_score(p)
        for p in db.execute(
            select(Player).join(TeamPlayer, TeamPlayer.player_id == Player.id).where(TeamPlayer.team_id == team.id)
        ).scalars()
    ]
    return sum(scores) / len(scores) if scores else None


def _gap(ours, fill_ins, opponent_avg):
    """|our average - the opponent side's average| when `fill_ins` stand in for
    the people the team is short of (the rest of its side plays at its average)."""
    real = TEAM_SIZE - len(fill_ins)
    opponent_side = (opponent_avg * real + sum(effective_score(p) for p in fill_ins)) / TEAM_SIZE
    return abs(sum(effective_score(p) for p in ours) / TEAM_SIZE - opponent_side)


def best_split(players, missing, opponent_avg):
    """Of the 6 + `missing` drafted players, which `missing` go fill in for the
    opponent so both sides come out closest in average. Ties go to the draw.
    Returns (ours, fill_ins, gap)."""
    players = list(players)
    random.shuffle(players)
    best = None
    for idx in combinations(range(len(players)), missing):
        fill_ins = [players[i] for i in idx]
        ours = [p for i, p in enumerate(players) if i not in idx]
        gap = _gap(ours, fill_ins, opponent_avg)
        if best is None or gap < best[2] - 1e-9:
            best = (ours, fill_ins, gap)
    return best


def side_gap(players, missing, opponent_avg):
    """Gap of the best split of a candidate squad; the draft's balance term."""
    return best_split(players, missing, opponent_avg)[2]
