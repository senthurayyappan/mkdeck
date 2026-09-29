"""Headless Chromium, for `mkdeck check` and `mkdeck export`.

Playwright is an optional extra, so it is imported only when a command actually runs.
Importing :mod:`mkdeck`, serving a deck and building one all work without it.
"""

import contextlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from mkdeck.errors import DeckError
from mkdeck.paths import stays_inside

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

__all__ = [
    "DEFAULT_SIZE",
    "EMBED_SETTLE_MS",
    "NETWORK_IDLE_MS",
    "SETTLE_JS",
    "browser_page",
    "file_path",
    "require_playwright",
]

DEFAULT_SIZE = (1920, 1080)

INSTALL_HINT = (
    "This command needs Playwright and a Chromium for it, which mkdeck does not install by default.\n"
    "  uv add 'mkdeck[check]'   (or: pip install 'mkdeck[check]')\n"
    "  uv run playwright install chromium   (or: playwright install chromium)\n"
    "If you installed the command with `uv tool install mkdeck`, install it again with the extra,\n"
    "  uv tool install 'mkdeck[check]'   (or run it once: uvx --from 'mkdeck[check]' mkdeck check talk)\n"
    "and download the browser with `uvx playwright install chromium`.\n"
    "Both `mkdeck check` and `mkdeck export` need them."
)

NETWORK_IDLE_MS = 4_000
"""How long a slide gets to stop fetching before its screenshot is taken anyway."""

EMBED_SETTLE_MS = 300
"""A figure is an iframe of another origin, so its own paint cannot be waited on."""

SETTLE_JS = """
() => document.fonts.ready.then(
  () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
)
"""
"""Resolves once fonts are in and two frames have been drawn."""


def require_playwright() -> Any:
    """Import Playwright's synchronous API, or explain how to install it.

    Returns:
        The ``playwright.sync_api`` module.

    Raises:
        DeckError: If Playwright is not installed.
    """
    try:
        import playwright.sync_api as api
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise DeckError(INSTALL_HINT) from exc
    return api


def _first_line(exc: Exception) -> str:
    """Take the headline of a Playwright error, which follows it with a call log."""
    return (str(exc).splitlines() or [type(exc).__name__])[0]


def file_path(url: str) -> Path:
    """Turn a ``file://`` URL into the path it names.

    Args:
        url: A ``file://`` URL, percent-encoded as a browser writes it.

    Returns:
        The path, decoded and in the form of the current platform.
    """
    return Path(url2pathname(urlparse(url).path))


def _keep_inside(folder: Path) -> Callable[["Route"], None]:
    """Build the request handler that keeps a page to the files of its own deck.

    A deck may hold raw HTML, such as an iframe of `file:///etc/hosts`, and the browser would
    draw that file into a screenshot or a PDF. Only a `file:` request outside `folder` is
    refused; a request to the network goes through.

    Args:
        folder: The folder that holds the document and the files it names.

    Returns:
        The handler to register for every request of a page.
    """

    def handle(route: "Route") -> None:
        url = route.request.url
        if urlparse(url).scheme == "file" and not stays_inside(file_path(url), folder):
            route.abort("blockedbyclient")
        else:
            route.continue_()

    return handle


@contextmanager
def browser_page(size: tuple[int, int], *, folder: Path | None = None) -> Iterator["Page"]:
    """Open a page in headless Chromium and close the browser afterwards.

    Args:
        size: The viewport, as ``(width, height)`` in pixels.
        folder: The folder of the deck being opened. When given, the page cannot read a
            local file outside it, whatever the deck's own HTML asks for. A handler the
            caller adds to the page with ``page.route`` runs first and may call
            ``route.fallback()`` to hand a request on to this rule.

    Yields:
        The page.

    Raises:
        DeckError: If Playwright is missing, Chromium cannot start, or
            Chromium fails or times out while the body runs.
    """
    api = require_playwright()
    with api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except api.Error as exc:  # pragma: no cover - depends on the machine
            raise DeckError(
                f"Could not start headless Chromium: {_first_line(exc)}\n"
                "Install it with: uv run playwright install chromium (or: playwright install chromium;\n"
                "for a command installed with `uv tool`: uvx playwright install chromium).\n"
                "On a bare Linux machine, `playwright install-deps chromium` adds the system libraries it needs."
            ) from exc
        try:
            page = browser.new_page(viewport={"width": size[0], "height": size[1]})
            if folder is not None:
                page.route("**/*", _keep_inside(folder))
            yield page
        except api.Error as exc:
            what = "timed out" if isinstance(exc, api.TimeoutError) else "failed"
            raise DeckError(f"Chromium {what} while opening the deck: {_first_line(exc)}") from exc
        finally:
            with contextlib.suppress(api.Error):
                browser.close()
