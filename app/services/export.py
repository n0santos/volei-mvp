import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from ..models import Match, MatchPlayer, Player
from .teams import effective_score

# A finished match this short was a mis-tap (started and ended by accident),
# not a game - flag it so analysis can drop it.
MIN_VALID_SECONDS = 60

COLUMNS = [
    "sessao", "partida", "inicio", "fim", "vencedor", "valida", "motivo_invalida",
    "time", "jogadores_titulares_time", "soma_score_titulares_time", "soma_efetiva_titulares_time",
    "jogador", "genero", "score_atual", "papel", "entrou", "saiu",
]


def history_rows(db: DBSession, session_name: str, session_id: int) -> list[dict]:
    """One row per player stint of every finished match, with the team's
    starter count and score sums repeated on each row for easy filtering.
    Scores are the players' *current* ones, not a snapshot from match time."""
    matches = db.execute(
        select(Match).where(Match.session_id == session_id, Match.status == "finished").order_by(Match.number)
    ).scalars().all()

    rows = []
    for m in matches:
        stints = db.execute(
            select(MatchPlayer, Player)
            .join(Player, Player.id == MatchPlayer.player_id)
            .where(MatchPlayer.match_id == m.id)
            .order_by(MatchPlayer.team, MatchPlayer.id)
        ).all()
        starters = {}
        for mp, p in stints:
            if mp.role == "starter":
                starters.setdefault(mp.team, []).append(p)

        seconds = (m.ended_at - m.started_at).total_seconds() if m.started_at and m.ended_at else None
        short = seconds is not None and seconds < MIN_VALID_SECONDS
        for mp, p in sorted(stints, key=lambda s: (s[0].team, s[0].id)):
            team = starters.get(mp.team, [])
            rows.append({
                "sessao": session_name,
                "partida": m.number,
                "inicio": m.started_at,
                "fim": m.ended_at,
                "vencedor": m.winner or "",
                "valida": "nao" if short else "sim",
                "motivo_invalida": f"durou {seconds:.0f} segundos" if short else "",
                "time": mp.team,
                "jogadores_titulares_time": len(team),
                "soma_score_titulares_time": sum(x.score for x in team),
                "soma_efetiva_titulares_time": sum(effective_score(x) for x in team),
                "jogador": p.name,
                "genero": p.gender,
                "score_atual": p.score,
                "papel": mp.role,
                "entrou": mp.entered_at,
                "saiu": mp.exited_at or "",
            })
    return rows


def history_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()
