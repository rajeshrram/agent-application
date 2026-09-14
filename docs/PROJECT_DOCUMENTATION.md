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

## 5. Build log & prompts

The initial pipeline — both graphs, the three tools, the scheduler, the
dashboard — was already working before this build log starts; that earlier
session isn't captured here. What follows is the real, unedited sequence of
what was asked of Claude Code after that, and what came back.

| I asked | What got built |
|---|---|
| Push was rejected — "would publish a private email address" | Set the repo's git email to my GitHub noreply address, amended the commit, pushed. |
| "I would like to create the diagram like the attached for this project" (a hand-drawn-style architecture poster) | Mapped Pulse's real architecture onto the same 4-stage layout; discovered no `node`/`bun` in this environment for the interactive canvas editor, published a static HTML artifact instead. |
| "kindly create a png file and add to the repo" | Rendered the artifact with headless Chrome, cropped it, committed it to `docs/`, linked it from the README. |
| "Is this application supports all the criteria for the project 3?" | Audited the app field-by-field against the Week 3 framework and Project 3C's spec; flagged two soft gaps — daily vs. weekly cadence, and "memory" being a dashboard read rather than something the agent could answer questions from. |
| "yes please" (close the memory gap) | Built `memory_tool.py`, `llm.answer_question()` + heuristic fallback, `ask_pulse.py`, the dashboard's Ask Pulse chat card, and its tests. |
| "whenever i click the cutoff [sweep], the reply is missing — did you add a delay?" | Grepped for any sleep/delay (none); traced two silent-failure paths in the webhook — an unlogged signature rejection, and a legitimate claim-race against the cutoff sweep — and made both observable instead of changing behavior. |
| "what am I submitting?" | A field-by-field mapping of the Week 3 handout's submission requirements onto this repo. |
| "1. push it. 2. demo transcript. 3. create a doc" | Pushed the three pending commits, wrote the demo script, and produced the project-report artifact. |
| "i want to create a project documentation in docs" | This file. |

## 6. Iterations

What changed along the way:

- **Diagram delivery.** Started down the interactive Design Canvas path
  (drag-to-edit artboards) — the tooling that seeds it needs Node or Bun,
  neither of which is installed here. Pivoted to a static page rendered to
  PNG with headless Chrome and cropped with Pillow. Traded away live
  editing; kept zero extra tooling.
- **Memory.** The brief suggests mem0 as a persistent memory layer. Went
  with a read-only query layer over the existing `status_entries` table
  instead, once it was clear that table already had the shape a memory
  store would need — one row per person per day.
- **Streak logic.** Was written once, inline, in the dashboard. Pulled out
  into `store.get_streak()` so the dashboard and the new memory tool can't
  drift apart on what "stuck for two days" means.
- **Webhook debugging.** First hypothesis (from the bug report) was a
  deliberately added delay. It wasn't — the actual causes were two failure
  paths that had always been silent: an unlogged 401 on signature mismatch,
  and an unlogged claim-race between a real Slack reply and a
  manually-triggered cutoff sweep.

## 7. Learnings

What I'd tell the next person building one of these:

- **Read vs. write is load-bearing, not academic.** Deciding it per-tool up
  front turned every later "should this run on its own" question into a
  lookup instead of a debate.
- **`interrupt()` + a checkpointer is the right tool specifically because
  the wait is open-ended.** A reply can take minutes or hours; hand-rolling
  that pause/resume outside LangGraph would mean building a worse version
  of the same checkpointer.
- **Once two independent triggers can touch the same row, you need an
  atomic claim, not a check-then-write.** The cutoff sweep and the Slack
  webhook can both try to resume the same paused thread;
  `UPDATE ... WHERE status='pending'` is what makes only one of them win.
- **A race you don't log looks like a mystery bug.** The claim-race above
  was correct the whole time — it just wasn't visible, so it read as
  "replies going missing" instead of "an expected race, unobserved."
- **Zero-key heuristic fallbacks pay for themselves.** Classify, summarize,
  and now ask-pulse all degrade to a plain-Python heuristic with no API
  key — that's what makes the whole pipeline demoable in one command with
  no setup.

## 8. Try it

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

## 9. Submission checklist

| Deliverable | Status |
|---|---|
| Code base on GitHub | https://github.com/rajeshrram/agent-application — pushed. |
| Video demo (≤5 min) | Script prepared — record and link here. |
| Project documentation | This file, plus the [rendered version](https://claude.ai/code/artifact/e08f1cc4-8993-444f-80ae-dd17e5221338) — paste into the Google Doc, or link either directly. |

Submission form: https://forms.gle/HMgTU7zy6UJ8XkJX6

---

*Built with Claude Code · Mastering Agentic AI, Week 3 · September 2026*
