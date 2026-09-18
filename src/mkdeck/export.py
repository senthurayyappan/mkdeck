"""Print a deck to PDF with headless Chromium, one page per slide.

Playwright is an optional extra, so it is imported only when an export actually
runs.
"""

import dataclasses
import shutil
import tempfile
from pathlib import Path

from mkdeck.build import build_deck, find_markdown, load_source
from mkdeck.check import DEFAULT_SIZE, launch_browser, require_playwright
from mkdeck.errors import DeckError


def _print_document(path: Path, workdir: Path, *, size: tuple[int, int]) -> Path:
    """Get an HTML document to print, building the deck when needed.

    The deck is rebuilt with reveal's dimensions pinned to the page size, which
    is what reveal's print view needs to paginate one slide per page.

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
    find_markdown(path)
    loaded = load_source(path)
    width, height = size
    printable = dataclasses.replace(
        loaded.deck,
        reveal={**loaded.deck.reveal, "width": width, "height": height, "minScale": 1, "maxScale": 1, "margin": 0},
    )
    return build_deck(printable, workdir, config=loaded.config, source=loaded.directory)


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
        DeckError: If Playwright is missing, Chromium cannot start, or the path
            holds no deck.
    """
    sync_playwright = require_playwright()
    width, height = size
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="mkdeck-export-"))
    try:
        document = _print_document(Path(path), workdir, size=size)
        with sync_playwright() as playwright:
            browser = launch_browser(playwright)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"{document.resolve().as_uri()}?print-pdf")
            page.wait_for_function("document.querySelectorAll('.reveal .slides section').length > 0")
            page.wait_for_timeout(1200)
            page.emulate_media(media="screen")
            page.pdf(
                path=str(out),
                width=f"{width}px",
                height=f"{height}px",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                prefer_css_page_size=False,
            )
            browser.close()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if not out.is_file():  # pragma: no cover - depends on the browser
        raise DeckError(f"Chromium produced no PDF at {out}.")
    print(f"Wrote {out}")
    return out
