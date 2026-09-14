"""Read-only query surface over Pulse's own history in `status_entries` --
this table already *is* the persistent memory the Week 3 framework asks
for ("add memory so the agent can answer what's been stuck for more than
one sprint"); this module is just the query shape that makes it
answerable instead of only dashboard-displayable.

Same autonomy class as jira_tool.fetch_tickets: everything here reads,
nothing writes. Backs src/ask_pulse.py and the dashboard's streaks card.
"""
from typing import Dict, List

from src.db import store


def get_streaks(min_days: int = 2) -> List[Dict]:
    """Everyone currently on a blocked/at_risk streak of at least
    `min_days`, longest streak first."""
    out = []
    for m in store.list_team_members():
        streak = store.get_streak(m.id)
        if streak >= min_days:
            out.append({"member_id": m.id, "name": m.name, "streak_days": streak})
    out.sort(key=lambda r: r["streak_days"], reverse=True)
    return out


def get_member_history(member_id: str, days: int = 14) -> List[Dict]:
    """One person's classified status per day, most-recent-first."""
    return [
        {"date": e.date, "status": e.classified_status, "blocker": e.blocker_description}
        for e in store.get_status_entries_for_member(member_id, limit=days)
    ]


def get_team_snapshot(days: int = 14) -> List[Dict]:
    """Every entry across every person for the last `days` days -- the raw
    context handed to the LLM (or the heuristic fallback) in
    src/llm.py's answer_question()."""
    entries = store.get_recent_status_entries(days=days)
    members = {m.id: m.name for m in store.list_team_members()}
    return [
        {
            "date": e.date,
            "member_id": e.team_member_id,
            "name": members.get(e.team_member_id, e.team_member_id),
            "status": e.classified_status,
            "blocker": e.blocker_description,
        }
        for e in entries
    ]
