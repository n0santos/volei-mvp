from collections import defaultdict
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from ..models import Attendance, Match, MatchPlayer


def history(db: DBSession, session_id: int):
    rows = db.execute(
        select(MatchPlayer, Match)
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(Match.session_id == session_id)
    ).all()

    h = defaultdict(lambda: {
        "matches": 0,
        "minutes": 0.0,
        "outside_streak": 0,
        "playing_streak": 0,
        "last_match": 0,
        "last_exit": None,
    })

    completed = db.execute(
        select(Match).where(
            Match.session_id == session_id,
            Match.status == "finished"
        ).order_by(Match.number)
    ).scalars().all()

    for mp, match in rows:
        if match.status not in ("finished", "running"):
            continue
        item = h[mp.player_id]
        if mp.role == "starter" and match.status == "finished":
            item["matches"] += 1
        if mp.entered_at and mp.exited_at:
            item["minutes"] += max(
                0, (mp.exited_at - mp.entered_at).total_seconds() / 60
            )
        elif mp.entered_at and match.ended_at:
            item["minutes"] += max(
                0, (match.ended_at - mp.entered_at).total_seconds() / 60
            )
        item["last_match"] = max(item["last_match"], match.number)

    # Consecutive finished matches are calculated by checking participation.
    all_mps = db.execute(
        select(MatchPlayer, Match)
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(Match.session_id == session_id)
    ).all()

    participation = defaultdict(set)
    for mp, match in all_mps:
        if match.status == "finished":
            participation[match.number].add(mp.player_id)

    # Every player who has ever checked in this session needs a streak,
    # even if they have never been picked for a match - otherwise someone
    # who is repeatedly skipped never accumulates an outside_streak (their
    # entry never gets created above) and the "force them in after 2
    # misses" rule in selection.py can never trigger for them.
    attendees = db.execute(
        select(Attendance).where(
            Attendance.session_id == session_id,
            Attendance.arrived_at.is_not(None),
        )
    ).scalars().all()

    for a in attendees:
        pid = a.player_id
        # Only matches that happened while this player was actually present
        # count toward their streak - matches before they arrived, or after
        # they left, aren't time they spent "waiting".
        relevant = [
            m for m in completed
            if m.started_at is None
            or (
                (a.arrived_at is None or m.started_at >= a.arrived_at)
                and (a.left_at is None or m.started_at <= a.left_at)
            )
        ]
        trailing_out = 0
        trailing_in = 0
        for m in reversed(relevant):
            if pid in participation[m.number]:
                if trailing_out == 0:
                    trailing_in += 1
                else:
                    break
            else:
                if trailing_in == 0:
                    trailing_out += 1
                else:
                    break
        item = h[pid]
        item["outside_streak"] = trailing_out
        item["playing_streak"] = trailing_in

    return h
