# Pulse — Project Documentation

**Mastering Agentic AI Certification · Week 3 · Project 3C (Intelligent Project
Status Agent) · Track 2 — LangChain / LangGraph**

Repo: https://github.com/rajeshrram/agent-application

---

## 1. Overview

Pulse replaces the daily routine of an engineering manager DMing each person
on their team, waiting for replies, and manually writing up who's blocked —
roughly twenty minutes a day, every day. Instead, an agent does it: it reads
each person's open JIRA tickets, pings them individually on Slack, waits for
their reply — for as long as it takes — classifies it, and once everyone's
answered (or the cutoff passes), writes and sends the manager one summary
email.

**One-liner:** My agent helps an engineering manager get a daily team status
report on Slack, replacing the ~20 minutes a day spent DMing each person and
chasing blockers. It pulls each person's open JIRA tickets, pings them
individually, classifies their reply into on_track / blocked / at_risk /
no_response, and drafts a collated summary on its own using 4 tools (JIRA,
Slack, Gmail, an LLM classifier); it sends the summary email autonomously but
flags every blocker inline for the manager to act on. Success: the manager
gets an accurate daily summary by cutoff time without chasing anyone
themselves, 4 days out of 5.

It's deliberately narrow. Pulse doesn't predict anything, doesn't resolve
blockers, and doesn't message anyone except the one person it's checking in
on and the manager receiving the summary — that scope is what made it
possible to reason precisely about which of its actions are safe to run
unsupervised.

## 2. Architecture

Pulse is two separate LangGraph `StateGraph`s, each checkpointed to its own
SQLite database (separate from the app's own data store) so a paused run
survives a restart:

```
Graph 1 — ping_and_classify  (one run per person, per day)
  fetch_tickets (JIRA, read)
    -> send_ping (Slack, write)
    -> [interrupt: wait for the Slack reply — paused to disk, could be minutes or hours]
    -> classify (LLM)
    -> persist (DB)

Graph 2 — daily_collation  (one run per day, after everyone's in)
  load_entries (DB, read)
    -> generate_summary (LLM)
    -> [optional interrupt: manager approval — off by default]
    -> send_email (Gmail, write)
```

The split exists because graph 1's wait for a human reply is genuinely
open-ended — one person might answer in ninety seconds, another in three
hours — so each person gets an independently paused/resumed run, addressed
by `thread_id = <member_id>:<date>`. Graph 2 only needs to fire once, after
every graph-1 run for the day has either resolved or been swept to a
timeout.

![Pulse architecture diagram](pulse-how-one-day-runs.png)

## 3. Design decisions

### Read vs. write, made explicit

The project brief's rule — reads can be autonomous, writes deserve a human —
is the one decision every tool in Pulse was built against up front:

| Action | Type | Autonomy |
|---|---|---|
| `fetch_tickets` | read | Fully autonomous — read-only, nothing to gate. |
| `send_ping` | write | Autonomous — a low-stakes recurring notification, not destructive. |
| `classify` (LLM) | read | Autonomous — a judgment call, but it only labels data shown back to the manager, never acted on directly. |
| `send_email` | write | Autonomous by default; gate with `REQUIRE_SUMMARY_APPROVAL=true` to require sign-off first. |
| `ask_pulse` (LLM) | read | Autonomous — grounded only in stored history, answers a question, changes nothing. |

### The gate that exists

The one write worth pausing for is the manager's summary email — it's the
highest-stakes, least-reversible action in the system. Flipping
`REQUIRE_SUMMARY_APPROVAL` pauses `daily_collation` right before the send,
with the draft already persisted; `scripts/approve_summary.py` (or the
dashboard's approval panel) resumes it with either `"approve"` or
replacement text.

### Error handling

- A JIRA fetch failure logs and falls back to an empty ticket list — the
  ping still goes out rather than crashing the whole day's run for one
  person.
- A Slack send failure is raised and logged per-person; the daily kickoff
  loop catches it so one bad send doesn't stop the rest.
- No reply by the cutoff isn't treated as a failure — it's a first-class
  `no_response` state, produced by force-resuming the paused thread.
- A Gmail send failure is raised and logged, but the draft was already
  persisted before the send was attempted — nothing is lost, and it can be
  retried.

### Memory — Ask Pulse

`status_entries` already accumulates one row per person per day, which is
the persistent memory the brief asks for; what was missing was a way to
query it in plain language instead of only reading the dashboard's
precomputed streaks. `ask_pulse.ask()` reads a rolling window of that
history and hands it to the LLM — grounded only in what's actually stored —
to answer things like *"who's stuck?"* or *"how has Priya looked this
week?"*; a zero-key heuristic answers the same two question shapes without a
model call.

**Why not mem0:** the history that needs remembering already has a natural
relational shape — one row per person per day — that SQLite already owns.
A second memory store would just be a second source of truth for the same
facts, so Ask Pulse is a read query over the existing table, not a new one.

## 4. Datasets

- `data/team_members.sample.json` — three mock team members (id, name, JIRA
  account id, Slack user id, email) used to seed the local demo database.
- `data/mock_tickets.json` — mock JIRA ticket fixtures, keyed by JIRA
  account id, served when `JIRA_MOCK=true`.
- With the mock flags off: live reads from the **JIRA Cloud REST API**
  (`/rest/api/3/search/jql`), the **Slack Events API** (`message.im`
  subscription), and writes to the **Gmail API** (`gmail.send` scope).
- No dataset is used for training or fine-tuning — the two LLM calls
  (classify, summarize/ask) are zero-shot prompts against Nebius AI
  Studio's hosted `meta-llama/Llama-3.3-70B-Instruct`, via its
  OpenAI-compatible endpoint.

## 5. Try it

Zero setup, zero API keys — runs entirely on mocked JIRA/Slack/Gmail and a
keyword-heuristic classifier, and prints the full ping → reply → classify →
summary → "sent" flow to the console:

```bash
pip install -r requirements.txt
cp .env.example .env
python scripts/seed_team.py
python scripts/run_local_demo.py

# or drive it from the manager dashboard
streamlit run streamlit_app.py
```

## 6. Submission checklist

| Deliverable | Status |
|---|---|
| Code base on GitHub | https://github.com/rajeshrram/agent-application — pushed. |
| Video demo (≤5 min) | Script prepared — record and link here. |
| Project documentation | This file, plus the [rendered version](https://claude.ai/code/artifact/e08f1cc4-8993-444f-80ae-dd17e5221338) — paste into the Google Doc, or link either directly. |

Submission form: https://forms.gle/HMgTU7zy6UJ8XkJX6

---

*Built with Claude Code · Mastering Agentic AI, Week 3 · September 2026*
