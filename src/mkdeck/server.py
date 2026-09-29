"""Serve a deck and rebuild it when its source changes.

The page is told to reload over a server-sent-event stream rather than a
websocket: the client side is a few lines of `EventSource` and the dependency
list stays short. Every rebuild is written into a fresh folder and the server switches
to it when it is complete, so a request never sees a half-written deck, and a rebuild
that fails leaves the last good deck being served.
"""

import ipaddress
import itertools
import queue
import shutil
import signal
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from watchfiles import DefaultFilter, watch

from mkdeck._messages import warn_deck
from mkdeck.build import build_deck
from mkdeck.errors import DeckError
from mkdeck.model import Deck
from mkdeck.render import RELOAD_PATH
from mkdeck.source import DeckSource, load_source

__all__ = ["HEARTBEAT_SECONDS", "RELOAD_PATH", "dev_server", "serve_deck", "serve_source"]

HEARTBEAT_SECONDS = 15.0
"""How often a quiet stream sends a comment, so proxies keep it open."""

Rebuild = Callable[[Path, bool], None]
"""Writes the deck into an empty folder that exists; the flag says whether to add the live-reload client."""

_OUTPUTS = ("site", "report", "deck.pdf")
"""What `mkdeck build`, `check` and `export` write by default; a change there is not a change to the deck."""

_DEBOUNCE_MS = 250

_WATCH_POLL_MS = 100
"""How often the watcher wakes with nothing to report; its first wake-up is the proof that the watch is live."""

_WATCH_START_SECONDS = 10.0
"""How long `dev_server` waits for the watch to come up before it serves without knowing."""


class _ReloadHub:
    """Fan rebuild events out to every open page."""

    def __init__(self) -> None:
        """Start with no listeners and no failed rebuild."""
        self._lock = threading.Lock()
        self._listeners: set[queue.SimpleQueue[tuple[str, str] | None]] = set()
        self._error: str | None = None

    def listen(self) -> "queue.SimpleQueue[tuple[str, str] | None]":
        """Register a listener.

        A page that connects while the last rebuild is failing is told so at once.

        Returns:
            The queue the listener reads `(event, data)` messages from.
        """
        channel: queue.SimpleQueue[tuple[str, str] | None] = queue.SimpleQueue()
        with self._lock:
            self._listeners.add(channel)
            if self._error is not None:
                channel.put(("deck-error", self._error))
        return channel

    def drop(self, channel: "queue.SimpleQueue[tuple[str, str] | None]") -> None:
        """Remove a listener.

        Args:
            channel: The queue returned by `listen`.
        """
        with self._lock:
            self._listeners.discard(channel)

    def publish(self, event: str, data: str = "") -> None:
        """Send an event to every listener.

        Args:
            event: `reload` after a rebuild, or `deck-error` after one that failed.
            data: The event payload; the error message for `deck-error`.
        """
        with self._lock:
            self._error = data if event == "deck-error" else None
            listeners = list(self._listeners)
        for channel in listeners:
            channel.put((event, data))

    def close(self) -> None:
        """Release every listener so its thread can finish."""
        with self._lock:
            listeners = list(self._listeners)
            self._listeners.clear()
        for channel in listeners:
            channel.put(None)


def _frame(event: str, data: str) -> bytes:
    """Write one server-sent event.

    Args:
        event: The event name.
        data: The payload; each line of it becomes a `data:` line.

    Returns:
        The bytes of the frame.
    """
    lines = "".join(f"data: {line}\n" for line in data.splitlines() or [""])
    return f"event: {event}\n{lines}\n".encode()


class _DeckServer(ThreadingHTTPServer):
    """A threading HTTP server that carries the reload hub and the folder it serves."""

    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"  # on Windows the option lets a second server steal the port

    def __init__(self, address: tuple[str, int], handler: Any, *, hub: _ReloadHub, root: Path) -> None:
        """Bind the server.

        Args:
            address: The host and port to listen on.
            handler: The request handler class or factory.
            hub: The reload hub open pages subscribe to.
            root: The folder to serve; assign a new one to switch decks.
        """
        self.hub = hub
        self.root = root
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
        if isinstance(sys.exc_info()[1], ConnectionError | TimeoutError):
            return
        super().handle_error(request, client_address)


