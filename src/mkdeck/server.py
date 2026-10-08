"""Serve a deck and rebuild it when its source changes.

The page is told to reload over a server-sent-event stream rather than a
websocket: the client side is a few lines of `EventSource` and the dependency
list stays short. Every rebuild is written into a fresh folder and the server
switches to it when it is complete, so a request never sees a half-written deck,
and a rebuild that fails leaves the last good deck being served.
"""

import ipaddress
import itertools
import json
import queue
import secrets
import shutil
import signal
import socket
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from watchfiles import Change, DefaultFilter, watch

from mkdeck._messages import warn_deck
from mkdeck.edit import EditConflictError, edit_file
from mkdeck.errors import DeckError
from mkdeck.render import EDIT_PATH, RELOAD_PATH

__all__ = ["EDIT_PATH", "RELOAD_PATH", "dev_server", "serve"]

_HEARTBEAT_SECONDS = 15.0
"""How often a quiet stream sends a comment, so proxies keep it open."""

Rebuild = Callable[[Path, bool], None]
"""Writes the deck into an empty folder that exists.

The flag says whether to add the live-reload client.
"""

_OUTPUTS = ("site", "report", "deck.pdf")
"""What `mkdeck build`, `check` and `export` write by default.

A change there is not a change to the deck.
"""

_DEBOUNCE_MS = 250

_EDIT_HEADER = "X-Mkdeck-Token"
"""The header an edit carries its token in.

A page on another site cannot set it without a preflight the server never
answers, and cannot read the token in the first place.
"""

_EDIT_MAX_BYTES = 1_000_000

_WATCH_POLL_MS = 100
"""How often the watcher wakes with nothing to report.

Its first wake-up is the proof that the watch is live.
"""

_WATCH_START_SECONDS = 10.0
"""How long `dev_server` waits for the watch to come up.

After that it serves without knowing whether the watch is live.
"""


