"""Unit tests for the zero-key heuristic classifier/summarizer fallback in
src/llm.py -- these run with no ANTHROPIC_API_KEY and no network access.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm import _classify_heuristic, _summarize_heuristic  # noqa: E402


def test_blocked_keyword_detected():
    result = _classify_heuristic("I'm blocked on the DBA team approving the migration.")
    assert result.status == "blocked"
    assert result.blocker_description


def test_at_risk_keyword_detected():
    result = _classify_heuristic("Might slip a day, a bit behind on testing.")
    assert result.status == "at_risk"


def test_plain_reply_is_on_track():
    result = _classify_heuristic("All good, shipping today.")
    assert result.status == "on_track"
    assert result.blocker_description == ""


def test_timeout_short_circuits_before_heuristic():
    from src.llm import classify_reply

    result = classify_reply("__TIMEOUT__", tickets=[])
    assert result.status == "no_response"


def test_summary_counts_and_sections():
    entries = [
        {"team_member_id": "alice", "classified_status": "on_track"},
        {"team_member_id": "bilal", "classified_status": "blocked", "blocker_description": "waiting on DBA"},
        {"team_member_id": "cara", "classified_status": "no_response"},
    ]
    text = _summarize_heuristic("2026-09-12", entries)
    assert "1 on track" in text
    assert "1 blocked" in text
    assert "1 no response" in text
    assert "waiting on DBA" in text
