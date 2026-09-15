from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from ..models import Match, MatchPlayer, Player


def ranking(db: DBSession, session_id: int):
    """Wins per player over the night's matches that had a winner recorded.

    Ordered by win rate rather than total wins, so whoever stayed longest
    doesn't top the list just by playing more. Only starters count, matching
    the rule that filling in as a substitute isn't a match played.
    """
    rows = db.execute(
        select(MatchPlayer, Match, Player)
        .join(Match, Match.id == MatchPlayer.match_id)
        .join(Player, Player.id == MatchPlayer.player_id)
        .where(
            Match.session_id == session_id,
            Match.status == "finished",
            Match.winner.is_not(None),
            MatchPlayer.role == "starter",
        )
    ).all()

    stats = defaultdict(lambda: {"wins": 0, "played": 0})
    names = {}
    for mp, m, p in rows:
        names[p.id] = p.name
        stats[p.id]["played"] += 1
        stats[p.id]["wins"] += mp.team == m.winner

    result = [
        {"id": pid, "name": names[pid], **s, "rate": s["wins"] / s["played"]}
        for pid, s in stats.items()
    ]
    return sorted(result, key=lambda r: (-r["rate"], -r["wins"], r["name"]))
