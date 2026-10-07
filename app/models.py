from datetime import datetime, date
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    score: Mapped[float] = mapped_column(Float, default=70)
    gender: Mapped[str] = mapped_column(String(1), default="X")  # M/F/X
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # "Against a team" night: JSON list of opponent names. Each match then drafts
    # one side of 6 from the arrivals and the opponent alternates down this list.
    opponents: Mapped[str | None] = mapped_column(Text, nullable=True)


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    status: Mapped[str] = mapped_column(String(20), default="expected")
    arrival_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    session: Mapped["Session"] = relationship()
    player: Mapped["Player"] = relationship()


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    number: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    opponent: Mapped[str | None] = mapped_column(String(120), nullable=True)  # set in "against a team" sessions
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MatchPlayer(Base):
    __tablename__ = "match_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team: Mapped[str] = mapped_column(String(1))
    role: Mapped[str] = mapped_column(String(20), default="starter")
    entered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    player: Mapped["Player"] = relationship()


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    type: Mapped[str] = mapped_column(String(40))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    code: Mapped[str] = mapped_column(String(20))
    # Regulation: 7. The organization can raise it for a single team (e.g. an athlete only available one day).
    max_players: Mapped[int] = mapped_column(Integer, default=7, server_default="7")


class TeamPlayer(Base):
    __tablename__ = "team_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    role: Mapped[str] = mapped_column(String(20), default="titular")  # titular/reserva
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)

    player: Mapped["Player"] = relationship()


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    court: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="agendado")  # agendado/em_andamento/encerrado
    # Kept in sync with stage == "final": the column is NOT NULL in existing DBs.
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    stage: Mapped[str] = mapped_column(String(20), default="grupos", server_default="grupos")
    # Decided by W.O.: stored as two closed 15x0 sets so every result/standings
    # path treats it like any other 2x0, this flag only labels it.
    walkover: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class TournamentSetResult(Base):
    __tablename__ = "tournament_set_results"
    __table_args__ = (UniqueConstraint("match_id", "set_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("tournament_matches.id"))
    set_number: Mapped[int]
    points_a: Mapped[int] = mapped_column(Integer, default=0)
    points_b: Mapped[int] = mapped_column(Integer, default=0)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
