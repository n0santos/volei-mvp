from datetime import date, datetime

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


class TournamentMatchCreate(BaseModel):
    team_a_id: int
    team_b_id: int
    scheduled_at: datetime
    court: str | None = None
    is_final: bool = False


class TournamentMatchUpdate(BaseModel):
    team_a_id: int | None = None
    team_b_id: int | None = None
    scheduled_at: datetime | None = None
    court: str | None = None
    status: str | None = None
    is_final: bool | None = None


class SetPointRequest(BaseModel):
    team: str
    delta: int


class GenerateFinalRequest(BaseModel):
    scheduled_at: datetime
    court: str | None = None
