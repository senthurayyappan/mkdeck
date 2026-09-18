"""Check the first line of a commit message or a pull request title."""

import os
import re
import sys
from pathlib import Path

HEADER = re.compile(r"(?:feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(?:\([^()\r\n]+\))?!?: \S.*")


def valid_header(message: str) -> bool:
    """Return True if the first line follows the Conventional Commit format."""
    lines = message.splitlines()
    return bool(lines and HEADER.fullmatch(lines[0]))


def main() -> None:
    """Check a commit message file, or read PR_TITLE if no file is given."""
    message = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else os.environ["PR_TITLE"]
    if not valid_header(message):
        print("Use a Conventional Commit header, e.g. feat(cli): add export command", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