class _DeckHandler(SimpleHTTPRequestHandler):
    """Serve the built deck, plus the reload event stream."""

    protocol_version = "HTTP/1.1"

    def translate_path(self, path: str) -> str:
        """Map a URL to a file of the deck being served right now.

        Args:
            path: The path of the request.

        Returns:
            The file path.
        """
        self.directory = str(cast(_DeckServer, self.server).root)
        return super().translate_path(path)

    def list_directory(self, path: Any) -> None:  # the name is fixed by http.server
        """Refuse to list a folder; the deck is served, not browsed.

        Args:
            path: The folder that was asked for.
        """
        self.send_error(404, "File not found")

    def do_GET(self) -> None:  # the name is fixed by http.server
        """Answer a GET request, handling the reload stream itself."""
        if self.path.split("?", 1)[0] == RELOAD_PATH:
            self._stream_reloads()
            return
        try:
            super().do_GET()
        except ConnectionError:
            # The page gave up on the file part-way through; there is nobody
            # left to send an error to, so just let the connection go.
            self.close_connection = True

    def _stream_reloads(self) -> None:
        """Hold the connection open and forward rebuild events to the page."""
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
                    self.wfile.write(_frame(*message))
                self.wfile.flush()
        except OSError:
            return
        finally:
            hub.drop(channel)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the name is fixed by http.server.
        """Stay quiet; the deck's own output is the interesting part.

        Args:
            format: The printf-style format string.
            args: The values for it.
        """


def _is_loopback(host: str) -> bool:
    """Say whether a host name or address reaches only this machine.

    Args:
        host: The interface the server binds.

    Returns:
        True for `localhost` and for a loopback address.
    """
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _watch_changes(
    paths: Sequence[Path],
    refresh: Callable[[], None],
    stop: threading.Event,
    live: threading.Event,
    failures: list[Exception],
) -> None:
    """Call `refresh` whenever something in the watched folders changes.

    `watchfiles` sets the operating system watch up when the first iteration begins, and it
    offers no signal for that. With `yield_on_timeout` it gives one anyway: an iteration ends
    with no changes when the wait times out, and that can only happen once the watch exists.

    Args:
        paths: The folders to watch.
        refresh: The rebuild, called once per batch of changes.
        stop: Event that ends the watch.
        live: Set as soon as the watch is up, or as soon as it is known that it never will be.
        failures: Where the error goes if the watch fails; read after `live` is set.
    """
    ignored = DefaultFilter(ignore_paths=[path / name for path in paths for name in _OUTPUTS])
    try:
        for changes in watch(
            *paths,
            stop_event=stop,
            watch_filter=ignored,
            debounce=_DEBOUNCE_MS,
            rust_timeout=_WATCH_POLL_MS,
            yield_on_timeout=True,
            raise_interrupt=False,
        ):
            live.set()
            if changes:
                refresh()
    except Exception as exc:
        if live.is_set():  # nobody is waiting for the start any more, so say so here
            warn_deck(f"The file watcher stopped: {exc}. Changes to the deck no longer rebuild it.")
        failures.append(exc)
    finally:
        live.set()


@contextmanager
def dev_server(
    build: Rebuild,
    *,
    watch_paths: Sequence[Path],
    host: str = "127.0.0.1",
    port: int = 5020,
    open_browser: bool = False,
    reload: bool = True,
) -> Iterator[str]:
    """Build a deck, serve it in the background, and rebuild it when its source changes.

    The deck is built into a folder of its own each time and the server switches to it
    only once it is complete. A rebuild that fails leaves the last good deck in place and
    tells every open page. Everything is torn down when the block ends, even on an error.

    Args:
        build: Writes the deck into an empty folder that exists; called for the first build and for
            every rebuild.
        watch_paths: The folders to watch, empty to serve a fixed build.
        host: The interface to bind. Anything but a loopback address serves the deck
            to the network, and warns.
        port: The port to bind; 0 picks a free one.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch `watch_paths` and push reloads.

    Yields:
        The URL the deck is served at.

    Raises:
        DeckError: If the first build fails, the port is taken, or the files cannot be watched.
    """
    live = reload and bool(watch_paths)
    scratch = Path(tempfile.mkdtemp(prefix="mkdeck-"))
    hub = _ReloadHub()
    stop = threading.Event()
    counter = itertools.count()
    retired: list[Path] = []
    threads: list[threading.Thread] = []
    watching = threading.Event()
    watch_failures: list[Exception] = []
    server: _DeckServer | None = None

    def make() -> Path:
        folder = scratch / f"build-{next(counter)}"
        folder.mkdir()
        try:
            build(folder, live)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return folder

    def refresh() -> None:
        try:
            folder = make()
        except DeckError as exc:
            message = str(exc)
        except Exception as exc:
            message = f"The rebuild failed: {exc.__class__.__name__}: {exc}"
        else:
            assert server is not None  # the watcher starts after the server exists
            retired.append(server.root)
            server.root = folder  # one assignment: a request sees the old deck or the new one, never a mix
            while len(retired) > 1:  # a request that started before the switch may still be reading the last one
                shutil.rmtree(retired.pop(0), ignore_errors=True)
            print("mkdeck: rebuilt")
            hub.publish("reload")
            return
        print(f"mkdeck: {message}", file=sys.stderr)
        print("mkdeck: keeping the last good build.", file=sys.stderr)
        hub.publish("deck-error", message)

    try:
        first = make()
        if not _is_loopback(host):
            warn_deck(
                f"The server is bound to {host}, so anyone who can reach this machine can read the deck and everything it embeds."
            )
        try:
            server = _DeckServer((host, port), _DeckHandler, hub=hub, root=first)
        except OSError as exc:
            raise DeckError(
                f"The server could not listen on {host}:{port}: {exc}. Choose another port with --port."
            ) from exc
        threads.append(threading.Thread(target=server.serve_forever, daemon=True))
        if live:
            threads.append(
                threading.Thread(
                    target=_watch_changes, args=(watch_paths, refresh, stop, watching, watch_failures), daemon=True
                )
            )
        for thread in threads:
            thread.start()
        if live:
            # The URL is handed out only once the watch is live: an edit made the moment the
            # deck opens would otherwise land before the operating system is watching.
            if not watching.wait(_WATCH_START_SECONDS):
                warn_deck(
                    f"The file watcher did not start within {_WATCH_START_SECONDS:.0f} seconds, "
                    "so an edit made now may not reload the page."
                )
            elif watch_failures:
                raise DeckError(f"The file watcher could not start: {watch_failures[0]}") from watch_failures[0]
        url = f"http://{host}:{server.server_port}/"
        if open_browser:
            try:
                webbrowser.open(url)
            except webbrowser.Error as exc:
                warn_deck(f"The browser could not be opened: {exc}.")
        yield url
    finally:
        stop.set()
        hub.close()
        if server is not None:
            if threads:  # serve_forever runs, and shutdown() would wait for it forever if it did not
                server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
        shutil.rmtree(scratch, ignore_errors=True)


