"""SQLAlchemy models for the app's own state (separate from the LangGraph
checkpointer DB, which holds the paused-graph state -- see db/store.py).

TeamMember    -- who we ping, and how to reach them.
StatusEntry   -- one classified reply per person per day.
DailySummary  -- the generated manager report for a given day.
OpenPing      -- bookkeeping row that lets the Slack webhook / cutoff sweep
                 find the paused LangGraph thread for an inbound reply.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    jira_account_id: Mapped[str] = mapped_column(String)
    slack_user_id: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, default="")


class StatusEntry(Base):
    __tablename__ = "status_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_member_id: Mapped[str] = mapped_column(ForeignKey("team_members.id"))
    date: Mapped[str] = mapped_column(String)  # ISO date, e.g. 2026-09-12
    jira_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    raw_reply_text: Mapped[str] = mapped_column(String, default="")
    classified_status: Mapped[str] = mapped_column(String)  # on_track|blocked|at_risk|no_response
    blocker_description: Mapped[str] = mapped_column(String, default="")
    ticket_notes: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String, unique=True)
    generated_text: Mapped[str] = mapped_column(String)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    recipient: Mapped[str] = mapped_column(String, default="")


class OpenPing(Base):
    """One row per (team_member, date) ping that is currently paused waiting
    on a Slack reply, or has just been resumed. Lets the webhook handler and
    the cutoff sweep find the right LangGraph thread_id to resume."""

    __tablename__ = "open_pings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_member_id: Mapped[str] = mapped_column(ForeignKey("team_members.id"))
    date: Mapped[str] = mapped_column(String)
    thread_id: Mapped[str] = mapped_column(String, unique=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|resumed|timeout
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