class _ReloadHub:
    """Fan rebuild events out to every open page."""

    def __init__(self) -> None:
        """Start with no listeners and no failed rebuild."""
        self._lock = threading.Lock()
        self._listeners: set[queue.SimpleQueue[tuple[str, str] | None]] = set()
        self._error: str | None = None

    def listen(self) -> "queue.SimpleQueue[tuple[str, str] | None]":
        """Register a listener.

        A page that connects while the last rebuild is failing is told so at
        once.

        Returns:
            The queue the listener reads `(event, data)` messages from.
        """
        channel: queue.SimpleQueue[tuple[str, str] | None] = queue.SimpleQueue()
        with self._lock:
            self._listeners.add(channel)
            if self._error is not None:
                channel.put(("deck-error", self._error))
        return channel

    def drop(
        self, channel: "queue.SimpleQueue[tuple[str, str] | None]"
    ) -> None:
        """Remove a listener.

        Args:
            channel: The queue returned by `listen`.
        """
        with self._lock:
            self._listeners.discard(channel)

    def publish(self, event: str, data: str = "") -> None:
        """Send an event to every listener.

        Args:
            event: `reload` after a rebuild, or `deck-error` after one that
                failed.
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
    """A threading HTTP server.

    It carries the reload hub and the folder it serves.
    """

    daemon_threads = True
    allow_reuse_address = (
        sys.platform != "win32"
    )  # on Windows the option lets a second server steal the port

    def __init__(
        self,
        address: tuple[str, int],
        handler: Any,
        *,
        hub: _ReloadHub,
        root: Path,
        edit_file: Path | None = None,
    ) -> None:
        """Bind the server.

        Args:
            address: The host and port to listen on.
            handler: The request handler class or factory.
            hub: The reload hub open pages subscribe to.
            root: The folder to serve; assign a new one to switch decks.
            edit_file: The Markdown file the page may edit, or `None`.
        """
        self.hub = hub
        self.root = root
        self.edit_file = edit_file
        self.edit_token = secrets.token_urlsafe(24)
        self.edit_lock = threading.Lock()
        # Bound to this machine alone, only a request that names this machine is
        # answered. A
        # page on another site can otherwise point its own domain at 127.0.0.1
        # and read the deck.
        self.loopback_only = _is_loopback(address[0])
        if not self.loopback_only:  # anyone on the network could rewrite it
            self.edit_file = None
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

    def parse_request(self) -> bool:
        """Read the request.

        Refuse one whose `Host` is not this machine when that matters.

        Returns:
            True when the request is to be answered; False after an error has
            been sent.
        """
        if not super().parse_request():
            return False
        named = self.headers.get("Host")
        strict = cast(_DeckServer, self.server).loopback_only
        if strict and named is not None and not _is_loopback(_host_name(named)):
            self.send_error(403, "This server answers only to localhost")
            return False
        return True

    def translate_path(self, path: str) -> str:
        """Map a URL to a file of the deck being served right now.

        Args:
            path: The path of the request.

        Returns:
            The file path.
        """
        self.directory = str(cast(_DeckServer, self.server).root)
        return super().translate_path(path)

    def list_directory(
        self, path: Any
    ) -> None:  # the name is fixed by http.server
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
        if self.path.split("?", 1)[0] == EDIT_PATH:
            server = cast(_DeckServer, self.server)
            if server.edit_file is None or not self._same_origin():
                self._send_json(404, {"error": "This deck cannot be edited."})
            else:
                self._send_json(200, {"token": server.edit_token})
            return
        try:
            super().do_GET()
        except ConnectionError:
            # The page gave up on the file part-way through; there is nobody
            # left to send an error to, so just let the connection go.
            self.close_connection = True

    def do_POST(self) -> None:  # the name is fixed by http.server
        """Write an edit made on the page into the deck file."""
        server = cast(_DeckServer, self.server)
        if self.path.split("?", 1)[0] != EDIT_PATH or server.edit_file is None:
            self._send_json(404, {"error": "Not found."})
            return
        token = self.headers.get(_EDIT_HEADER, "")
        if not self._same_origin() or not secrets.compare_digest(
            token, server.edit_token
        ):
            self._send_json(403, {"error": "This page may not edit the deck."})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if not 0 <= length <= _EDIT_MAX_BYTES:
            self._send_json(400, {"error": "The edit has no usable length."})
            return
        try:
            edit = json.loads(self.rfile.read(length))
            slide, key = edit["slide"], edit["key"]
            expected, text = edit["expected"], edit["text"]
        except (ValueError, KeyError, TypeError):
            self._send_json(400, {"error": "The edit is not readable."})
            return
        if not (
            isinstance(slide, int)
            and all(isinstance(value, str) for value in (key, expected, text))
        ):
            self._send_json(400, {"error": "The edit is not readable."})
            return
        try:
            with server.edit_lock:
                edit_file(
                    server.edit_file,
                    slide=slide,
                    key=key,
                    expected=expected,
                    replacement=text,
                )
        except EditConflictError as error:
            self._send_json(409, {"error": error.message})
        except DeckError as error:
            self._send_json(422, {"error": error.message})
        else:
            self._send_json(200, {"saved": True})

    def _same_origin(self) -> bool:
        """Say whether the request came from a page of this server.

        A browser names the page in `Origin` on every POST and on a
        cross-site GET; a request with no `Origin` did not come from a page
        on another site.

        Returns:
            True when there is no `Origin`, or it names this server.
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return origin == f"http://{self.headers.get('Host', '')}"

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        """Answer with a small JSON document.

        Args:
            status: The HTTP status.
            body: The document.
        """
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
                    message = channel.get(timeout=_HEARTBEAT_SECONDS)
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


def _ignoring_outputs(paths: Sequence[Path]) -> Callable[[Change, str], bool]:
    """Build the filter that keeps a watch off build output.

    That output is what `build`, `check` and `export` write.

    `watchfiles` reports absolute paths and its own ignore list matches text
    prefixes, so a relative watch path would never match, and `site` would
    swallow `site-notes.md`. This compares whole path components under the
    resolved watch paths instead.

    Args:
        paths: The folders being watched.

    Returns:
        A filter that says whether a change is one to rebuild for.
    """
    outputs = [path.resolve() / name for path in paths for name in _OUTPUTS]
    default = DefaultFilter()

    def keep(change: Change, path: str) -> bool:
        location = Path(path)
        return default(change, path) and not any(
            location.is_relative_to(output) for output in outputs
        )

    return keep


