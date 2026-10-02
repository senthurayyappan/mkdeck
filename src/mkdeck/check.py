"""Check a built deck in headless Chromium, slide by slide.

Playwright is an optional extra, so it is imported only when a check actually
runs. Importing :mod:`mkdeck`, serving a deck and building one all work without
it.
"""

import contextlib
import json
import tempfile
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict
from urllib.parse import urlparse

from mkdeck.browser import (
    DEFAULT_SIZE,
    EMBED_SETTLE_MS,
    NETWORK_IDLE_MS,
    SETTLE_JS,
    browser_page,
    file_path,
    require_playwright,
)
from mkdeck.source import load_source

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

__all__ = ["Probe", "check_deck", "report_text", "slide_flags"]

EMBED_BLOCK_BYTES = 2_000_000
"""Embeds larger than this are replaced with a stub so the check stays fast."""

BLOCKED_BODY = (
    '<html><body style="margin:0;background:#f4f4f4;font:14px '
    'Roboto,sans-serif;color:#999">'
    '<div style="padding:12px">embed (blocked in the '
    "checker)</div></body></html>"
)

ROLLOUT_WAIT_MS = 20_000
"""How long a slide's rollouts and diagrams get to load.

After that the check reports them as failed.
"""

FIGURES_DONE_JS = """
() => {
  const slide = document.querySelector('.reveal .slides section.present');
  const settled = (host, states) => states.includes(host.dataset.mkdState);
  const rollouts = slide.querySelectorAll('deck-rollout[src]');
  const diagrams = slide.querySelectorAll('deck-mermaid');
  const ready = (host) => settled(host, ['ready', 'error']);
  const done = (host) => settled(host, ['done', 'error']);
  return !slide
    || (Array.from(rollouts).every(ready)
      && Array.from(diagrams).every(done));
}
"""
"""True once the slide on screen has finished loading.

Every rollout and diagram has loaded or failed.
"""


class Scroller(TypedDict):
    """An element inside a slide that would show a scrollbar."""

    tag: str
    cls: str
    sw: int
    cw: int
    sh: int
    ch: int


class Overlap(TypedDict):
    """Two blocks of a slide that cover each other.

    The overlap is ``ox`` by ``oy`` pixels.
    """

    i: int
    j: int
    ox: int
    oy: int


class TableProbe(TypedDict):
    """The size of the slide's table."""

    rows: int
    cols: int
    width: int


class RolloutProbe(TypedDict):
    """A rollout on the slide that is not drawing."""

    src: str
    state: str
    message: str


class Probe(TypedDict, total=False):
    """What ``probe.js`` measured on one slide, plus its number and flags."""

    n: int
    error: str
    vw: int
    vh: int
    top: int
    bottom: int
    left: int
    right: int
    overflow_top: int
    overflow_bottom: int
    into_chrome: bool
    scrollers: list[Scroller]
    overlaps: list[Overlap]
    sentence_chars: int
    bullets: int
    bullet_chars: list[int]
    table: TableProbe | None
    figures: int
    formula_blocks: int
    katex_errors: int
    mermaid_errors: int
    math_unrendered: int
    layout: str
    id: str
    dense: bool
    rollout_errors: list[RolloutProbe]
    chrome_left: str
    chrome_right: str
    flags: list[str]


@cache
def probe_script() -> str:
    """Read the JavaScript that measures the slide on screen.

    It lives beside this module.
    """
    return Path(__file__).with_name("probe.js").read_text(encoding="utf-8")


def blocks_embed(url: str, *, subframe: bool) -> bool:
    """Say whether a request is a nested page too heavy to load in a check.

    The deck itself is never blocked, however large it is: a single-file deck
    that carries a rollout is several megabytes.

    Args:
        url: The URL the browser is about to fetch.
        subframe: True when the request navigates an iframe rather than the
            page.

    Returns:
        True when the request should get a stub in place of the page.
    """
    parts = urlparse(url)
    if (
        not subframe
        or parts.scheme != "file"
        or not parts.path.lower().endswith((".html", ".htm"))
    ):
        return False
    try:
        return file_path(url).stat().st_size > EMBED_BLOCK_BYTES
    except OSError:
        return False


