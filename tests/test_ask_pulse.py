"""Unit tests for the zero-key heuristic behind Ask Pulse
(src/llm.py's _answer_heuristic) -- same convention as test_classify.py:
exercise the heuristic directly so these run with no API key and no
network access.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm import _answer_heuristic  # noqa: E402

SNAPSHOT = [
    {"date": "2026-09-12", "member_id": "priya", "name": "Priya", "status": "blocked", "blocker": "waiting on DBA"},
    {"date": "2026-09-11", "member_id": "priya", "name": "Priya", "status": "blocked", "blocker": "waiting on DBA"},
    {"date": "2026-09-12", "member_id": "sam", "name": "Sam", "status": "on_track", "blocker": ""},
]
STREAKS = [{"member_id": "priya", "name": "Priya", "streak_days": 2}]


def test_who_is_stuck_lists_streaks():
    answer = _answer_heuristic("who's stuck?", SNAPSHOT, STREAKS)
    assert "Priya" in answer
    assert "2" in answer


def test_who_is_stuck_with_no_streaks():
    answer = _answer_heuristic("who's blocked right now?", SNAPSHOT, [])
    assert "Nobody" in answer


def test_person_lookup_by_name():
    answer = _answer_heuristic("how has Priya looked this week?", SNAPSHOT, STREAKS)
    assert "blocked" in answer


def test_unrecognized_question_gives_a_hint_not_an_error():
    answer = _answer_heuristic("what's the meaning of life?", SNAPSHOT, STREAKS)
    assert "NEBIUS_API_KEY" in answer
