"""The two LLM calls in the system: classify one reply, and summarize a
day's worth of classified replies.

Both fall back to a plain heuristic when no NEBIUS_API_KEY is set, so
scripts/run_local_demo.py runs with zero setup. Once you export a real key
they automatically switch to a Nebius AI Studio model via the OpenAI-
compatible API (Nebius Token Factory).

Classification uses plain JSON-in-the-prompt + manual parsing rather than
LangChain's with_structured_output(): that feature depends on the specific
hosted model supporting OpenAI-style tool calling, which isn't guaranteed
across Nebius's catalog. Asking for JSON directly and parsing it works with
any instruct model, and falls back to the heuristic if parsing ever fails.
"""
import json
import re
from typing import Dict, List

from pydantic import BaseModel, Field, ValidationError

from src import config

_TIMEOUT_TEXT = "__TIMEOUT__"


class Classification(BaseModel):
    status: str = Field(description="one of: on_track, blocked, at_risk, no_response")
    blocker_description: str = Field(default="", description="empty string if not blocked")
    ticket_notes: Dict[str, str] = Field(
        default_factory=dict, description="ticket_id -> note, only for tickets explicitly mentioned"
    )


def _get_llm():
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config.NEBIUS_MODEL,
        api_key=config.NEBIUS_API_KEY,
        base_url=config.NEBIUS_BASE_URL,
        temperature=0,
    )


def _extract_json_block(text: str) -> Dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in model output")
    return json.loads(match.group(0))


def classify_reply(reply_text: str, tickets: List[Dict]) -> Classification:
    if reply_text == _TIMEOUT_TEXT:
        return Classification(status="no_response")

    if not config.NEBIUS_API_KEY:
        return _classify_heuristic(reply_text)

    ticket_list = "\n".join(f"- {t['ticket_id']}: {t['title']}" for t in tickets) or "(none)"
    prompt = (
        "You are classifying a team member's daily standup reply.\n\n"
        f"Their open tickets:\n{ticket_list}\n\n"
        f"Their reply:\n\"\"\"{reply_text}\"\"\"\n\n"
        "Respond with ONLY a JSON object, no other text, matching this shape:\n"
        '{"status": "on_track|blocked|at_risk", '
        '"blocker_description": "one sentence, empty string if not blocked", '
        '"ticket_notes": {"TICKET-ID": "note"}}\n'
        "Only add ticket_notes for tickets the reply explicitly mentions."
    )
    try:
        raw = _get_llm().invoke(prompt).content
    except Exception as exc:  # noqa: BLE001 -- auth/network/model-not-found, degrade gracefully
        print(f"[llm] classification API call failed ({exc}), falling back to heuristic")
        return _classify_heuristic(reply_text)

    try:
        return Classification.model_validate(_extract_json_block(raw))
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"[llm] classification parse failed ({exc}), falling back to heuristic")
        return _classify_heuristic(reply_text)


def _classify_heuristic(reply_text: str) -> Classification:
    """Zero-dependency fallback so the pipeline is testable with no API key,
    and a safety net if the model ever returns unparseable output."""
    text = reply_text.lower()
    if any(w in text for w in ("blocked", "stuck", "waiting on", "can't proceed")):
        return Classification(status="blocked", blocker_description=reply_text.strip())
    if any(w in text for w in ("risk", "might slip", "behind", "concerned")):
        return Classification(status="at_risk", blocker_description=reply_text.strip())
    return Classification(status="on_track")


def generate_summary(date: str, entries: List[Dict]) -> str:
    if not config.NEBIUS_API_KEY:
        return _summarize_heuristic(date, entries)

    rows = "\n".join(
        f"- {e.get('name', e['team_member_id'])}: {e['classified_status']}"
        + (f" -- {e['blocker_description']}" if e.get("blocker_description") else "")
        for e in entries
    )
    prompt = (
        f"Write a concise daily team status email for {date} for an engineering "
        "manager, based on these per-person statuses:\n\n"
        f"{rows}\n\n"
        "Structure: one-line overall count (X on track, Y blocked, Z at risk, "
        "W no response), then a 'Blockers' section listing each blocked/at-risk "
        "person with their blocker, then a short 'Notable progress' section. "
        "Plain text, no markdown."
    )
    try:
        return _get_llm().invoke(prompt).content
    except Exception as exc:  # noqa: BLE001 -- network/API hiccup, degrade gracefully
        print(f"[llm] summary generation failed ({exc}), falling back to heuristic")
        return _summarize_heuristic(date, entries)


def _summarize_heuristic(date: str, entries: List[Dict]) -> str:
    counts = {"on_track": 0, "blocked": 0, "at_risk": 0, "no_response": 0}
    for e in entries:
        counts[e["classified_status"]] = counts.get(e["classified_status"], 0) + 1

    lines = [
        f"Pulse — {date}",
        f"{counts['on_track']} on track, {counts['blocked']} blocked, "
        f"{counts['at_risk']} at risk, {counts['no_response']} no response",
        "",
        "Blockers:",
    ]
    blockers = [e for e in entries if e["classified_status"] in ("blocked", "at_risk")]
    if not blockers:
        lines.append("  (none)")
    for e in blockers:
        lines.append(f"  - {e.get('name', e['team_member_id'])}: {e.get('blocker_description', '')}")

    lines += ["", "Notable progress:"]
    ok = [e for e in entries if e["classified_status"] == "on_track"]
    if not ok:
        lines.append("  (none reported)")
    for e in ok:
        lines.append(f"  - {e.get('name', e['team_member_id'])}: on track")

    return "\n".join(lines)