def _route(route: "Route") -> None:
    """Stub a heavy iframe, and let every other request through."""
    request = route.request
    subframe = (
        request.is_navigation_request()
        and request.frame.parent_frame is not None
    )
    if blocks_embed(request.url, subframe=subframe):
        route.fulfill(status=200, content_type="text/html", body=BLOCKED_BODY)
    else:
        # on to the rule that keeps the page to the files of its deck
        route.fallback()


def _prepare(path: Path, workdir: Path) -> Path:
    """Get an HTML document to check, building the deck when needed.

    A deck is built as one file, so a slide that draws a rollout can read it
    from the document instead of fetching it, which a ``file://`` page may not.

    Args:
        path: A built ``.html`` file, a Markdown file, or a deck folder.
        workdir: A scratch folder the deck is built into.

    Returns:
        The HTML document to open.

    Raises:
        DeckError: If the path holds no deck.
    """
    path = Path(path)
    if path.is_file() and path.suffix.lower() in {".html", ".htm"}:
        return path
    return load_source(path).build(workdir / "deck.html", single_file=True)


def slide_flags(record: Probe) -> list[str]:
    """List everything wrong with one slide.

    The same list is written into ``report.json`` and printed in ``report.txt``,
    so a program reading the JSON sees exactly what a person reading the text
    sees.

    Args:
        record: The probe result for a slide.

    Returns:
        One string per finding, empty when the slide is clean.
    """
    flags: list[str] = []
    if (
        record.get("overflow_top", 0) > 0
        or record.get("overflow_bottom", 0) > 0
    ):
        flags.append(
            f"OVERFLOW top {record.get('overflow_top', 0)}px bottom "
            f"{record.get('overflow_bottom', 0)}px"
        )
    if record.get("into_chrome"):
        flags.append("INTO-CHROME")
    if record.get("scrollers"):
        details = ", ".join(
            f"{s['tag']}.{s['cls']} {s['sw']}>{s['cw']}w {s['sh']}>{s['ch']}h"
            for s in record["scrollers"]
        )
        flags.append(f"SCROLLBAR {details}")
    if record.get("overlaps"):
        flags.append("OVERLAP " + json.dumps(record["overlaps"]))
    if record.get("katex_errors"):
        flags.append(f"KATEX-ERROR x{record['katex_errors']}")
    if record.get("mermaid_errors"):
        flags.append(f"MERMAID-ERROR x{record['mermaid_errors']}")
    if record.get("math_unrendered"):
        flags.append(f"MATH-UNRENDERED x{record['math_unrendered']}")
    for rollout in record.get("rollout_errors", []):
        flags.append(
            f"ROLLOUT-ERROR {rollout['src']}: "
            f"{rollout['message'] or 'still ' + rollout['state']}"
        )
    return flags


def _format_row(record: Probe) -> str:
    """Format one slide's findings as a report line.

    Args:
        record: The probe result for a slide.

    Returns:
        A single line of ``report.txt``.
    """
    number = record.get("n", 0)
    slide_id = str(record.get("id") or "")
    if record.get("error"):
        return f"{number:3d} {slide_id:26s} {record['error']}"
    flags = slide_flags(record)
    table = record.get("table")
    table_text = (
        f" table {table['rows']}x{table['cols']} {table['width']}px"
        if table
        else ""
    )
    bullets = record.get("bullets", 0)
    bullet_text = (
        "/" + "+".join(str(n) for n in record.get("bullet_chars", []))
        if bullets
        else ""
    )
    return (
        f"{number:3d} {slide_id:26s} {record.get('layout', ''):9s}"
        f" sent {record.get('sentence_chars', 0):4d}"
        f" bul {bullets}{bullet_text}"
        f" fig {record.get('figures', 0)}{table_text}"
        f" fb {record.get('formula_blocks', 0)}"
        f" h {record.get('top', 0)}-{record.get('bottom', 0)}"
        f"  {' | '.join(flags) if flags else 'ok'}"
    )


