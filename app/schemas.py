from datetime import date, datetime

from pydantic import BaseModel


class PlayerCreate(BaseModel):
    name: str
    score: float = 70
    gender: str = "X"


class SessionCreate(BaseModel):
    name: str = "Vôlei"
    player_ids: list[int] | None = None
    opponents: list[str] | None = None  # "against a team" night: 6 drafted per match vs these teams, in turn


class GenerateRequest(BaseModel):
    # Against a team: which one (default: the other one than last match) and how
    # many are missing from its side - that many extra players are drafted to fill in.
    opponent: str | None = None
    missing: int = 0


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


class TeamUpdate(BaseModel):
    code: str | None = None
    max_players: int | None = None


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
    stage: str = "grupos"


class TournamentMatchUpdate(BaseModel):
    team_a_id: int | None = None
    team_b_id: int | None = None
    scheduled_at: datetime | None = None
    court: str | None = None
    status: str | None = None
    stage: str | None = None


class SetPointRequest(BaseModel):
    team: str
    delta: int


class GenerateSemifinalsRequest(BaseModel):
    semifinal_1_at: datetime
    semifinal_2_at: datetime
    court: str | None = None


class GenerateFinalRequest(BaseModel):
    final_at: datetime
    court: str | None = None


class DrawRequest(BaseModel):
    slots: dict[str, int]  # slot letter "A".."F" -> team id, as drawn
    times: list[datetime]  # one per qualifying game, in fixture order


class WalkoverRequest(BaseModel):
    present: str  # the team that showed up and wins: "a" or "b"
