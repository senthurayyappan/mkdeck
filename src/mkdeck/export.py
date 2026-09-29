"""Print a deck to PDF with headless Chromium, one page per slide.

Playwright is an optional extra, so it is imported only when an export actually
runs.
"""

import contextlib
import dataclasses
import tempfile
from pathlib import Path

from mkdeck.check import (
    DEFAULT_SIZE,
    EMBED_SETTLE_MS,
    NETWORK_IDLE_MS,
    SETTLE_JS,
    browser_page,
    require_playwright,
)
from mkdeck.errors import DeckError
from mkdeck.source import load_source

__all__ = ["export_deck"]

PRINT_READY_JS = """
() => window.Reveal && Reveal.isReady() && document.querySelectorAll('.reveal .slides .pdf-page').length > 0
  && document.documentElement.dataset.mkdPrint === 'ready'
"""
"""True once reveal has laid the slides out as printed pages and mkdeck.js has filled them."""

PRINT_WAIT_MS = 120_000
"""How long the pages get to become ready; a rollout is read and drawn one at a time."""


def _print_document(path: Path, workdir: Path, *, size: tuple[int, int]) -> Path:
    """Get an HTML document to print, building the deck when needed.

    The deck is rebuilt with reveal's dimensions pinned to the page size, which
    is what reveal's print view needs to paginate one slide per page. It is
    built as one file, so a slide that draws a rollout can read it from the
    document instead of fetching it, which a ``file://`` page may not.

    Args:
        path: A built ``.html`` file, a Markdown file, or a deck folder.
        workdir: A scratch folder the deck is built into.
        size: The page size, as ``(width, height)`` in pixels.

    Returns:
        The HTML document to open.

    Raises:
        DeckError: If the path holds no deck.
    """
    path = Path(path)
    if path.is_file() and path.suffix.lower() in {".html", ".htm"}:
        return path
    loaded = load_source(path)
    width, height = size
    printable = dataclasses.replace(
        loaded.deck,
        reveal={**loaded.deck.reveal, "width": width, "height": height, "minScale": 1, "maxScale": 1, "margin": 0},
    )
    return printable.build(workdir / "deck.html", source=loaded.directory, single_file=True)


def export_deck(
    path: Path | str,
    out: Path | str = Path("deck.pdf"),
    *,
    size: tuple[int, int] = DEFAULT_SIZE,
) -> Path:
    """Export a deck to a PDF, one page per slide.

    Args:
        path: A built ``.html`` file, a Markdown file, or a deck folder.
        out: The PDF to write.
        size: The page size, as ``(width, height)`` in pixels.

    Returns:
        The path of the written PDF.

    Raises:
        DeckError: If Playwright is missing, Chromium cannot start or fails,
            or the path holds no deck.
    """
    timed_out = require_playwright().TimeoutError
    width, height = size
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mkdeck-export-", ignore_cleanup_errors=True) as workdir:
        document = _print_document(Path(path), Path(workdir), size=size)
        with browser_page(size) as page:
            page.goto(f"{document.resolve().as_uri()}?print-pdf")
            page.wait_for_function(PRINT_READY_JS, timeout=PRINT_WAIT_MS)
            with contextlib.suppress(timed_out):
                page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
            # A figure is an iframe of another origin, so its own paint cannot be waited on.
            page.wait_for_timeout(EMBED_SETTLE_MS)
            page.evaluate(SETTLE_JS)
            page.emulate_media(media="screen")
            page.pdf(
                path=str(out),
                width=f"{width}px",
                height=f"{height}px",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                prefer_css_page_size=False,
            )
    if not out.is_file():  # pragma: no cover - depends on the browser
        raise DeckError(f"Chromium produced no PDF at {out}.")
    return out
