"""Graph 2: one run per day, fired by the scheduler at CUTOFF_HOUR:MINUTE
(after Graph 1's cutoff sweep has force-resumed any stragglers).

load_entries -> generate_summary -> [optional interrupt: manager approval] -> send_email

The approval step is OFF by default (config.REQUIRE_SUMMARY_APPROVAL=false):
the summary email auto-sends. That's a real decision from the framework's
"write actions deserve a human" rule -- flip the flag on if you'd rather the
manager approve/edit the draft before it goes out; see scripts/approve_summary.py
to resume a paused run.
"""
import sqlite3
from typing import Dict, List, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src import config
from src.db import store
from src.email_template import render_status_email_html
from src.llm import generate_summary
from src.tools import gmail_tool


class CollationState(TypedDict):
    date: str
    entries: List[Dict]
    summary_text: Optional[str]
    sent: bool


def load_entries_node(state: CollationState) -> Dict:
    entries = store.get_status_entries_for_date(state["date"])
    entries_as_dicts = []
    for e in entries:
        member = store.get_team_member(e.team_member_id)
        entries_as_dicts.append(
            {
                "team_member_id": e.team_member_id,
                "name": member.name if member else e.team_member_id,
                "classified_status": e.classified_status,
                "blocker_description": e.blocker_description,
            }
        )
    return {"entries": entries_as_dicts}


def generate_summary_node(state: CollationState) -> Dict:
    text = generate_summary(state["date"], state["entries"])
    # Persist the draft immediately so nothing is lost if this run then
    # sits paused at the approval interrupt for a while.
    store.save_daily_summary(state["date"], text, config.GMAIL_MANAGER_ADDRESS, sent=False)
    return {"summary_text": text}


def approve_node(state: CollationState) -> Dict:
    decision = interrupt({"date": state["date"], "summary_text": state["summary_text"]})
    # Resume with "approve" to send as-is, or with replacement text to edit
    # the draft before it goes out.
    if decision and decision.strip().lower() != "approve":
        return {"summary_text": decision}
    return {}


def send_email_node(state: CollationState) -> Dict:
    subject = f"Pulse — {state['date']}"
    html_body = render_status_email_html(state["date"], state["entries"], state["summary_text"])
    gmail_tool.send_email(config.GMAIL_MANAGER_ADDRESS, subject, state["summary_text"], html_body=html_body)
    store.save_daily_summary(
        state["date"], state["summary_text"], config.GMAIL_MANAGER_ADDRESS, sent=True
    )
    return {"sent": True}


def _build_graph():
    builder = StateGraph(CollationState)
    builder.add_node("load_entries", load_entries_node)
    builder.add_node("generate_summary", generate_summary_node)
    builder.add_node("send_email", send_email_node)

    builder.add_edge(START, "load_entries")
    builder.add_edge("load_entries", "generate_summary")

    if config.REQUIRE_SUMMARY_APPROVAL:
        builder.add_node("approve", approve_node)
        builder.add_edge("generate_summary", "approve")
        builder.add_edge("approve", "send_email")
    else:
        builder.add_edge("generate_summary", "send_email")

    builder.add_edge("send_email", END)

    conn = sqlite3.connect(config.CHECKPOINT_DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return builder.compile(checkpointer=checkpointer)


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def run_collation(date: str) -> Dict:
    thread_id = f"collation:{date}"
    graph = get_graph()
    return graph.invoke(
        {"date": date, "entries": [], "summary_text": None, "sent": False},
        config={"configurable": {"thread_id": thread_id}},
    )


def resume_collation(date: str, decision: str) -> Dict:
    """decision: "approve" to send the draft as-is, or replacement text."""
    thread_id = f"collation:{date}"
    graph = get_graph()
    return graph.invoke(Command(resume=decision), config={"configurable": {"thread_id": thread_id}})
