"""Fetch a team member's open JIRA tickets.

Read-only tool -> safe to run fully autonomously (per the framework's
"reads can be autonomous, writes need a human" rule).
"""
import json
from pathlib import Path
from typing import Dict, List

import requests

from src import config

_MOCK_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "mock_tickets.json"

# JQL: everything assigned to this person that isn't Done/Closed.
_JQL_TEMPLATE = 'assignee = "{account_id}" AND status NOT IN (Done, Closed) ORDER BY updated DESC'


def fetch_tickets(member: Dict) -> List[Dict]:
    """Returns a list of {ticket_id, title, status} for the given member.

    `member` is a dict with at least `jira_account_id`.
    """
    if config.JIRA_MOCK:
        return _fetch_mock(member["jira_account_id"])
    return _fetch_real(member["jira_account_id"])


def _fetch_mock(account_id: str) -> List[Dict]:
    all_mock = json.loads(_MOCK_DATA_PATH.read_text())
    return all_mock.get(account_id, all_mock.get("_default", []))


def _fetch_real(account_id: str) -> List[Dict]:
    """TODO: if you're on JIRA Server/Data Center (not Cloud), swap `auth=`
    for `headers={"Authorization": f"Bearer {token}"}` -- PAT, not Basic auth.

    Uses /rest/api/3/search/jql (POST), not the old /rest/api/3/search (GET)
    -- Atlassian retired that one (returns 410 Gone) as part of their JQL
    search API migration.
    """
    url = f"{config.JIRA_BASE_URL}/rest/api/3/search/jql"
    jql = _JQL_TEMPLATE.format(account_id=account_id)
    try:
        resp = requests.post(
            url,
            json={"jql": jql, "fields": ["summary", "status"], "maxResults": 50},
            auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN),
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        # Fail soft: an empty ticket list still lets the ping go out, it'll
        # just say "no open tickets found" -- surfaced to the person, not a
        # silent crash of the whole run.
        print(f"[jira_tool] fetch failed for {account_id}: {exc}")
        return []

    issues = resp.json().get("issues", [])
    return [
        {
            "ticket_id": issue["key"],
            "title": issue["fields"]["summary"],
            "status": issue["fields"]["status"]["name"],
        }
        for issue in issues
    ]
