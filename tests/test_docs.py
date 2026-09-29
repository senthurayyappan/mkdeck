"""The examples in the README and the docs are what the code accepts."""

import re
from pathlib import Path

import pytest

from mkdeck.markdown import parse_markdown

ROOT = Path(__file__).resolve().parents[1]
PAGES = [path for path in (ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))) if path.is_file()]
FENCE = re.compile(r"^(?P<fence>`{3,})(?P<language>\w*)\n(?P<body>.*?)^(?P=fence)$", re.MULTILINE | re.DOTALL)


def examples(language: str) -> list:
    """Every fenced block of a language, as test parameters (where, text) named for where."""
    found = []
    for page in PAGES:
        for number, block in enumerate(FENCE.finditer(page.read_text(encoding="utf-8")), start=1):
            if block.group("language") == language:
                where = f"{page.name} block {number}"
                found.append(pytest.param(where, block.group("body"), id=where))
    return found


def test_the_docs_are_there_to_read() -> None:
    if not PAGES:
        pytest.skip("the docs are not part of this copy of the source")
    assert {page.name for page in PAGES} >= {"README.md", "writing-slides.md", "extending.md"}


@pytest.mark.parametrize(("where", "text"), examples("markdown"))
def test_every_markdown_example_is_a_deck_file_that_parses(where: str, text: str) -> None:
    """Pasted as a whole file, a snippet that starts with `---` used to fail with "frontmatter never closed"."""
    parse_markdown(text, source=where)


@pytest.mark.parametrize(("where", "text"), examples("js"))
def test_no_javascript_example_imports_statically(where: str, text: str) -> None:
    """`extra_js` is a classic script, where a top-level `import ... from` is a syntax error."""
    assert not re.search(r"^\s*import\s+[\w{*]", text, re.MULTILINE), where
