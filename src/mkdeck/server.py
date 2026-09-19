"""Serve a deck and rebuild it when its source changes.

The page is told to reload over a server-sent-event stream rather than a
websocket: the client side is four lines of ``EventSource`` and the dependency
list stays short.
"""

import queue
import shutil
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from watchfiles import watch

from mkdeck.build import build_deck, load_source
from mkdeck.config import DeckConfig
from mkdeck.errors import DeckError
from mkdeck.model import Deck

RELOAD_PATH = "/__mkdeck__/events"
"""Endpoint the page listens on for reload events."""

HEARTBEAT_SECONDS = 15.0
"""How often a quiet stream sends a comment, so proxies keep it open."""

RELOAD_SNIPPET = f"""<script>
/* mkdeck live reload: the dev server pushes "reload" when the deck is rebuilt. */
(function () {{
  var source = new EventSource("{RELOAD_PATH}");
  source.onmessage = function (event) {{ if (event.data === "reload") {{ window.location.reload(); }} }};
}})();
</script>
"""

Rebuild = Callable[[Path], None]


class _ReloadHub:
    """Fan a reload message out to every open page."""

    def __init__(self) -> None:
        """Start with no listeners."""
        self._lock = threading.Lock()
        self._listeners: set[queue.SimpleQueue[str | None]] = set()

    def listen(self) -> "queue.SimpleQueue[str | None]":
        """Register a listener.

        Returns:
            The queue the listener reads messages from.
        """
        channel: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        with self._lock:
            self._listeners.add(channel)
        return channel

    def drop(self, channel: "queue.SimpleQueue[str | None]") -> None:
        """Remove a listener.

        Args:
            channel: The queue returned by :meth:`listen`.
        """
        with self._lock:
            self._listeners.discard(channel)

    def notify(self, message: str) -> None:
        """Send a message to every listener.

        Args:
            message: The event payload, normally ``reload``.
        """
        with self._lock:
            listeners = list(self._listeners)
        for channel in listeners:
            channel.put(message)

    def close(self) -> None:
        """Release every listener so its thread can finish."""
        with self._lock:
            listeners = list(self._listeners)
            self._listeners.clear()
        for channel in listeners:
            channel.put(None)


