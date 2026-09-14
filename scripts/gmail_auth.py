"""One-time interactive OAuth authorization for Gmail send.

Run this yourself (it opens a browser for the Google consent screen):
    python scripts/gmail_auth.py

Prerequisite: credentials.json (an OAuth Desktop-app client secret) in the
project root -- see README.md's "Turning on real integrations" section for
how to get one from Google Cloud Console.

On success, writes token.json -- after that, src/tools/gmail_tool.py sends
unattended (the refresh token keeps it working without repeating this step).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from src import config  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main() -> None:
    creds_path = Path(config.GMAIL_CREDENTIALS_PATH)
    if not creds_path.exists():
        print(f"Missing {creds_path}. Download it from Google Cloud Console "
              f"(APIs & Services > Credentials > OAuth client ID > Desktop app) "
              f"and save it at that path first.")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_path = Path(config.GMAIL_TOKEN_PATH)
    token_path.write_text(creds.to_json())
    print(f"Saved {token_path}. GMAIL_MOCK=false will now send for real.")


if __name__ == "__main__":
    main()