def report_text(
    records: list[Probe], *, size: tuple[int, int], path: Path | str
) -> str:
    """Lay the findings out as ``report.txt`` does.

    Args:
        records: One probe result per checked slide.
        size: The viewport the deck was checked at.
        path: The deck that was checked.

    Returns:
        A header line and one line per slide, ending in a newline.
    """
    header = f"viewport {size[0]}x{size[1]}, deck {path}"
    return (
        header
        + "\n"
        + "\n".join(_format_row(record) for record in records)
        + "\n"
    )


def _probe_slide(page: "Page", number: int, *, shots: bool) -> Probe:
    """Go to a slide, wait for it to settle, and measure it.

    Args:
        page: The page the deck is open in.
        number: The slide to go to, counting from 1.
        shots: True when a screenshot follows, which waits for the network too.

    Returns:
        The probe result, numbered.
    """
    timed_out = require_playwright().TimeoutError
    page.evaluate("(i) => window.Reveal && Reveal.slide(i, 0)", number - 1)
    # A rollout that never answers, or a page that never goes quiet, is not
    # fatal: the probe reports the first, and a screenshot of the second is
    # still worth having.
    with contextlib.suppress(timed_out):
        page.wait_for_function(FIGURES_DONE_JS, timeout=ROLLOUT_WAIT_MS)
    if shots:
        with contextlib.suppress(timed_out):
            page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
        if page.evaluate(
            "!!document.querySelector('.reveal .slides section.present "
            "deck-embed')"
        ):
            page.wait_for_timeout(EMBED_SETTLE_MS)
    page.evaluate(SETTLE_JS)
    record: Probe = page.evaluate(probe_script())
    record["n"] = number
    return record


def check_deck(
    path: Path | str,
    *,
    out: Path | str = Path("report"),
    size: tuple[int, int] = DEFAULT_SIZE,
    shots: bool = True,
) -> list[Probe]:
    """Open a deck in headless Chromium and report what each slide does.

    Every slide is measured for content overflow past the viewport, elements
    that would show a scrollbar, elements overlapping the chrome, KaTeX
    failures, diagrams that did not draw and rollouts that did not load. A
    screenshot is written for each slide unless ``shots`` is off, and the
    findings go to ``report.json`` and ``report.txt`` in ``out``.

    Args:
        path: A built ``.html`` file, a Markdown file, or a deck folder.
        out: The folder the report and screenshots are written to.
        size: The viewport, as ``(width, height)`` in pixels.
        shots: True to write one PNG per slide.

    Returns:
        One record per slide, the same data as ``report.json``.

    Raises:
        DeckError: If Playwright is missing, Chromium cannot start or fails, or
            the path holds no deck.
    """
    require_playwright()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob(
        "slide_*.png"
    ):  # from an earlier run, maybe of a longer deck
        stale.unlink()
    records: list[Probe] = []
    with tempfile.TemporaryDirectory(
        prefix="mkdeck-check-", ignore_cleanup_errors=True
    ) as workdir:
        document = _prepare(Path(path), Path(workdir))
        with browser_page(size, folder=document.parent) as page:
            page.route("**/*", _route)
            page.goto(document.resolve().as_uri())
            page.wait_for_function("window.Reveal && Reveal.isReady()")
            total = page.evaluate(
                "document.querySelectorAll('.reveal .slides section').length"
            )
            for number in range(1, total + 1):
                records.append(_probe_slide(page, number, shots=shots))
                if shots:
                    page.screenshot(path=str(out / f"slide_{number:02d}.png"))
    for record in records:
        record["flags"] = slide_flags(record)
    (out / "report.json").write_text(
        json.dumps(records, indent=1), encoding="utf-8"
    )
    (out / "report.txt").write_text(
        report_text(records, size=size, path=path), encoding="utf-8"
    )
    return records
