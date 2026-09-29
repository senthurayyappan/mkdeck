"""The examples in the README and the docs are what the code accepts, and the docs link to real pages."""

import itertools
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

from mkdeck.markdown import parse_markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE_URL = "https://senthurayyappan.com/mkdeck/"
BANNER_URL = "https://raw.githubusercontent.com/senthurayyappan/mkdeck/main/docs/images/banner.jpg"
GUIDE_PAGES = [path for path in sorted(DOCS.rglob("*.md")) if path.is_file()]
TOP_PAGES = [path for path in (ROOT / "README.md", ROOT / "CONTRIBUTING.md") if path.is_file()]
PAGES = [*TOP_PAGES[:1], *GUIDE_PAGES]  # the pages whose code examples are tested
FENCE = re.compile(r"^(?P<fence>`{3,})(?P<language>\w*)\n(?P<body>.*?)^(?P=fence)$", re.MULTILINE | re.DOTALL)
LINK = re.compile(r"\]\((?P<target>[^)\s]+)")  # the target of a link, an image, or a badge that wraps an image
HEADING = re.compile(r"^#{1,6}\s+(?P<text>.+?)\s*#*$", re.MULTILINE)
MAX_PAGE_WORDS = 600

pytestmark = pytest.mark.skipif(not DOCS.is_dir(), reason="the docs are not part of this copy of the source")


def without_fences(text: str) -> str:
    """Drop the fenced code from a page, so that a heading in an example is not read as a heading."""
    return FENCE.sub("", text)


def prose(text: str) -> str:
    """Drop the code from a page, so that a link in an example is not checked as a link."""
    return re.sub(r"`[^`\n]*`", "", without_fences(text))


def nav_pages() -> list[str]:
    """List the pages of `mkdocs.yml` in reading order, as paths relative to `docs/`."""
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    found: list[str] = []

    def walk(items: list) -> None:
        for item in items:
            for value in item.values():
                if isinstance(value, list):
                    walk(value)
                else:
                    found.append(value)

    walk(config["nav"])
    return found


