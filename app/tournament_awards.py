"""Individual awards (MVPs and the fighting-spirit prizes). The committee picks
the winners; a referee login sets them on the page, everyone else only sees them.
Writes live under /api/tournaments, so arbitro.referee_guard covers them."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from .database import get_db
from .models import Player, Team, TeamPlayer, TournamentAward
from .tournament import get_tournament

router = APIRouter()

AWARDS = (
    {"key": "mvp_m", "gender": "M", "title": "Melhor Jogador (MVP Masculino)",
     "description": "Decisivo em cada ponto. O craque que fez a diferença no torneio."},
    {"key": "mvp_f", "gender": "F", "title": "Melhor Jogadora (MVP Feminino)",
     "description": "Talento, visão de jogo e liderança. O grande destaque feminino da quadra."},
    {"key": "raca_m", "gender": "M", "title": "Prêmio Raça, Paixão e Espírito Esportivo (Masculino)",
     "description": "O coração do time em quadra. Exemplo de garra, alegria e espírito esportivo."},
    {"key": "raca_f", "gender": "F", "title": "Prêmio Raça, Paixão e Espírito Esportivo (Feminino)",
     "description": "Jogar com alma transforma o jogo. Obrigado por elevar a energia do torneio!"},
)
AWARD_KEYS = {a["key"]: a for a in AWARDS}


class AwardWinner(BaseModel):
    player_id: int | None = None  # None clears the winner


def roster(db, tournament_id):
    """player_id -> (player, team code) for everyone on a team of this tournament."""
    rows = db.execute(
        select(Player, Team.code)
        .join(TeamPlayer, TeamPlayer.player_id == Player.id)
        .join(Team, Team.id == TeamPlayer.team_id)
        .where(Team.tournament_id == tournament_id)
    ).all()
    return {p.id: (p, code) for p, code in rows}


@router.get("/api/tournaments/{tournament_id}/awards")
def list_awards(tournament_id: int, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    athletes = roster(db, tournament_id)
    chosen = {
        a.award_key: a.player_id
        for a in db.execute(select(TournamentAward).where(TournamentAward.tournament_id == tournament_id)).scalars()
    }
    result = []
    for award in AWARDS:
        winner = None
        pid = chosen.get(award["key"])
        if pid is not None:
            player, team = athletes.get(pid, (db.get(Player, pid), None))
            winner = {"player_id": pid, "name": player.name if player else "?", "team": team}
        result.append({**award, "winner": winner})
    return result


@router.put("/api/tournaments/{tournament_id}/awards/{award_key}")
def set_award(tournament_id: int, award_key: str, data: AwardWinner, db: DBSession = Depends(get_db)):
    get_tournament(db, tournament_id)
    award = AWARD_KEYS.get(award_key)
    if not award:
        raise HTTPException(404, "Prêmio não encontrado")

    existing = db.execute(
        select(TournamentAward).where(
            TournamentAward.tournament_id == tournament_id, TournamentAward.award_key == award_key
        )
    ).scalar_one_or_none()

    if data.player_id is None:
        if existing:
            db.delete(existing)
            db.commit()
        return {"ok": True}

    entry = roster(db, tournament_id).get(data.player_id)
    if not entry:
        raise HTTPException(400, "Atleta não está em nenhuma equipe do torneio")
    if entry[0].gender != award["gender"]:
        raise HTTPException(400, "Esse prêmio é do outro naipe")

    if existing:
        existing.player_id = data.player_id
    else:
        db.add(TournamentAward(tournament_id=tournament_id, award_key=award_key, player_id=data.player_id))
    db.commit()
    return {"ok": True}
