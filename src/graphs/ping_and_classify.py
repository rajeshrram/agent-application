"""Graph 1: one run per team member per day.

fetch_tickets -> send_ping -> [interrupt: wait for Slack reply] -> classify -> persist

The interrupt is the whole point: this run can sit paused for minutes or
hours between send_ping and classify, checkpointed to disk, until either
- a Slack reply comes in (src/webhook_app.py resumes it), or
- the cutoff sweep (src/scheduler.py) force-resumes it with a timeout.

Nothing about fetch/send/classify/persist is itself hard -- the reason this
lives in LangGraph rather than a plain function is that "pause, persist,
resume later from an external event" is exactly what its checkpointer +
interrupt() primitives are for.
"""
import sqlite3
from typing import Dict, List, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src import config
from src.db import store
from src.llm import Classification, classify_reply
from src.tools import jira_tool, slack_tool

TIMEOUT_SENTINEL = "__TIMEOUT__"


class PingState(TypedDict):
    member: Dict
    date: str
    tickets: List[Dict]
    reply_text: Optional[str]
    classification: Optional[Dict]


def fetch_tickets_node(state: PingState) -> Dict:
    tickets = jira_tool.fetch_tickets(state["member"])
    return {"tickets": tickets}


def send_ping_node(state: PingState) -> Dict:
    slack_tool.send_ping(state["member"], state["tickets"])
    return {}


def wait_for_reply_node(state: PingState) -> Dict:
    # Pauses graph execution here. The value passed to `interrupt()` is
    # informational (surfaces in the interrupt payload for anyone inspecting
    # graph state); the value the graph resumes with is whatever the caller
    # passes to Command(resume=...).
    reply_text = interrupt({"waiting_on": "slack_reply", "member_id": state["member"]["id"]})
    return {"reply_text": reply_text}


def classify_node(state: PingState) -> Dict:
    classification: Classification = classify_reply(state["reply_text"], state["tickets"])
    return {"classification": classification.model_dump()}


def persist_node(state: PingState) -> Dict:
    c = state["classification"]
    store.save_status_entry(
        {
            "team_member_id": state["member"]["id"],
            "date": state["date"],
            "jira_snapshot": state["tickets"],
            "raw_reply_text": "" if state["reply_text"] == TIMEOUT_SENTINEL else state["reply_text"],
            "classified_status": c["status"],
            "blocker_description": c.get("blocker_description", ""),
            "ticket_notes": c.get("ticket_notes", {}),
        }
    )
    return {}


def _build_graph():
    builder = StateGraph(PingState)
    builder.add_node("fetch_tickets", fetch_tickets_node)
    builder.add_node("send_ping", send_ping_node)
    builder.add_node("wait_for_reply", wait_for_reply_node)
    builder.add_node("classify", classify_node)
    builder.add_node("persist", persist_node)

    builder.add_edge(START, "fetch_tickets")
    builder.add_edge("fetch_tickets", "send_ping")
    builder.add_edge("send_ping", "wait_for_reply")
    builder.add_edge("wait_for_reply", "classify")
    builder.add_edge("classify", "persist")
    builder.add_edge("persist", END)

    conn = sqlite3.connect(config.CHECKPOINT_DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return builder.compile(checkpointer=checkpointer)


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def start_ping(member: Dict, date: str) -> str:
    """Kicks off Graph 1 for one person; runs up to the wait_for_reply
    interrupt and returns. Records an OpenPing row so the webhook / cutoff
    sweep can find this thread later.

    Idempotent per (member, date): if this person already has a ping today
    -- pending, resumed, or timed out -- this is a no-op. Without this
    check, calling it twice in one day (a re-run kickoff, a double click)
    would send a second real Slack DM before failing on the thread_id
    UNIQUE constraint on the second write.
    """
    thread_id = f"{member['id']}:{date}"
    if store.get_ping_for_date(member["id"], date) is not None:
        return thread_id

    graph = get_graph()
    graph.invoke(
        {"member": member, "date": date, "tickets": [], "reply_text": None, "classification": None},
        config={"configurable": {"thread_id": thread_id}},
    )
    store.open_ping(member["id"], date, thread_id)
    return thread_id


def resume_ping(thread_id: str, reply_text: str) -> Optional[Dict]:
    """Resumes a paused Graph 1 run with the given reply text (or
    TIMEOUT_SENTINEL from the cutoff sweep). Runs classify + persist.

    Returns None (a no-op) if this thread isn't currently pending -- e.g. a
    duplicate Slack webhook delivery for a reply already processed, or a
    double-clicked cutoff sweep racing another caller for the same thread.
    store.claim_ping() makes that check-and-flip atomic, so at most one
    caller ever proceeds past it for a given thread_id.
    """
    if not store.claim_ping(thread_id):
        return None

    graph = get_graph()
    result = graph.invoke(
        Command(resume=reply_text), config={"configurable": {"thread_id": thread_id}}
    )
    store.mark_ping_status(thread_id, "timeout" if reply_text == TIMEOUT_SENTINEL else "resumed")
    return result