def _wait_for_stop() -> None:
    """Block until Ctrl-C or SIGTERM, so a stopped server cleans up after itself."""
    stop = threading.Event()
    try:
        previous = signal.signal(signal.SIGTERM, lambda *_: stop.set())
    except ValueError:  # only the main thread may install a handler
        previous = None
    try:
        while not stop.wait(0.5):  # a timeout, so that Ctrl-C is delivered promptly on every platform
            pass
    except KeyboardInterrupt:
        print()
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def _serve(
    build: Rebuild, *, watch_paths: Sequence[Path], host: str, port: int, open_browser: bool, reload: bool
) -> None:
    """Serve until interrupted.

    Args:
        build: Writes the deck into an empty folder.
        watch_paths: The folders to watch, empty to serve a fixed build.
        host: The interface to bind.
        port: The port to bind.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch the source and push reloads.
    """
    with dev_server(
        build, watch_paths=watch_paths, host=host, port=port, open_browser=open_browser, reload=reload
    ) as url:
        print(f"Slide deck: {url}")
        print("Press Ctrl-C to stop.")
        _wait_for_stop()


def serve_deck(
    deck: Deck,
    *,
    source: Path | str | None = None,
    host: str = "127.0.0.1",
    port: int = 5020,
    open_browser: bool = False,
    reload: bool = True,
) -> None:
    """Serve a deck built in Python; `Deck.serve` is the public way to call this.

    Args:
        deck: The deck to serve.
        source: The folder holding the deck's assets; it is watched when given.
        host: The interface to bind.
        port: The port to bind.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch `source` and push reloads.

    Raises:
        DeckError: If the deck cannot be rendered or the port is taken.
    """
    folder = Path(source) if source is not None else None

    def build(root: Path, live: bool) -> None:
        build_deck(deck, root, source=folder, live_reload=live)

    _serve(
        build,
        watch_paths=[folder] if folder is not None else [],
        host=host,
        port=port,
        open_browser=open_browser,
        reload=reload,
    )


def serve_source(
    loaded: DeckSource,
    *,
    host: str = "127.0.0.1",
    port: int = 5020,
    open_browser: bool = False,
    reload: bool = True,
) -> None:
    """Serve a deck from disk, reading it again whenever its folder changes; `DeckSource.serve` calls this.

    The deck folder is watched, apart from the folders `mkdeck build`, `check` and
    `export` write into by default (`site`, `report` and `deck.pdf`).

    Args:
        loaded: The deck to serve. Its Markdown file is read again on every rebuild.
        host: The interface to bind.
        port: The port to bind.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch the source folder and push reloads.

    Raises:
        DeckError: If the deck cannot be loaded or the port is taken.
    """
    pending: DeckSource | None = loaded

    def build(root: Path, live: bool) -> None:
        nonlocal pending
        current, pending = pending or load_source(loaded.markdown), None  # the first build reuses the deck in hand
        build_deck(current.deck, root, source=current.directory, live_reload=live)

    _serve(build, watch_paths=[loaded.directory], host=host, port=port, open_browser=open_browser, reload=reload)
