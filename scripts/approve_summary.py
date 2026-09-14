"""Only needed if REQUIRE_SUMMARY_APPROVAL=true in .env. Resumes a paused
daily_collation run for the given date.

Usage:
    python scripts/approve_summary.py 2026-09-12 approve
    python scripts/approve_summary.py 2026-09-12 "edited summary text..."
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.graphs.daily_collation import resume_collation  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    date, decision = sys.argv[1], sys.argv[2]
    resume_collation(date, decision)


if __name__ == "__main__":
    main()