def _shown_host(host: str) -> str:
    """Name the host to put in the URL of the deck.

    Args:
        host: The interface the server binds.

    Returns:
        `localhost` for an address that means every interface, which no browser
        can open; an IPv6 address in the brackets a URL needs; and the host as
        given otherwise.
    """
    if host in {"", "0.0.0.0", "::"}:
        return "localhost"
    return f"[{host}]" if ":" in host else host


def _host_name(header: str) -> str:
    """Take the host name out of a `Host` header.

    Args:
        header: The header value, such as `localhost:5020` or `[::1]:5020`.

    Returns:
        The name without the port or the brackets, lowercase, or an empty string
        when the header is not a host at all.
    """
    try:
        return urlsplit(f"//{header}").hostname or ""
    except ValueError:  # an unclosed bracket, for one
        return ""


def _watch_changes(
    paths: Sequence[Path],
    refresh: Callable[[], None],
    stop: threading.Event,
    live: threading.Event,
    failures: list[Exception],
) -> None:
    """Call `refresh` whenever something in the watched folders changes.

    `watchfiles` sets the operating system watch up when the first iteration
    begins, and it offers no signal for that. With `yield_on_timeout` it gives
    one anyway: an iteration ends with no changes when the wait times out, and
    that can only happen once the watch exists.

    Args:
        paths: The folders to watch.
        refresh: The rebuild, called once per batch of changes.
        stop: Event that ends the watch.
        live: Set as soon as the watch is up, or as soon as it is known that it
            never will be.
        failures: Where the error goes if the watch fails; read after `live` is
            set.
    """
    try:
        for changes in watch(
            *(path.resolve() for path in paths),
            stop_event=stop,
            watch_filter=_ignoring_outputs(paths),
            debounce=_DEBOUNCE_MS,
            rust_timeout=_WATCH_POLL_MS,
            yield_on_timeout=True,
            raise_interrupt=False,
        ):
            live.set()
            if changes:
                refresh()
    except Exception as exc:
        if (
            live.is_set()
        ):  # nobody is waiting for the start any more, so say so here
            warn_deck(
                f"The file watcher stopped: {exc}. Changes to the deck no "
                f"longer rebuild it."
            )
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
    edit_file: Path | None = None,
) -> Iterator[str]:
    """Build a deck and serve it in the background.

    Rebuild it when its source changes.

    The deck is built into a folder of its own each time and the server switches
    to it only once it is complete. A rebuild that fails leaves the last good
    deck in place and tells every open page. Everything is torn down when the
    block ends, even on an error.

    Args:
        build: Writes the deck into an empty folder that exists; called for the
            first build and for every rebuild.
        watch_paths: The folders to watch, empty to serve a fixed build.
        host: The interface to bind. Anything but a loopback address serves the
            deck to the network, and warns. Bound to a loopback address, the
            server answers only requests whose `Host` header names this machine.
        port: The port to bind; 0 picks a free one.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch `watch_paths` and push reloads.
        edit_file: The Markdown file the page may write text edits into, or
            `None`. Edits are refused unless the server is bound to a
            loopback address and reloads are on.

    Yields:
        The URL the deck is served at.

    Raises:
        DeckError: If the first build fails, the port is taken, or the files
            cannot be watched.
    """
    if not 0 <= port <= 65535:
        raise DeckError(
            f"The port {port} is not one a server can listen on; choose a port "
            f"from 0 to 65535 with --port."
        )
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
            assert (
                server is not None
            )  # the watcher starts after the server exists
            retired.append(server.root)
            # one assignment: a request sees the old deck or the new one, never
            # a mix
            server.root = folder
            # A request that started before the switch may still be reading
            # the last folder.
            while len(retired) > 1:
                shutil.rmtree(retired.pop(0), ignore_errors=True)
            print("mkdeck: rebuilt", flush=True)
            hub.publish("reload")
            return
        print(f"mkdeck: {message}", file=sys.stderr)
        print("mkdeck: keeping the last good build.", file=sys.stderr)
        hub.publish("deck-error", message)

    try:
        first = make()
        try:
            server = _DeckServer(
                (host, port),
                _DeckHandler,
                hub=hub,
                root=first,
                edit_file=edit_file if live else None,
            )
        except (socket.gaierror, UnicodeError) as exc:
            raise DeckError(
                f'The host "{host}" is not an address this machine can listen '
                f"on: {exc}. Choose one with --host."
            ) from exc
        except OSError as exc:
            raise DeckError(
                f"The server could not listen on {host}:{port}: {exc}. Choose "
                f"another port with --port."
            ) from exc
        if not _is_loopback(host):
            warn_deck(
                f"The server is bound to {host}, so anyone who can reach this "
                f"machine can read the deck and everything it embeds."
            )
        threads.append(
            threading.Thread(target=server.serve_forever, daemon=True)
        )
        if live:
            threads.append(
                threading.Thread(
                    target=_watch_changes,
                    args=(watch_paths, refresh, stop, watching, watch_failures),
                    daemon=True,
                )
            )
        for thread in threads:
            thread.start()
        if live:
            # The URL is handed out only once the watch is live: an edit made
            # the moment the
            # deck opens would otherwise land before the operating system is
            # watching.
            if not watching.wait(_WATCH_START_SECONDS):
                warn_deck(
                    f"The file watcher did not start within "
                    f"{_WATCH_START_SECONDS:.0f} seconds, "
                    "so an edit made now may not reload the page."
                )
            elif watch_failures:
                raise DeckError(
                    f"The file watcher could not start: {watch_failures[0]}"
                ) from watch_failures[0]
        url = f"http://{_shown_host(host)}:{server.server_port}/"
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
            # serve_forever runs, and shutdown() would wait for it forever if it
            # did not
            if threads:
                server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
        shutil.rmtree(scratch, ignore_errors=True)


