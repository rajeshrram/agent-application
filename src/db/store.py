"""Thin data-access layer over the app DB (SQLite by default, swap the URL
for Postgres later -- nothing else in the codebase needs to change)."""
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterator, List, Optional

from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from src import config
from src.db.models import Base, DailySummary, OpenPing, StatusEntry, TeamMember

_engine = create_engine(f"sqlite:///{config.APP_DB_PATH}", echo=False)
_SessionLocal = sessionmaker(bind=_engine)


def init_db() -> None:
    Base.metadata.create_all(_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- TeamMember ---

def upsert_team_member(member: Dict) -> None:
    with session_scope() as s:
        existing = s.get(TeamMember, member["id"])
        if existing:
            for k, v in member.items():
                setattr(existing, k, v)
        else:
            s.add(TeamMember(**member))


def list_team_members() -> List[TeamMember]:
    with session_scope() as s:
        rows = s.execute(select(TeamMember)).scalars().all()
        s.expunge_all()
        return list(rows)


def get_team_member(member_id: str) -> Optional[TeamMember]:
    with session_scope() as s:
        row = s.get(TeamMember, member_id)
        if row:
            s.expunge(row)
        return row


def get_team_member_by_slack_user(slack_user_id: str) -> Optional[TeamMember]:
    with session_scope() as s:
        row = s.execute(
            select(TeamMember).where(TeamMember.slack_user_id == slack_user_id)
        ).scalar_one_or_none()
        if row:
            s.expunge(row)
        return row


# --- StatusEntry ---

def save_status_entry(entry: Dict) -> None:
    """Upsert by (team_member_id, date): replaces any existing entry for
    that day instead of adding a second row. Belt-and-suspenders alongside
    claim_ping() -- if a persist ever runs twice for the same person/date
    despite that guard, this still can't produce duplicate rows."""
    with session_scope() as s:
        s.execute(
            delete(StatusEntry).where(
                StatusEntry.team_member_id == entry["team_member_id"],
                StatusEntry.date == entry["date"],
            )
        )
        s.add(StatusEntry(**entry))


def get_status_entries_for_date(date: str) -> List[StatusEntry]:
    with session_scope() as s:
        rows = s.execute(
            select(StatusEntry).where(StatusEntry.date == date)
        ).scalars().all()
        s.expunge_all()
        return list(rows)


def get_status_entries_for_member(member_id: str, limit: int = 30) -> List[StatusEntry]:
    """Most-recent-first, for computing streaks like "blocked N days running"."""
    with session_scope() as s:
        rows = s.execute(
            select(StatusEntry)
            .where(StatusEntry.team_member_id == member_id)
            .order_by(StatusEntry.date.desc())
            .limit(limit)
        ).scalars().all()
        s.expunge_all()
        return list(rows)


# --- DailySummary ---

def get_daily_summary(date: str) -> Optional[DailySummary]:
    with session_scope() as s:
        row = s.execute(
            select(DailySummary).where(DailySummary.date == date)
        ).scalar_one_or_none()
        if row:
            s.expunge(row)
        return row


def list_daily_summaries(limit: int = 14) -> List[DailySummary]:
    with session_scope() as s:
        rows = s.execute(
            select(DailySummary).order_by(DailySummary.date.desc()).limit(limit)
        ).scalars().all()
        s.expunge_all()
        return list(rows)


def save_daily_summary(date: str, generated_text: str, recipient: str, sent: bool) -> None:
    with session_scope() as s:
        existing = s.execute(
            select(DailySummary).where(DailySummary.date == date)
        ).scalar_one_or_none()
        if existing:
            existing.generated_text = generated_text
            existing.recipient = recipient
            existing.sent_at = datetime.utcnow() if sent else existing.sent_at
        else:
            s.add(
                DailySummary(
                    date=date,
                    generated_text=generated_text,
                    recipient=recipient,
                    sent_at=datetime.utcnow() if sent else None,
                )
            )


# --- OpenPing ---

def open_ping(team_member_id: str, date: str, thread_id: str) -> None:
    with session_scope() as s:
        s.add(OpenPing(team_member_id=team_member_id, date=date, thread_id=thread_id))


def get_ping_for_date(team_member_id: str, date: str) -> Optional[OpenPing]:
    """Any status (pending, resumed, or timeout) -- used to check whether
    this person has been pinged at all today, so a re-run of the kickoff
    doesn't send a duplicate real ping. thread_id is unique per
    (team_member_id, date), so at most one row can exist."""
    with session_scope() as s:
        row = s.execute(
            select(OpenPing).where(
                OpenPing.team_member_id == team_member_id, OpenPing.date == date
            )
        ).scalar_one_or_none()
        if row:
            s.expunge(row)
        return row


def find_open_ping(team_member_id: str, date: str) -> Optional[OpenPing]:
    with session_scope() as s:
        row = s.execute(
            select(OpenPing)
            .where(
                OpenPing.team_member_id == team_member_id,
                OpenPing.date == date,
                OpenPing.status == "pending",
            )
            .order_by(OpenPing.created_at.desc())
        ).scalars().first()
        if row:
            s.expunge(row)
        return row


def list_pending_pings_for_date(date: str) -> List[OpenPing]:
    with session_scope() as s:
        rows = s.execute(
            select(OpenPing).where(OpenPing.date == date, OpenPing.status == "pending")
        ).scalars().all()
        s.expunge_all()
        return list(rows)


def claim_ping(thread_id: str) -> bool:
    """Atomically flips one OpenPing from pending -> processing via a single
    UPDATE ... WHERE status='pending'. Returns True if this call won the
    race, False if it was already claimed/resumed/timed-out by someone
    else -- the caller should treat False as a no-op, not an error.

    This is what makes resume_ping() safe against duplicate Slack webhook
    deliveries (Slack retries if a handler is slow to respond) and against
    a double-clicked "Run cutoff sweep" -- two callers racing to resume the
    same thread now can't both win."""
    with session_scope() as s:
        result = s.execute(
            update(OpenPing)
            .where(OpenPing.thread_id == thread_id, OpenPing.status == "pending")
            .values(status="processing")
        )
        return result.rowcount == 1


def mark_ping_status(thread_id: str, status: str) -> None:
    with session_scope() as s:
        row = s.execute(
            select(OpenPing).where(OpenPing.thread_id == thread_id)
        ).scalar_one_or_none()
        if row:
            row.status = status


# --- Demo / testing utilities ---

def reset_date(date: str) -> Dict[str, int]:
    """Deletes OpenPing, StatusEntry, and DailySummary rows for one date only
    -- every other date's history is untouched. Used by the dashboard's
    "Reset today's data" button so a demo run can be retried without
    re-seeding the whole DB. Does NOT touch the LangGraph checkpointer DB;
    re-invoking start_ping for the same (member, date) after this still
    works because that just starts a fresh checkpoint on the same thread."""
    with session_scope() as s:
        r1 = s.execute(delete(OpenPing).where(OpenPing.date == date))
        r2 = s.execute(delete(StatusEntry).where(StatusEntry.date == date))
        r3 = s.execute(delete(DailySummary).where(DailySummary.date == date))
        return {
            "open_pings": r1.rowcount,
            "status_entries": r2.rowcount,
            "daily_summaries": r3.rowcount,
        }
