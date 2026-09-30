from datetime import date

from pydantic import BaseModel


class PlayerCreate(BaseModel):
    name: str
    score: float = 70
    gender: str = "X"


class SessionCreate(BaseModel):
    name: str = "Vôlei"
    player_ids: list[int] | None = None


class AttendanceUpdate(BaseModel):
    status: str


class SubstituteRequest(BaseModel):
    player_id: int


class SwapRequest(BaseModel):
    out_player_id: int
    in_player_id: int


class TournamentCreate(BaseModel):
    name: str
    start_date: date
    end_date: date


class TeamCreate(BaseModel):
    code: str


class TeamPlayerAdd(BaseModel):
    player_id: int
    role: str = "titular"


class TeamPlayerUpdate(BaseModel):
    role: str | None = None
    is_captain: bool | None = None
