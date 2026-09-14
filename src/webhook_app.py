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
        print(f"[webhook_app] no open ping for {member.id} on {date} -- late/duplicate reply?")
        return

    try:
        resume_ping(open_ping.thread_id, reply_text)
    except Exception as exc:  # noqa: BLE001 -- one bad resume shouldn't 500 the endpoint
        print(f"[webhook_app] failed to resume {open_ping.thread_id}: {exc}")
