"""Load data/team_members.sample.json into the app DB.
Usage: python scripts/seed_team.py [path/to/team.json]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import store  # noqa: E402

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "team_members.sample.json"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    members = json.loads(path.read_text())

    store.init_db()
    for m in members:
        store.upsert_team_member(m)
        print(f"seeded {m['id']} ({m['name']})")


if __name__ == "__main__":
    main()
