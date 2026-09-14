"""Ask Pulse: memory-backed Q&A over status history.

This is the piece the Week 3 framework asks for under "memory" -- "track
week-over-week trends and answer questions like what's been stuck for
more than one sprint" -- without reaching for a separate memory store
like mem0. `status_entries` already accumulates one row per person per
day; that table *is* the memory. This module just reads a window of it
(src/tools/memory_tool.py, read-only) and hands it to the LLM (or the
zero-key heuristic in src/llm.py) to answer in natural language,
grounded only in what's actually in the DB.

Deliberately not a LangGraph: there's no multi-step control flow, no
tool call the model needs to choose, and no write action to gate behind
a human -- just a read and a single LLM call, same shape as
generate_summary in graphs/daily_collation.py.
"""
from src.llm import answer_question
from src.tools import memory_tool

# ~3 work-weeks of history -- enough to answer "more than one sprint"
# without the prompt growing unbounded as the team accumulates history.
DEFAULT_HISTORY_DAYS = 21


def ask(question: str, history_days: int = DEFAULT_HISTORY_DAYS) -> str:
    snapshot = memory_tool.get_team_snapshot(days=history_days)
    streaks = memory_tool.get_streaks(min_days=2)
    return answer_question(question, snapshot, streaks)