class _DeckServer(ThreadingHTTPServer):
    """A threading HTTP server that carries the reload hub."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: Any, *, hub: _ReloadHub) -> None:
        """Bind the server.

        Args:
            address: The host and port to listen on.
            handler: The request handler class or factory.
            hub: The reload hub open pages subscribe to.
        """
        self.hub = hub
        super().__init__(address, handler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Swallow the noise a browser makes when it walks away from a request.

        A page that navigates, reloads, or drops an iframe mid-download leaves
        the transfer half-finished, and the stock handler prints a traceback for
        it. Anything else is still worth seeing.

        Args:
            request: The socket the request came in on.
            client_address: The address it came from.
        """
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class _DeckHandler(SimpleHTTPRequestHandler):
    """Serve the built deck, plus the reload event stream."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # the name is fixed by http.server
        """Answer a GET request, handling the reload stream itself."""
        if self.path.split("?", 1)[0] == RELOAD_PATH:
            self._stream_reloads()
            return
        try:
            super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            # The page gave up on the file part-way through; there is nobody
            # left to send an error to, so just let the connection go.
            self.close_connection = True

    def _stream_reloads(self) -> None:
        """Hold the connection open and forward reload events to the page."""
        hub = cast(_DeckServer, self.server).hub
        channel = hub.listen()
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b": mkdeck connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    message = channel.get(timeout=HEARTBEAT_SECONDS)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                else:
                    if message is None:
                        return
                    self.wfile.write(f"data: {message}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        finally:
            hub.drop(channel)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the name is fixed by http.server.
        """Stay quiet; the deck's own output is the interesting part.

        Args:
            format: The printf-style format string.
            args: The values for it.
        """


def inject_reload(index: Path) -> None:
    """Add the live-reload client to a built page.

    Args:
        index: The built ``index.html``.
    """
    if not index.is_file():
        return
    html = index.read_text(encoding="utf-8")
    if RELOAD_PATH in html:
        return
    if "</body>" in html:
        html = html.replace("</body>", f"{RELOAD_SNIPPET}</body>", 1)
    else:
        html += RELOAD_SNIPPET
    index.write_text(html, encoding="utf-8")


def _watch_and_rebuild(
    rebuild: Rebuild,
    root: Path,
    *,
    paths: list[Path],
    hub: _ReloadHub,
    stop: threading.Event,
) -> None:
    """Rebuild the deck whenever a watched path changes.

    A failed rebuild prints its error and leaves the last good build in place.

    Args:
        rebuild: Callable that writes the deck into the given folder.
        root: The folder being served.
        paths: The paths to watch.
        hub: The reload hub to notify after a successful rebuild.
        stop: Event that ends the watch.
    """
    for _changes in watch(*paths, stop_event=stop):
        try:
            rebuild(root)
        except DeckError as exc:
            print(f"mkdeck: {exc}", file=sys.stderr)
            print("mkdeck: keeping the last good build.", file=sys.stderr)
            continue
        except Exception as exc:
            print(f"mkdeck: rebuild failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
            print("mkdeck: keeping the last good build.", file=sys.stderr)
            continue
        inject_reload(root / "index.html")
        print("mkdeck: rebuilt")
        hub.notify("reload")


def _run(
    rebuild: Rebuild,
    *,
    paths: list[Path],
    host: str,
    port: int,
    open_browser: bool,
    reload: bool,
) -> None:
    """Build once, then serve until interrupted.

    Args:
        rebuild: Callable that writes the deck into the given folder.
        paths: The paths to watch, empty to serve a fixed build.
        host: The interface to bind.
        port: The port to bind.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch the source and push reloads.

    Raises:
        DeckError: If the first build fails or the port is taken.
    """
    root = Path(tempfile.mkdtemp(prefix="mkdeck-"))
    live = reload and bool(paths)
    try:
        rebuild(root)
        if live:
            inject_reload(root / "index.html")
        hub = _ReloadHub()
        try:
            server = _DeckServer((host, port), partial(_DeckHandler, directory=str(root)), hub=hub)
        except OSError as exc:
            raise DeckError(f"Cannot serve on {host}:{port}: {exc}. Choose another port with --port.") from exc
        # The watcher goes up before the URL is printed, so an edit made the moment
        # the deck opens is not missed while the file watches are still being set up.
        stop = threading.Event()
        if live:
            watcher = threading.Thread(
                target=_watch_and_rebuild,
                args=(rebuild, root),
                kwargs={"paths": paths, "hub": hub, "stop": stop},
                daemon=True,
            )
            watcher.start()
        url = f"http://{host}:{port}/"
        print(f"Slide deck: {url}")
        print("Press Ctrl-C to stop.")
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()
        finally:
            stop.set()
            hub.close()
            server.shutdown()
            server.server_close()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def serve_deck(
    deck: Deck,
    *,
    config: DeckConfig | None = None,
    source: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 5020,
    open_browser: bool = False,
    reload: bool = True,
) -> None:
    """Serve a deck built in Python.

    Args:
        deck: The deck to serve.
        config: The merged deck configuration.
        source: The folder holding the deck's assets; it is watched when given.
        host: The interface to bind.
        port: The port to bind.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch ``source`` and push reloads.

    Raises:
        DeckError: If the deck cannot be rendered or the port is taken.
    """

    def rebuild(root: Path) -> None:
        build_deck(deck, root, config=config, source=source)

    paths = [Path(source)] if source is not None else []
    _run(rebuild, paths=paths, host=host, port=port, open_browser=open_browser, reload=reload)


def serve_source(
    path: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 5020,
    open_browser: bool = False,
    reload: bool = True,
) -> None:
    """Serve a deck from disk, re-reading it whenever its folder changes.

    Args:
        path: A Markdown file, or a folder holding ``deck.md`` or ``slides.md``.
        host: The interface to bind.
        port: The port to bind.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch the source folder and push reloads.

    Raises:
        DeckError: If the deck cannot be loaded or the port is taken.
    """
    first = load_source(Path(path))

    def rebuild(root: Path) -> None:
        loaded = load_source(Path(path))
        build_deck(loaded.deck, root, config=loaded.config, source=loaded.directory)

    _run(
        rebuild,
        paths=[first.directory],
        host=host,
        port=port,
        open_browser=open_browser,
        reload=reload,
    )