def _wait_for_stop() -> None:
    """Block until Ctrl-C or SIGTERM.

    A stopped server then cleans up after itself.
    """
    stop = threading.Event()
    try:
        previous = signal.signal(signal.SIGTERM, lambda *_: stop.set())
    except ValueError:  # only the main thread may install a handler
        previous = None
    try:
        while not stop.wait(
            0.5
        ):  # a timeout, so that Ctrl-C is delivered promptly on every platform
            pass
    except KeyboardInterrupt:
        print()
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def serve(
    build: Rebuild,
    *,
    watch_paths: Sequence[Path],
    host: str = "127.0.0.1",
    port: int = 5020,
    open_browser: bool = False,
    reload: bool = True,
    edit_file: Path | None = None,
) -> None:
    """Serve a deck until interrupted.

    `Deck.serve` and `DeckSource.serve` call this.

    The folders in `watch_paths` are watched, apart from the ones `mkdeck
    build`, `check` and `export` write into by default (`site`, `report` and
    `deck.pdf`).

    Args:
        build: Writes the deck into an empty folder that exists; see
            `dev_server`.
        watch_paths: The folders to watch, empty to serve a fixed build.
        host: The interface to bind.
        port: The port to bind.
        open_browser: True to open the deck in a browser once it is up.
        reload: True to watch `watch_paths` and push reloads.
        edit_file: The Markdown file the page may write text edits into, or
            `None`; see `dev_server`.

    Raises:
        DeckError: If the deck cannot be built, the port is taken, or the files
            cannot be watched.
    """
    with dev_server(
        build,
        watch_paths=watch_paths,
        host=host,
        port=port,
        open_browser=open_browser,
        reload=reload,
        edit_file=edit_file,
    ) as url:
        print(f"Slide deck: {url}", flush=True)
        print("Press Ctrl-C to stop.", flush=True)
        _wait_for_stop()
