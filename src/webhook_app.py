"""Slack Events API receiver. Run with:
    uvicorn src.webhook_app:app --port 8000
and point a Slack Event Subscription (message.im) at https://<your-tunnel>/slack/events.

Matches an inbound DM to the open ping for that person *by Slack user id*,
not by channel -- simpler, and avoids needing to resolve/store DM channel
ids up front.
"""
from datetime import date as date_cls

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from src import config
from src.db import store
from src.graphs.ping_and_classify import resume_ping
from src.tools.slack_tool import verify_signature

app = FastAPI()


@app.post("/slack/events")
async def slack_events(
    request: Request,
    x_slack_signature: str = Header(default=""),
    x_slack_request_timestamp: str = Header(default=""),
):
    raw_body = (await request.body()).decode("utf-8")

    if not verify_signature(x_slack_request_timestamp, raw_body, x_slack_signature):
        # This used to fail silently -- a wrong/missing SLACK_SIGNING_SECRET or a
        # skewed server clock rejects every real Slack event with no clue why.
        print(
            f"[webhook_app] signature check FAILED -- rejecting event "
            f"(timestamp={x_slack_request_timestamp!r}, "
            f"secret configured={bool(config.SLACK_SIGNING_SECRET)}). "
            "If secret configured=False, set SLACK_SIGNING_SECRET in .env. "
            "If True, check it matches the Slack app's Signing Secret exactly, "
            "and that this machine's clock is within 5 minutes of real time."
        )
        return JSONResponse(status_code=401, content={"error": "invalid signature"})

    payload = await request.json()

    # One-time URL verification handshake when you first register the endpoint.
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    event = payload.get("event", {})
    if event.get("type") == "message" and not event.get("bot_id"):
        slack_user_id = event.get("user")
        reply_text = event.get("text", "")
        _handle_reply(slack_user_id, reply_text)

    return {"ok": True}


def _handle_reply(slack_user_id: str, reply_text: str) -> None:
    member = store.get_team_member_by_slack_user(slack_user_id)
    if member is None:
        print(f"[webhook_app] reply from unknown slack user {slack_user_id}, ignoring")
        return

    date = date_cls.today().isoformat()
    open_ping = store.find_open_ping(member.id, date)
    if open_ping is None:
        # Most common cause: the cutoff sweep (or another delivery of this
        # same Slack event -- Slack retries) already claimed this thread
        # first. store.claim_ping()'s atomic flip means only one caller can
        # ever win that race, so this reply is intentionally dropped rather
        # than silently double-processed -- but it IS dropped, so log it.
        print(
            f"[webhook_app] no open (pending) ping for {member.id} on {date} -- "
            "already resumed/timed out (race with cutoff sweep or a duplicate "
            "Slack delivery), or this is a late/unexpected reply. Ignoring."
        )
        return

    try:
        result = resume_ping(open_ping.thread_id, reply_text)
    except Exception as exc:  # noqa: BLE001 -- one bad resume shouldn't 500 the endpoint
        print(f"[webhook_app] failed to resume {open_ping.thread_id}: {exc}")
        return

    if result is None:
        print(
            f"[webhook_app] lost the claim race for {open_ping.thread_id} -- "
            "someone else (cutoff sweep / a duplicate delivery) resumed it first. "
            f"{member.name}'s reply was NOT recorded."
        )
    else:
        print(f"[webhook_app] resumed {open_ping.thread_id} with {member.name}'s reply: {reply_text!r}")
