"""Send the daily ping DM, and verify inbound Slack webhook requests.

send_ping is a WRITE (it messages a real person) -- kept autonomous here
because it's a low-stakes recurring notification, not a destructive action.
If that's not the call you want, gate it behind the same approval interrupt
used in graphs/daily_collation.py before send_email.
"""
import hashlib
import hmac
import time
from typing import Dict, List

from src import config


def _format_ping_text(tickets: List[Dict]) -> str:
    if not tickets:
        return (
            "Hey! No open tickets assigned to you today. Anything blocked "
            "that isn't tracked in JIRA?"
        )
    lines = [f"- {t['ticket_id']}: {t['title']} ({t['status']})" for t in tickets]
    return (
        "Morning! Quick status check on your open tickets:\n"
        + "\n".join(lines)
        + "\n\nHow's progress -- anything blocked?"
    )


def send_ping(member: Dict, tickets: List[Dict]) -> Dict:
    """Returns {"channel": ..., "ts": ...} identifying the sent message."""
    text = _format_ping_text(tickets)
    if config.SLACK_MOCK:
        print(f"[slack_tool:MOCK] -> {member['name']} ({member['slack_user_id']}):\n{text}\n")
        return {"channel": member["slack_user_id"], "ts": str(time.time())}
    return _send_real(member["slack_user_id"], text)


def _send_real(slack_user_id: str, text: str) -> Dict:
    """TODO (Day 2): needs SLACK_BOT_TOKEN with chat:write + im:write scopes.
    Passing a user ID as `channel` opens/uses the DM automatically."""
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=config.SLACK_BOT_TOKEN)
    try:
        resp = client.chat_postMessage(channel=slack_user_id, text=text)
        return {"channel": resp["channel"], "ts": resp["ts"]}
    except SlackApiError as exc:
        print(f"[slack_tool] send failed for {slack_user_id}: {exc.response['error']}")
        raise


def verify_signature(timestamp: str, body: str, signature: str) -> bool:
    """Slack request signing verification for the webhook endpoint.
    See: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    try:
        stale = abs(time.time() - int(timestamp)) > 60 * 5
    except (TypeError, ValueError):
        return False  # missing/malformed timestamp -- not a real Slack request
    if stale:
        return False  # possible replay
    basestring = f"v0:{timestamp}:{body}"
    computed = "v0=" + hmac.new(
        config.SLACK_SIGNING_SECRET.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)
