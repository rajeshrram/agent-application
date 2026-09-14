"""End-to-end demo with zero external services and zero API keys.

Runs Graph 1 for three mock team members, simulates their Slack replies
directly (standing in for what the webhook would do), then runs Graph 2 and
prints the resulting summary email to the console.

    python scripts/seed_team.py
    python scripts/run_local_demo.py
"""
import sys
from datetime import date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import store  # noqa: E402
from src.graphs.daily_collation import run_collation  # noqa: E402
from src.graphs.ping_and_classify import resume_ping, start_ping  # noqa: E402

# Canned replies -- one on-track, one blocked, one no-response (never resumed).
CANNED_REPLIES = {
    "rajesh": "All good, no blockers today.",
    "meenu": "Blocked -- waiting on review before I can move forward.",
    # navilan intentionally left out: simulates a no_response case via the cutoff sweep.
}


def main() -> None:
    store.init_db()
    today = date_cls.today().isoformat()
    members = store.list_team_members()
    if not members:
        print("No team members seeded. Run scripts/seed_team.py first.")
        return

    print(f"=== Kicking off pings for {today} ===")
    threads = {}
    for m in members:
        member_dict = {
            "id": m.id,
            "name": m.name,
            "jira_account_id": m.jira_account_id,
            "slack_user_id": m.slack_user_id,
        }
        try:
            threads[m.id] = start_ping(member_dict, today)
        except Exception as exc:  # noqa: BLE001 -- one bad ping shouldn't hide the rest
            print(f"-> FAILED to ping {m.id}: {exc}")

    print("\n=== Simulating replies (standing in for the Slack webhook) ===")
    for member_id, reply in CANNED_REPLIES.items():
        if member_id in threads:
            print(f"-> {member_id} replies: {reply!r}")
            resume_ping(threads[member_id], reply)

    print("\n=== Cutoff sweep: force-resuming anyone who never replied ===")
    from src.graphs.ping_and_classify import TIMEOUT_SENTINEL

    for p in store.list_pending_pings_for_date(today):
        print(f"-> {p.team_member_id} timed out with no reply")
        resume_ping(p.thread_id, TIMEOUT_SENTINEL)

    print(f"\n=== Running daily collation for {today} ===")
    try:
        run_collation(today)
    except Exception as exc:  # noqa: BLE001 -- summary was already persisted as a draft
        print(f"-> Collation/send failed: {exc}")
        print("   The draft summary was still saved to daily_summaries -- nothing is lost.")


if __name__ == "__main__":
    main()
