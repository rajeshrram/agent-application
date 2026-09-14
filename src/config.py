"""Central config, loaded once from the environment / .env file.

Every external integration has a *_MOCK flag. With all three MOCK flags on
(the default) the whole system runs with zero API keys and zero network
calls -- see scripts/run_local_demo.py. Flip them off one at a time as you
wire in the real JIRA / Slack / Gmail integrations.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


# --- LLM (Nebius Token Factory / Nebius AI Studio, OpenAI-compatible API) ---
NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY", "")
NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1")
NEBIUS_MODEL = os.getenv("NEBIUS_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

# --- Mock switches ---
JIRA_MOCK = _bool("JIRA_MOCK")
SLACK_MOCK = _bool("SLACK_MOCK")
GMAIL_MOCK = _bool("GMAIL_MOCK")

# --- JIRA ---
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

# --- Slack ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")

# --- Gmail ---
GMAIL_MANAGER_ADDRESS = os.getenv("GMAIL_MANAGER_ADDRESS", "manager@example.com")
GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "token.json")

# --- Storage ---
APP_DB_PATH = os.getenv("APP_DB_PATH", str(BASE_DIR / "data" / "app.db"))
CHECKPOINT_DB_PATH = os.getenv(
    "CHECKPOINT_DB_PATH", str(BASE_DIR / "data" / "checkpoints.sqlite")
)

# --- Schedule ---
PING_HOUR = _int("PING_HOUR", 9)
PING_MINUTE = _int("PING_MINUTE", 0)
CUTOFF_HOUR = _int("CUTOFF_HOUR", 16)
CUTOFF_MINUTE = _int("CUTOFF_MINUTE", 0)

# --- Human-in-the-loop ---
REQUIRE_SUMMARY_APPROVAL = _bool("REQUIRE_SUMMARY_APPROVAL", "false")
