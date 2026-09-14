"""Manager dashboard for Pulse.

Talks directly to src/db and src/graphs -- no new backend, no HTTP layer.
Everything here is a thin read (and a few action buttons) over the same
LangGraph runs and SQLite store the rest of the app uses.

Visual identity matches the architecture diagram and the status email:
IBM Plex Sans/Mono, a slate-paper neutral, and the same amber/blue read
vs. write accent used throughout the project.

Run:
    streamlit run streamlit_app.py
"""
import html
from datetime import date as date_cls

import streamlit as st

from src import ask_pulse, config
from src.db import store
from src.graphs.daily_collation import resume_collation, run_collation
from src.graphs.ping_and_classify import TIMEOUT_SENTINEL, resume_ping, start_ping
from src.status_style import STATUS_STYLE, style_for
from src.tools import memory_tool

st.set_page_config(page_title="Pulse", page_icon="📋", layout="wide")
store.init_db()


def today() -> str:
    return date_cls.today().isoformat()


def member_dict(m) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "jira_account_id": m.jira_account_id,
        "slack_user_id": m.slack_user_id,
    }


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


# ------------------------------------------------------------------- CSS ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    :root {
        --bg: #EDEFF2; --surface: #FFFFFF; --surface-2: #F7F8FA;
        --ink: #161A22; --ink-muted: #5B6472; --border: #E3E6EC;
        --accent-write: #B8791E; --accent-read: #3B6E8F;
    }
    html, body, [class*="css"] { font-family: "IBM Plex Sans", -apple-system, sans-serif; }
    .stApp { background: var(--bg); }
    section[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
    div.block-container { padding-top: 2rem; max-width: 1100px; }

    .ent-eyebrow {
        font-family: "IBM Plex Mono", monospace; font-size: 11px; font-weight: 500;
        letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-muted); margin-bottom: 4px;
    }
    .ent-title { font-size: 30px; font-weight: 700; color: var(--ink); margin: 0 0 14px; }

    .ent-chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 26px; }
    .ent-chip {
        display: inline-flex; align-items: center; gap: 7px; padding: 6px 12px;
        border: 1px solid var(--border); border-radius: 999px; background: var(--surface);
        font-family: "IBM Plex Mono", monospace; font-size: 12px; color: var(--ink);
    }
    .ent-dot { width: 7px; height: 7px; border-radius: 50%; }

    .ent-card {
        background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
        padding: 20px 22px; margin-bottom: 20px;
    }
    .ent-card h3 {
        font-size: 15px; font-weight: 600; color: var(--ink); margin: 0 0 4px;
        display: flex; align-items: center; gap: 8px;
    }
    .ent-card .ent-sub { font-size: 12.5px; color: var(--ink-muted); margin: 0 0 14px; }

    .ent-kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 22px; }
    .ent-kpi {
        background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
        padding: 16px 18px; text-align: center;
    }
    .ent-kpi .num { font-size: 30px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
    .ent-kpi .lbl {
        font-family: "IBM Plex Mono", monospace; font-size: 10.5px; color: var(--ink-muted);
        text-transform: uppercase; letter-spacing: 0.05em; margin-top: 6px;
    }

    table.ent-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
    table.ent-table th {
        text-align: left; font-family: "IBM Plex Mono", monospace; font-size: 10.5px;
        letter-spacing: 0.05em; text-transform: uppercase; color: var(--ink-muted);
        font-weight: 500; padding: 0 10px 8px; border-bottom: 1px solid var(--border);
    }
    table.ent-table td { padding: 10px; border-bottom: 1px solid var(--border); color: var(--ink); vertical-align: middle; }
    table.ent-table tr:last-child td { border-bottom: none; }
    .ent-pill {
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 11.5px; font-weight: 600; white-space: nowrap;
    }
    .ent-empty { color: var(--ink-muted); font-size: 13px; padding: 4px 0; }
    .ent-list-row { padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13.5px; color: var(--ink); }
    .ent-list-row:last-child { border-bottom: none; }
    .ent-list-row b { color: var(--ink); }

    .stButton > button {
        border-radius: 8px; font-family: "IBM Plex Sans", sans-serif; font-weight: 500;
        background: var(--surface); color: var(--ink); border: 1px solid var(--border);
    }
    .stButton > button:hover, .stButton > button:focus:not(:active) {
        background: var(--surface-2); color: var(--ink); border-color: var(--accent-write);
    }
    .stButton > button:active { color: var(--ink); }
    .stButton > button p { color: inherit; }
    </style>
    """,
    unsafe_allow_html=True,
)


def status_pill_html(status: str) -> str:
    s = style_for(status)
    return f'<span class="ent-pill" style="background:{s["bg"]};color:{s["fg"]};">{esc(s["label"])}</span>'


# ---------------------------------------------------------------- header ---
st.markdown('<div class="ent-eyebrow">Pulse · Live Pipeline</div>', unsafe_allow_html=True)
st.markdown(f'<div class="ent-title">📋 Daily Status — {today()}</div>', unsafe_allow_html=True)

integrations = [
    ("Jira", not config.JIRA_MOCK),
    ("Slack", not config.SLACK_MOCK),
    ("Nebius", bool(config.NEBIUS_API_KEY)),
    ("Gmail", not config.GMAIL_MOCK),
]
chips = "".join(
    f'<span class="ent-chip"><span class="ent-dot" style="background:{"#1E7A42" if live else "#8890A0"};"></span>'
    f'{esc(label)} · {"live" if live else "mock"}</span>'
    for label, live in integrations
)
st.markdown(f'<div class="ent-chip-row">{chips}</div>', unsafe_allow_html=True)

# --------------------------------------------------------------- sidebar ---
with st.sidebar:
    st.markdown('<div class="ent-eyebrow">Run pipeline</div>', unsafe_allow_html=True)
    st.caption("For the demo, or to nudge the day along without waiting on cron.")

    if st.button("▶️  Run daily kickoff", use_container_width=True):
        members = store.list_team_members()
        if not members:
            st.warning("No team members seeded — run `python scripts/seed_team.py` first.")
        else:
            pinged, already = [], []
            for m in members:
                if store.get_ping_for_date(m.id, today()) is not None:
                    already.append(m.name)
                    continue
                try:
                    start_ping(member_dict(m), today())
                    pinged.append(m.name)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Failed to ping {m.name}: {exc}")
            if pinged:
                st.success(f"Pinged: {', '.join(pinged)}")
            if already:
                st.info(f"Already pinged today, skipped: {', '.join(already)}")
            st.rerun()

    if st.button("⏱️  Run cutoff sweep", use_container_width=True):
        pending = store.list_pending_pings_for_date(today())
        for p in pending:
            try:
                resume_ping(p.thread_id, TIMEOUT_SENTINEL)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to time out {p.team_member_id}: {exc}")
        st.success(f"Swept {len(pending)} still-pending ping(s) to no_response.")
        st.rerun()

    if st.button("📧  Run collation", use_container_width=True):
        try:
            run_collation(today())
            st.success("Collation run — see History below.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Collation failed: {exc}")
        st.rerun()

    st.divider()
    with st.expander("🗑️ Danger zone"):
        st.caption(
            f"Deletes today's ({today()}) pings, statuses, and summary only — "
            "every other date's history is untouched."
        )
        confirm = st.checkbox("I understand this clears today's data", key="confirm_reset")
        if st.button("Reset today's data", disabled=not confirm, use_container_width=True):
            counts = store.reset_date(today())
            st.success(
                f"Cleared {counts['open_pings']} ping(s), {counts['status_entries']} "
                f"status entr{'y' if counts['status_entries'] == 1 else 'ies'}, "
                f"{counts['daily_summaries']} summary/summaries."
            )
            st.rerun()

# ------------------------------------------------------------------ data ---
members = store.list_team_members()
entries_by_member = {e.team_member_id: e for e in store.get_status_entries_for_date(today())}

# ---------------------------------------------------------------- KPI row --
counts = {"on_track": 0, "blocked": 0, "at_risk": 0, "no_response": 0}
for e in entries_by_member.values():
    counts[e.classified_status] = counts.get(e.classified_status, 0) + 1

kpi_cells = "".join(
    f'<div class="ent-kpi"><div class="num" style="color:{STATUS_STYLE[k]["fg"]};">{counts[k]}</div>'
    f'<div class="lbl">{esc(STATUS_STYLE[k]["label"])}</div></div>'
    for k in ("on_track", "blocked", "at_risk", "no_response")
)
st.markdown(f'<div class="ent-kpi-row">{kpi_cells}</div>', unsafe_allow_html=True)

# --------------------------------------------------------------- today -----
today_rows = ""
if not members:
    today_rows = '<tr><td colspan="4" class="ent-empty">No team members seeded yet. Run <code>python scripts/seed_team.py</code>.</td></tr>'
else:
    for m in members:
        e = entries_by_member.get(m.id)
        if e is None:
            today_rows += (
                f'<tr><td><b>{esc(m.name)}</b></td>'
                f'<td><span class="ent-pill" style="background:#F1F3F7;color:#8890A0;">Not pinged yet</span></td>'
                f'<td>—</td><td>—</td></tr>'
            )
        else:
            updated = e.created_at.strftime("%H:%M") if e.created_at else "—"
            today_rows += (
                f'<tr><td><b>{esc(m.name)}</b></td>'
                f'<td>{status_pill_html(e.classified_status)}</td>'
                f'<td>{esc(e.blocker_description) or "—"}</td>'
                f'<td>{esc(updated)}</td></tr>'
            )

st.markdown(
    f"""
    <div class="ent-card">
      <h3>Today</h3>
      <table class="ent-table">
        <tr><th>Person</th><th>Status</th><th>Blocker</th><th>Updated</th></tr>
        {today_rows}
      </table>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------- pending -----
pending = store.list_pending_pings_for_date(today())
if not pending:
    pending_html = '<div class="ent-empty">Nobody pending — everyone\'s replied or the cutoff sweep already ran.</div>'
else:
    rows = []
    for p in pending:
        m = store.get_team_member(p.team_member_id)
        name = m.name if m else p.team_member_id
        ts = p.created_at.strftime("%H:%M") if p.created_at else "?"
        rows.append(f'<div class="ent-list-row"><b>{esc(name)}</b> — pinged at {esc(ts)}, no reply yet</div>')
    pending_html = "".join(rows)

st.markdown(
    f'<div class="ent-card"><h3>Still waiting on a reply</h3>{pending_html}</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------- streaks --------
# store.get_streak() / memory_tool.get_streaks() is the one place this
# logic lives -- Ask Pulse (below) reads from the same function.
streak_rows = [(s["name"], s["streak_days"]) for s in memory_tool.get_streaks(min_days=2)]

if streak_rows:
    streaks_html = "".join(
        f'<div class="ent-list-row">⚠️ <b>{esc(name)}</b> — stuck for <b>{streak}</b> day(s) running</div>'
        for name, streak in streak_rows
    )
else:
    streaks_html = '<div class="ent-empty">Nobody\'s been stuck for 2+ days.</div>'

st.markdown(
    f"""
    <div class="ent-card">
      <h3>Blocked streaks</h3>
      <div class="ent-sub">Consecutive most-recent days at blocked or at_risk — surfaces what's stuck, not just today's snapshot.</div>
      {streaks_html}
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------- ask pulse ------
st.markdown(
    '<div class="ent-card"><h3>💬 Ask Pulse</h3>'
    '<div class="ent-sub">Answered from status history, not just today\'s '
    'snapshot — try "who\'s stuck?" or "how has Priya looked this week?"</div>',
    unsafe_allow_html=True,
)

if "ask_pulse_log" not in st.session_state:
    st.session_state.ask_pulse_log = []

if not st.session_state.ask_pulse_log:
    st.markdown('<div class="ent-empty">No questions asked yet.</div>', unsafe_allow_html=True)
for role, text in st.session_state.ask_pulse_log:
    with st.chat_message(role):
        st.write(text)

st.markdown("</div>", unsafe_allow_html=True)

# st.chat_input always renders pinned to the bottom of the page, wherever
# it's called from -- that's the intended spot for it here.
question = st.chat_input("Ask about the team's history...")
if question:
    st.session_state.ask_pulse_log.append(("user", question))
    try:
        answer = ask_pulse.ask(question)
    except Exception as exc:  # noqa: BLE001 -- one bad question shouldn't break the dashboard
        answer = f"Couldn't answer that: {exc}"
    st.session_state.ask_pulse_log.append(("assistant", answer))
    st.rerun()

# ------------------------------------------------------------ approval -----
if config.REQUIRE_SUMMARY_APPROVAL:
    st.markdown('<div class="ent-card"><h3>Pending approval</h3>', unsafe_allow_html=True)
    summary = store.get_daily_summary(today())
    if summary and summary.sent_at is None:
        st.warning("Today's summary is drafted and waiting on manager approval before it sends.")
        edited = st.text_area("Summary text", value=summary.generated_text, height=180, label_visibility="collapsed")
        ac1, ac2 = st.columns(2)
        if ac1.button("✅ Approve & send as-is", use_container_width=True):
            resume_collation(today(), "approve")
            st.success("Sent.")
            st.rerun()
        if ac2.button("✏️ Send edited version", use_container_width=True):
            resume_collation(today(), edited)
            st.success("Sent your edited version.")
            st.rerun()
    else:
        st.markdown('<div class="ent-empty">Nothing pending approval right now.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------------------- history ----
st.markdown('<div class="ent-card"><h3>History</h3>', unsafe_allow_html=True)
summaries = store.list_daily_summaries(limit=14)
if not summaries:
    st.markdown('<div class="ent-empty">No summaries generated yet.</div>', unsafe_allow_html=True)
else:
    for s in summaries:
        state = f"sent {s.sent_at.strftime('%H:%M')}" if s.sent_at else "draft, not sent"
        with st.expander(f"{s.date} — {state}"):
            st.text(s.generated_text)
            st.caption(f"recipient: {s.recipient}")
st.markdown("</div>", unsafe_allow_html=True)