def slug(heading: str) -> str:
    """Make the anchor that the `toc` extension of Markdown gives a heading."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).replace("*", "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[-\s]+", "-", re.sub(r"[^\w\s-]", "", text).strip().lower())


def anchors(page: Path) -> set[str]:
    """Collect the anchors a page offers, numbering a repeated heading the way `toc` does."""
    seen: dict[str, int] = {}
    found: set[str] = set()
    for match in HEADING.finditer(without_fences(page.read_text(encoding="utf-8"))):
        base = slug(match.group("text"))
        count = seen.get(base, 0)
        seen[base] = count + 1
        found.add(base if count == 0 else f"{base}_{count}")
    return found


def examples(language: str) -> list:
    """Every fenced block of a language, as test parameters (where, text) named for where."""
    found = []
    for page in PAGES:
        for number, block in enumerate(FENCE.finditer(page.read_text(encoding="utf-8")), start=1):
            if block.group("language") == language:
                where = f"{page.relative_to(ROOT).as_posix()} block {number}"
                found.append(pytest.param(where, block.group("body"), id=where))
    return found


def docs_file_for(url: str) -> Path | None:
    """Map a page of the deployed site to its source file, or `None` when the site has no such page."""
    path = unquote(urlsplit(url).path).removeprefix(urlsplit(SITE_URL).path).strip("/")
    for candidate in (DOCS / f"{path}.md", DOCS / path / "index.md") if path else (DOCS / "index.md",):
        if candidate.is_file():
            return candidate
    return None


def test_the_docs_are_there_to_read() -> None:
    names = {page.relative_to(DOCS).as_posix() for page in GUIDE_PAGES}
    assert {"index.md", "api.md", "write/slide-basics.md", "extend/js.md", "start/first-deck.md"} <= names
    assert {page.name for page in TOP_PAGES} == {"README.md", "CONTRIBUTING.md"}


def test_the_nav_lists_every_page_once_and_only_real_pages() -> None:
    listed = nav_pages()
    assert len(listed) == len(set(listed)), "a page appears twice in the nav"
    on_disk = {page.relative_to(DOCS).as_posix() for page in GUIDE_PAGES}
    assert set(listed) == on_disk


def test_every_page_ends_with_a_next_line_that_points_at_the_next_page() -> None:
    listed = nav_pages()
    for here, following in itertools.pairwise(listed[1:]):  # the home page and the last page have no Next line
        lines = (DOCS / here).read_text(encoding="utf-8").rstrip().splitlines()
        assert lines[-1].startswith("Next: ["), f"{here} does not end with a Next line"
        target = LINK.search(lines[-1])
        assert target is not None, here
        resolved = (DOCS / here).parent / target.group("target").split("#")[0]
        assert resolved.resolve() == (DOCS / following).resolve(), f"{here} points at {target.group('target')}"


@pytest.mark.parametrize("page", GUIDE_PAGES, ids=lambda page: page.relative_to(DOCS).as_posix())
def test_a_page_stays_short(page: Path) -> None:
    """A page over the limit is split into two, so that a reader can take it in one sitting."""
    words = len(re.findall(r"\w[\w'./-]*", prose(page.read_text(encoding="utf-8"))))
    assert words <= MAX_PAGE_WORDS, f"{page.relative_to(DOCS)} holds {words} words"


@pytest.mark.parametrize("page", GUIDE_PAGES, ids=lambda page: page.relative_to(DOCS).as_posix())
def test_every_relative_link_of_the_docs_resolves(page: Path) -> None:
    text = prose(page.read_text(encoding="utf-8"))
    for match in LINK.finditer(text):
        target = match.group("target")
        if urlsplit(target).scheme or target.startswith("#"):
            continue
        pointed, _, anchor = target.partition("#")
        destination = (page.parent / unquote(pointed)).resolve()
        assert destination.is_file(), f"{page.relative_to(DOCS)} links to {target}, which is not a file"
        if anchor and destination.suffix == ".md":
            assert anchor in anchors(destination), f"{page.relative_to(DOCS)} links to {target}: no such heading"


@pytest.mark.parametrize("page", GUIDE_PAGES, ids=lambda page: page.relative_to(DOCS).as_posix())
def test_a_link_to_the_page_itself_finds_its_heading(page: Path) -> None:
    for match in LINK.finditer(prose(page.read_text(encoding="utf-8"))):
        target = match.group("target")
        if target.startswith("#"):
            assert target[1:] in anchors(page), f"{page.relative_to(DOCS)} links to {target}: no such heading"


@pytest.mark.parametrize("page", TOP_PAGES, ids=lambda page: page.name)
def test_an_absolute_link_to_the_docs_site_names_a_page_of_the_nav(page: Path) -> None:
    listed = {(DOCS / name).resolve() for name in nav_pages()}
    for match in LINK.finditer(prose(page.read_text(encoding="utf-8"))):
        target = match.group("target")
        if target.startswith(SITE_URL):
            found = docs_file_for(target)
            assert found is not None, f"{page.name} links to {target}, which is not a page of the docs"
            assert found.resolve() in listed, f"{page.name} links to {target}, which is not in the nav"
            anchor = urlsplit(target).fragment
            if anchor:
                assert anchor in anchors(found), f"{page.name} links to {target}: no such heading"


def test_the_readme_opens_with_the_banner_and_holds_no_relative_link() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.startswith(f"![mkdeck: Markdown in, slide deck out]({BANNER_URL})")
    for match in LINK.finditer(prose(text)):
        assert urlsplit(match.group("target")).scheme in {"http", "https"}, match.group("target")


def test_the_contributing_guide_holds_no_relative_link() -> None:
    text = prose((ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"))
    for match in LINK.finditer(text):
        assert urlsplit(match.group("target")).scheme in {"http", "https"}, match.group("target")


def test_the_banner_is_in_the_repository_and_on_the_landing_page() -> None:
    assert (DOCS / "images" / "banner.jpg").is_file()
    assert "](images/banner.jpg)" in (DOCS / "index.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(("where", "text"), examples("markdown"))
def test_every_markdown_example_is_a_deck_file_that_parses(where: str, text: str) -> None:
    """Pasted as a whole file, a snippet that starts with `---` used to fail with "frontmatter never closed"."""
    parse_markdown(text, source=where)


@pytest.mark.parametrize(("where", "text"), examples("js"))
def test_no_javascript_example_imports_statically(where: str, text: str) -> None:
    """`extra_js` is a classic script, where a top-level `import ... from` is a syntax error."""
    assert not re.search(r"^\s*import\s+[\w{*]", text, re.MULTILINE), where
