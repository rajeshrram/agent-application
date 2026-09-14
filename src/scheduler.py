"""Three scheduled jobs, wired with APScheduler. Run with:
    python -m src.scheduler
Leave this running alongside src/webhook_app.py (the Slack event receiver)
for real day-to-day operation.
"""
from datetime import date as date_cls

from apscheduler.schedulers.blocking import BlockingScheduler

from src import config
from src.db import store
from src.graphs.daily_collation import run_collation
from src.graphs.ping_and_classify import TIMEOUT_SENTINEL, resume_ping, start_ping


def today_str() -> str:
    return date_cls.today().isoformat()


def daily_kickoff() -> None:
    """Fires each morning: starts one Graph-1 run per team member."""
    date = today_str()
    members = store.list_team_members()
    print(f"[scheduler] kicking off {len(members)} pings for {date}")
    for m in members:
        member_dict = {"id": m.id, "name": m.name, "jira_account_id": m.jira_account_id, "slack_user_id": m.slack_user_id}
        try:
            start_ping(member_dict, date)
        except Exception as exc:  # noqa: BLE001 -- one bad ping shouldn't kill the run
            print(f"[scheduler] failed to ping {m.id}: {exc}")


def cutoff_sweep() -> None:
    """Fires at the cutoff time: force-resumes anyone who never replied so
    they're classified as no_response instead of silently missing."""
    date = today_str()
    pending = store.list_pending_pings_for_date(date)
    print(f"[scheduler] cutoff sweep: {len(pending)} still-open pings for {date}")
    for p in pending:
        try:
            resume_ping(p.thread_id, TIMEOUT_SENTINEL)
        except Exception as exc:  # noqa: BLE001
            print(f"[scheduler] failed to timeout-resume {p.thread_id}: {exc}")


def daily_collation_job() -> None:
    date = today_str()
    print(f"[scheduler] running daily collation for {date}")
    try:
        run_collation(date)
    except Exception as exc:  # noqa: BLE001
        print(f"[scheduler] collation failed for {date}: {exc}")


def main() -> None:
    store.init_db()
    scheduler = BlockingScheduler()
    scheduler.add_job(daily_kickoff, "cron", day_of_week="mon-fri", hour=config.PING_HOUR, minute=config.PING_MINUTE)
    scheduler.add_job(cutoff_sweep, "cron", day_of_week="mon-fri", hour=config.CUTOFF_HOUR, minute=config.CUTOFF_MINUTE)
    scheduler.add_job(
        daily_collation_job,
        "cron",
        day_of_week="mon-fri",
        hour=config.CUTOFF_HOUR,
        minute=config.CUTOFF_MINUTE + 1,
    )
    print("[scheduler] started; Ctrl+C to stop")
    scheduler.start()


if __name__ == "__main__":
    main()
