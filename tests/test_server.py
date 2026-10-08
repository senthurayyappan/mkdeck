"""The development server: what it serves, what it tells the page, and how it
ends.
"""

import contextlib
import http.client
import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import pytest
from watchfiles import Change

import mkdeck.server as server_module
import mkdeck.source as source_module
from mkdeck import Deck, DeckError, DeckWarning, Slide, load_source
from mkdeck.render import EDIT_PATH, EXPORT_PATH, RELOAD_PATH
from mkdeck.server import (
    _DeckHandler,
    _DeckServer,
    _frame,
    _ignoring_outputs,
    _is_loopback,
    _ReloadHub,
    _shown_host,
    _wait_for_stop,
    dev_server,
)

MARKER = "<!--live-->"


def _server(tmp_path: Path) -> _DeckServer:
    return _DeckServer(
        ("127.0.0.1", 0), _DeckHandler, hub=_ReloadHub(), root=tmp_path
    )


class Builds:
    """A stand-in for the deck build: it writes a small deck and can be told
    to fail.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.version = "1"
        self.fail: str | None = None
        self.pause = 0.0

    def __call__(self, root: Path, live: bool) -> None:
        self.calls += 1
        if self.fail is not None:
            raise DeckError(self.fail)
        (root / "sub").mkdir()
        (root / "index.html").write_text(
            f"<html>build {self.version}{MARKER if live else ''}</html>"
        )
        time.sleep(self.pause)
        (root / f"only-{self.version}.txt").write_text("x")


def get(url: str, path: str = "/") -> tuple[int, str]:
    try:
        with urllib.request.urlopen(
            url.rstrip("/") + path, timeout=5
        ) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def wait_for(condition, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError("timed out")


class Stream:
    """The event stream of a running server, read on a thread so a test can
    wait on it.
    """

    def __init__(self, url: str) -> None:
        self.lines: queue.Queue[str] = queue.Queue()
        host, port = url.removeprefix("http://").rstrip("/").split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=10)
        self.sock.sendall(
            f"GET {RELOAD_PATH} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode()
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            for raw in self.sock.makefile("rb"):
                self.lines.put(raw.decode().rstrip("\r\n"))
        except (OSError, ValueError):
            pass

    def until(self, wanted: str, timeout: float = 10.0) -> list[str]:
        seen: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=0.2)
            except queue.Empty:
                continue
            seen.append(line)
            if line == wanted:
                return seen
        raise AssertionError(f"never saw {wanted!r}; saw {seen}")

    def drain(self) -> None:
        while not self.lines.empty():
            self.lines.get_nowait()

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()


def wait_until_quiet(
    builds: Builds, seconds: float = 1.5, timeout: float = 20.0
) -> int:
    """Wait until no rebuild has happened for `seconds`, and return the
    number of builds so far.

    macOS replays the events of a test's own setup writes, and how late they
    arrive depends on the load on the machine. Counting from a quiet moment
    keeps a late replay out of the count.
    """
    deadline = time.monotonic() + timeout
    seen, since = builds.calls, time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(0.05)
        if builds.calls != seen:
            seen, since = builds.calls, time.monotonic()
        elif time.monotonic() - since >= seconds:
            return seen
    raise AssertionError("the rebuilds never stopped")


def settle(*streams: Stream) -> None:
    """Let the file watch report the files the test has just made, then
    forget them.

    The watch is already live when `dev_server` yields; what is left to wait out
    is the operating system replaying the writes the test made a moment before
    it started.
    """
    time.sleep(1.0)
    for stream in streams:
        stream.drain()


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "deck").mkdir()
    (tmp_path / "deck" / "deck.md").write_text("---\ntitle: T\n---\n\nHi.\n")
    return tmp_path / "deck"


def test_a_page_that_walks_away_mid_download_is_not_a_traceback(
    tmp_path, capsys
) -> None:
    server = _server(tmp_path)
    try:
        try:
            raise ConnectionResetError(104, "Connection reset by peer")
        except ConnectionResetError:
            server.handle_error(server.socket, ("127.0.0.1", 33136))
    finally:
        server.server_close()
    assert capsys.readouterr().err == ""


def test_a_real_failure_still_shows(tmp_path, capsys) -> None:
    server = _server(tmp_path)
    try:
        try:
            raise ValueError("the deck is on fire")
        except ValueError:
            server.handle_error(server.socket, ("127.0.0.1", 33136))
    finally:
        server.server_close()
    assert "the deck is on fire" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("0.0.0.0", False),
        ("192.168.1.5", False),
        ("deck.example.org", False),
    ],
)
def test_only_a_loopback_host_is_local(host: str, loopback: bool) -> None:
    assert _is_loopback(host) is loopback


def test_an_event_is_framed_line_by_line() -> None:
    assert _frame("reload", "") == b"event: reload\ndata: \n\n"
    assert (
        _frame("deck-error", "one\ntwo")
        == b"event: deck-error\ndata: one\ndata: two\n\n"
    )


def test_a_page_that_connects_during_a_failure_is_told_at_once() -> None:
    hub = _ReloadHub()
    hub.publish("deck-error", "the table has no columns")
    late = hub.listen()
    assert late.get_nowait() == ("deck-error", "the table has no columns")
    hub.publish("reload")
    assert hub.listen().empty()


def test_the_hub_releases_its_listeners_on_close() -> None:
    hub = _ReloadHub()
    channel = hub.listen()
    hub.close()
    assert channel.get_nowait() is None
    hub.publish("reload")
    assert channel.empty()


def test_the_server_serves_the_deck_and_the_reload_client_is_part_of_it(
    folder,
) -> None:
    builds = Builds()
    with dev_server(builds, watch_paths=[folder], port=0) as url:
        status, body = get(url)
        assert status == 200
        assert body == f"<html>build 1{MARKER}</html>"
        assert get(url, "/only-1.txt") == (200, "x")
        assert get(url, "/nothing.html")[0] == 404


def test_a_folder_is_not_listed(folder) -> None:
    with dev_server(Builds(), watch_paths=[folder], port=0) as url:
        status, body = get(url, "/sub/")
        assert status == 404
        assert "only-1.txt" not in body
        assert get(url, "/sub")[0] in {404, 301}


def test_a_fixed_build_has_no_reload_client_and_no_watcher(folder) -> None:
    builds = Builds()
    with dev_server(builds, watch_paths=[folder], port=0, reload=False) as url:
        assert MARKER not in get(url)[1]
        (folder / "deck.md").write_text("changed")
        time.sleep(0.8)
        assert builds.calls == 1
    with dev_server(builds, watch_paths=[], port=0) as url:
        assert MARKER not in get(url)[1]


def test_a_change_to_the_source_rebuilds_and_tells_the_page(folder) -> None:
    builds = Builds()
    with dev_server(builds, watch_paths=[folder], port=0) as url:
        stream = Stream(url)
        stream.until(": mkdeck connected")
        settle(stream)
        builds.version = "2"
        (folder / "deck.md").write_text("changed")
        assert stream.until("event: reload")[-1] == "event: reload"
        assert "build 2" in get(url)[1]
        assert MARKER in get(url)[1]
        assert get(url, "/only-2.txt")[0] == 200
        assert (
            get(url, "/only-1.txt")[0] == 404
        )  # a file the new build no longer writes is gone
        stream.close()


def slow_watch(monkeypatch, delay: float) -> None:
    """Make the file watch take `delay` seconds to come up, as it can on a
    busy machine or a big folder.
    """
    real = server_module.watch

    def watch(*args, **kwargs):
        time.sleep(delay)
        yield from real(*args, **kwargs)

    monkeypatch.setattr(server_module, "watch", watch)


def test_an_edit_made_the_moment_the_url_is_handed_out_is_not_missed(
    folder, monkeypatch
) -> None:
    slow_watch(monkeypatch, 0.3)
    seen: list[str] = []

    def build(root: Path, live: bool) -> None:
        seen.append((folder / "deck.md").read_text(encoding="utf-8"))
        (root / "index.html").write_text("deck")

    with dev_server(build, watch_paths=[folder], port=0):
        (folder / "deck.md").write_text("edited straight away")
        wait_for(lambda: len(seen) > 1 and seen[-1] == "edited straight away")


def test_a_watcher_that_cannot_start_is_a_deck_error_and_leaves_nothing_behind(
    folder, monkeypatch
) -> None:
    made: list[str] = []
    real = server_module.tempfile.mkdtemp
    monkeypatch.setattr(
        server_module.tempfile,
        "mkdtemp",
        lambda **kw: made.append(real(**kw)) or made[-1],
    )

    def watch(*args, **kwargs):
        raise OSError("too many open files")
        yield set()

    monkeypatch.setattr(server_module, "watch", watch)
    threads = threading.active_count()
    with (
        pytest.raises(
            DeckError, match="file watcher could not start: too many open files"
        ),
        dev_server(Builds(), watch_paths=[folder], port=0),
    ):
        pytest.fail("the block must not run")
    assert not Path(made[0]).exists()
    assert threading.active_count() == threads


def test_a_folder_that_is_not_there_cannot_be_watched(tmp_path) -> None:
    with (
        pytest.raises(DeckError, match="file watcher could not start"),
        dev_server(Builds(), watch_paths=[tmp_path / "missing"], port=0),
    ):
        pytest.fail("the block must not run")


def test_a_watcher_that_is_slow_to_start_is_a_warning_not_a_hang(
    folder, monkeypatch
) -> None:
    slow_watch(monkeypatch, 1.0)
    monkeypatch.setattr(server_module, "_WATCH_START_SECONDS", 0.1)
    started = time.monotonic()
    with (
        pytest.warns(DeckWarning, match="file watcher did not start"),
        dev_server(Builds(), watch_paths=[folder], port=0),
    ):
        assert time.monotonic() - started < 1.0


def test_a_failing_rebuild_keeps_the_last_good_deck_and_says_why(
    folder, capsys
) -> None:
    builds = Builds()
    with dev_server(builds, watch_paths=[folder], port=0) as url:
        stream = Stream(url)
        stream.until(": mkdeck connected")
        settle(stream)
        builds.fail = "slide 2: This slide holds two tables."
        (folder / "deck.md").write_text("broken")
        seen = stream.until("data: slide 2: This slide holds two tables.")
        assert "event: deck-error" in seen
        assert "build 1" in get(url)[1]  # still the last good deck
        assert "keeping the last good build" in capsys.readouterr().err

        late = Stream(
            url
        )  # a page that opens now is told about the failure too
        assert "event: deck-error" in late.until(
            "data: slide 2: This slide holds two tables."
        )
        late.close()

        builds.fail = None
        builds.version = "3"
        stream.drain()
        (folder / "deck.md").write_text("fixed")
        stream.until("event: reload")
        assert "build 3" in get(url)[1]
        stream.close()


def test_an_unexpected_failure_in_a_rebuild_is_also_reported_and_survived(
    folder,
) -> None:
    folders: list[Path] = []
    state = {"fail": False}

    def build(root: Path, live: bool) -> None:
        folders.append(root)
        if state["fail"]:
            raise RuntimeError("disk full")
        (root / "index.html").write_text("good deck")

    with dev_server(build, watch_paths=[folder], port=0) as url:
        stream = Stream(url)
        stream.until(": mkdeck connected")
        settle(stream)
        state["fail"] = True
        (folder / "deck.md").write_text("x")
        assert stream.until("data: The rebuild failed: RuntimeError: disk full")
        assert get(url)[1] == "good deck"
        assert not folders[-1].exists()  # the half-built folder is cleaned away
        stream.close()


def test_a_request_never_sees_a_half_written_deck(folder) -> None:
    builds = Builds()
    seen: list[str] = []
    stop = threading.Event()

    def hammer(url: str) -> None:
        while not stop.is_set():
            with contextlib.suppress(OSError):
                seen.append(get(url)[1])

    with dev_server(builds, watch_paths=[folder], port=0) as url:
        settle()
        builds.pause = 0.15
        thread = threading.Thread(target=hammer, args=(url,))
        thread.start()
        before = builds.calls
        for number in range(3):
            builds.version = str(number + 2)
            (folder / "deck.md").write_text(f"edit {number}")
            time.sleep(0.9)
        stop.set()
        thread.join()
    assert len(seen) > 20
    assert builds.calls >= before + 3
    assert all(
        body.startswith("<html>build ") and body.endswith(f"{MARKER}</html>")
        for body in seen
    )


def test_the_output_folders_inside_the_deck_do_not_trigger_a_rebuild(
    folder,
) -> None:
    builds = Builds()
    for name in ("site", "report"):
        (folder / name).mkdir()
    with dev_server(builds, watch_paths=[folder], port=0) as url:
        settle()
        baseline = builds.calls
        (folder / "site" / "index.html").write_text("built")
        (folder / "report" / "01.png").write_text("png")
        (folder / "deck.pdf").write_text("pdf")
        time.sleep(1.0)
        assert builds.calls == baseline
        builds.version = "2"
        (folder / "deck.md").write_text("changed")
        wait_for(lambda: "build 2" in get(url)[1])
        assert builds.calls > baseline


def test_the_server_and_its_scratch_folder_are_gone_when_the_block_ends(
    folder, monkeypatch
) -> None:
    made: list[str] = []
    real = server_module.tempfile.mkdtemp
    monkeypatch.setattr(
        server_module.tempfile,
        "mkdtemp",
        lambda **kw: made.append(real(**kw)) or made[-1],
    )
    with dev_server(Builds(), watch_paths=[folder], port=0) as url:
        port = int(url.rsplit(":", 1)[1].strip("/"))
        assert Path(made[0]).is_dir()
    assert not Path(made[0]).exists()
    with (
        pytest.raises(OSError),
        socket.create_connection(("127.0.0.1", port), timeout=1),
    ):
        pass


def test_a_failed_first_build_is_a_deck_error_and_leaves_nothing_behind(
    folder, monkeypatch
) -> None:
    made: list[str] = []
    real = server_module.tempfile.mkdtemp
    monkeypatch.setattr(
        server_module.tempfile,
        "mkdtemp",
        lambda **kw: made.append(real(**kw)) or made[-1],
    )
    builds = Builds()
    builds.fail = "the deck is broken"
    with (
        pytest.raises(DeckError, match="the deck is broken"),
        dev_server(builds, watch_paths=[folder], port=0),
    ):
        pytest.fail("the block must not run")
    assert not Path(made[0]).exists()


def test_a_taken_port_is_a_deck_error(folder) -> None:
    with dev_server(Builds(), watch_paths=[], port=0) as url:
        port = int(url.rsplit(":", 1)[1].strip("/"))
        with (
            pytest.raises(
                DeckError, match=f"could not listen on 127.0.0.1:{port}"
            ),
            dev_server(Builds(), watch_paths=[], port=port),
        ):
            pytest.fail("the block must not run")


def test_a_browser_that_will_not_open_does_not_leak_the_server(
    folder, monkeypatch
) -> None:
    made: list[str] = []
    real = server_module.tempfile.mkdtemp
    monkeypatch.setattr(
        server_module.tempfile,
        "mkdtemp",
        lambda **kw: made.append(real(**kw)) or made[-1],
    )

    def broken(_url: str) -> bool:
        raise RuntimeError("no display")

    monkeypatch.setattr(webbrowser, "open", broken)
    with (
        pytest.raises(RuntimeError, match="no display"),
        dev_server(Builds(), watch_paths=[folder], port=0, open_browser=True),
    ):
        pytest.fail("the block must not run")
    assert not Path(made[0]).exists()


def test_a_browser_error_is_only_a_warning(folder, monkeypatch) -> None:
    def refused(_url: str) -> bool:
        raise webbrowser.Error("could not locate runnable browser")

    monkeypatch.setattr(webbrowser, "open", refused)
    with (
        pytest.warns(DeckWarning, match="browser could not be opened"),
        dev_server(Builds(), watch_paths=[], port=0, open_browser=True) as url,
    ):
        assert get(url)[0] == 200


def test_the_browser_is_opened_at_the_url(folder, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        webbrowser, "open", lambda url: opened.append(url) or True
    )
    with dev_server(Builds(), watch_paths=[], port=0, open_browser=True) as url:
        assert opened == [url]


def test_serving_to_the_network_is_a_warning(folder) -> None:
    with (
        pytest.warns(DeckWarning, match="0.0.0.0"),
        dev_server(Builds(), watch_paths=[], host="0.0.0.0", port=0),
    ):
        pass


def test_serving_to_this_machine_is_not(folder) -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeckWarning)
        with dev_server(Builds(), watch_paths=[], port=0):
            pass


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="os.kill(SIGTERM) ends the whole process on Windows",
)
def test_sigterm_ends_the_wait_and_gives_the_handler_back() -> None:
    before = signal.getsignal(signal.SIGTERM)
    timer = threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()
    _wait_for_stop()
    timer.join()
    assert signal.getsignal(signal.SIGTERM) == before


def test_serving_a_loaded_deck_reads_it_again_only_on_a_rebuild(
    folder, monkeypatch, tmp_path
) -> None:
    loads: list[Path] = []
    real = source_module.load_source
    monkeypatch.setattr(
        source_module,
        "load_source",
        lambda path: loads.append(Path(path)) or real(path),
    )
    builds: list = []
    monkeypatch.setattr(
        server_module, "serve", lambda build, **kwargs: builds.append(build)
    )
    load_source(folder).serve(port=0)
    (build,) = builds
    for number in range(2):
        target = tmp_path / f"out-{number}"
        target.mkdir()
        build(target, False)
        assert (target / "index.html").is_file()
    assert loads == [
        folder / "deck.md"
    ]  # the first build reuses the deck in hand; the second reads the file


def test_serve_source_serves_the_deck_built_from_disk(
    folder, monkeypatch, capsys
) -> None:
    bodies: list[str] = []

    def wait() -> None:
        url = capsys.readouterr().out.split("Slide deck: ")[1].split()[0]
        bodies.append(get(url)[1])

    monkeypatch.setattr(server_module, "_wait_for_stop", wait)
    load_source(folder).serve(port=0)
    assert 'class="reveal"' in bodies[0]
    assert (
        "EventSource" in bodies[0]
    )  # the live-reload client is rendered in, not patched in afterwards


def test_serving_a_deck_without_a_source_watches_the_current_directory(
    monkeypatch, tmp_path, capsys
) -> None:
    bodies: list[str] = []
    watched: list[list[Path]] = []
    real = server_module.dev_server

    def spy(build, **kwargs):
        watched.append(kwargs["watch_paths"])
        return real(build, **kwargs)

    def wait() -> None:
        url = capsys.readouterr().out.split("Slide deck: ")[1].split()[0]
        bodies.append(get(url)[1])

    monkeypatch.setattr(server_module, "dev_server", spy)
    monkeypatch.setattr(server_module, "_wait_for_stop", wait)
    monkeypatch.chdir(tmp_path)
    Deck(title="Runs", slides=[Slide(sentence="Hi.")]).serve(port=0)
    assert [[path.resolve() for path in paths] for paths in watched] == [
        [tmp_path.resolve()]
    ]
    assert (
        "EventSource" in bodies[0]
    )  # a deck served without a source reloads like any other
    assert "Hi." in bodies[0]


# --------------------------------------------------------------------------- #
# What the watch ignores
# --------------------------------------------------------------------------- #


def test_the_watch_ignores_what_a_build_writes_and_nothing_that_only_starts_like_it(  # noqa: E501
    tmp_path, monkeypatch
) -> None:
    """A relative watch path never matched the absolute ones watchfiles
    reports, and `site` swallowed `site-notes.md`.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "talk").mkdir()
    keep = _ignoring_outputs([Path("talk")])

    def changed(name: str) -> bool:
        return keep(Change.modified, str((tmp_path / "talk" / name).resolve()))

    for name in (
        "site/index.html",
        "site/mkdeck-assets/mkdeck.js",
        "report/slide_01.png",
        "report",
        "deck.pdf",
    ):
        assert not changed(name), name
    for name in (
        "deck.md",
        "assets/run3.html",
        "site-notes.md",
        "reports/a.html",
        "deck.pdf.bak",
        "sub/site/a.md",
    ):
        assert changed(name), name


def test_a_build_written_into_a_relative_watch_path_does_not_rebuild_the_deck(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    talk = tmp_path / "talk"
    talk.mkdir()
    builds = Builds()
    with dev_server(builds, watch_paths=[Path("talk")], port=0) as url:
        stream = Stream(url)
        stream.until(": mkdeck connected")
        settle(stream)
        before = wait_until_quiet(builds)
        (talk / "site").mkdir()
        (talk / "site" / "index.html").write_text("built")
        (talk / "report").mkdir()
        (talk / "report" / "report.txt").write_text("checked")
        (talk / "deck.pdf").write_bytes(b"%PDF")
        time.sleep(1.0)
        assert builds.calls == before
        (talk / "site-notes.md").write_text("mine")
        wait_for(lambda: builds.calls > before)
        stream.close()


# --------------------------------------------------------------------------- #
# Who may talk to the server
# --------------------------------------------------------------------------- #


def request(url: str, *, host: str | None) -> int:
    """The status of a GET whose Host header says `host`, however the URL is
    spelled.
    """
    address, port = url.removeprefix("http://").rstrip("/").split(":")
    connection = http.client.HTTPConnection(address, int(port), timeout=5)
    try:
        connection.putrequest("GET", "/", skip_host=True)
        if host is not None:
            connection.putheader("Host", host)
        connection.endheaders()
        return connection.getresponse().status
    finally:
        connection.close()


def test_a_loopback_server_answers_only_requests_that_name_this_machine(
    folder,
) -> None:
    """A page on another site can point its own domain at 127.0.0.1 and read
    the deck (DNS rebinding).
    """
    with dev_server(Builds(), watch_paths=[], port=0) as url:
        port = url.rsplit(":", 1)[1].rstrip("/")
        for host in (
            f"127.0.0.1:{port}",
            f"localhost:{port}",
            "LOCALHOST",
            f"[::1]:{port}",
            "127.0.0.2",
            None,
        ):
            assert request(url, host=host) == 200, host
        for host in (
            f"evil.example:{port}",
            "evil.example",
            f"127.0.0.1.evil.example:{port}",
            "",
            "[::1",
            "0.0.0.0",
        ):
            assert request(url, host=host) == 403, host


def test_a_server_bound_to_the_network_leaves_the_host_alone(folder) -> None:
    with (
        pytest.warns(DeckWarning, match="0.0.0.0"),
        dev_server(Builds(), watch_paths=[], host="0.0.0.0", port=0) as url,
    ):
        port = url.rsplit(":", 1)[1].rstrip("/")
        assert request(url, host=f"my-laptop.local:{port}") == 200


# --------------------------------------------------------------------------- #
# What goes wrong on the way up
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("port", [-1, 65536, 99999])
def test_a_port_out_of_range_is_a_deck_error(port) -> None:
    with (
        pytest.raises(DeckError, match="0 to 65535"),
        dev_server(Builds(), watch_paths=[], port=port),
    ):
        pytest.fail("the block must not run")


def test_a_host_that_is_not_an_address_is_not_blamed_on_the_port() -> None:
    with (
        pytest.raises(DeckError, match="--host") as caught,
        dev_server(Builds(), watch_paths=[], host="256.1.1.1", port=0),
    ):
        pytest.fail("the block must not run")
    assert "another port" not in str(caught.value)


def test_a_port_that_is_taken_says_so() -> None:
    with dev_server(Builds(), watch_paths=[], port=0) as url:
        taken = int(url.rsplit(":", 1)[1].rstrip("/"))
        with (
            pytest.raises(DeckError, match="another port"),
            dev_server(Builds(), watch_paths=[], port=taken),
        ):
            pytest.fail("the block must not run")


@pytest.mark.parametrize(
    ("host", "shown"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("localhost", "localhost"),
        ("0.0.0.0", "localhost"),
        ("::", "localhost"),
        ("::1", "[::1]"),
    ],
)
def test_the_url_names_a_host_a_browser_can_open(host: str, shown: str) -> None:
    assert _shown_host(host) == shown


def test_serving_to_every_interface_hands_out_a_url_that_opens() -> None:
    with (
        pytest.warns(DeckWarning, match="0.0.0.0"),
        dev_server(Builds(), watch_paths=[], host="0.0.0.0", port=0) as url,
    ):
        assert url.startswith("http://localhost:")
        assert get(url)[0] == 200


def test_the_address_is_printed_the_moment_the_server_is_up(
    folder, tmp_path
) -> None:
    """A pipe to a log or an editor terminal buffers stdout, and the URL used
    to arrive on exit.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "PYTHONUNBUFFERED"
    }
    errors = tmp_path / "stderr.txt"
    with errors.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mkdeck",
                "serve",
                str(folder),
                "--port",
                "0",
            ],
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            env=env,
        )
    output = process.stdout
    assert output is not None
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(
        target=lambda: lines.put(output.readline()), daemon=True
    ).start()
    try:
        try:
            first = lines.get(timeout=90)
        except queue.Empty:
            pytest.fail(
                f"No address after 90 s (exit code {process.poll()}); stderr "
                f"was:\n{errors.read_text('utf-8')}"
            )
        assert first.startswith("Slide deck: http://127.0.0.1:")
    finally:
        process.kill()
        process.wait()
        output.close()


def post_edit(
    url: str, body: dict, *, token: str | None, origin: str | None = None
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Mkdeck-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    request = urllib.request.Request(
        url.rstrip("/") + EDIT_PATH,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


@contextlib.contextmanager
def editable(folder: Path, **kwargs):
    deck_md = folder / "deck.md"
    deck_md.write_text("---\ntitle: T\n---\n\n# Hello\n\nHi.\n")
    with dev_server(
        Builds(),
        watch_paths=[folder],
        port=0,
        edit_file=deck_md,
        **kwargs,
    ) as url:
        yield url, deck_md


def test_an_edit_from_the_page_is_written_into_the_deck_file(folder) -> None:
    with editable(folder) as (url, deck_md):
        status, body = get(url, EDIT_PATH)
        assert status == 200
        token = json.loads(body)["token"]
        edit = {"slide": 0, "key": "title", "expected": "Hello", "text": "Hey"}
        assert post_edit(url, edit, token=token, origin=url.rstrip("/")) == (
            200,
            {"saved": True},
        )
        assert "# Hey\n" in deck_md.read_text()
        status, body = post_edit(url, edit, token=token)
        assert status == 409  # the page still shows "Hello"
        assert "changed" in body["error"]


def test_an_edit_needs_the_token_and_this_origin(folder) -> None:
    with editable(folder) as (url, deck_md):
        edit = {"slide": 0, "key": "title", "expected": "Hello", "text": "x"}
        assert post_edit(url, edit, token=None)[0] == 403
        assert post_edit(url, edit, token="guess")[0] == 403
        token = json.loads(get(url, EDIT_PATH)[1])["token"]
        assert (
            post_edit(url, edit, token=token, origin="http://evil.test")[0]
            == 403
        )
        assert "# Hello\n" in deck_md.read_text()


def test_a_malformed_edit_is_refused(folder) -> None:
    with editable(folder) as (url, _):
        token = json.loads(get(url, EDIT_PATH)[1])["token"]
        assert post_edit(url, {"slide": "0"}, token=token)[0] == 400
        bad = {"slide": 0, "key": "notes", "expected": "", "text": ""}
        assert post_edit(url, bad, token=token)[0] == 422
        bad["slide"] = 5
        assert post_edit(url, bad, token=token)[0] == 409


def test_a_deck_served_without_reloads_cannot_be_edited(folder) -> None:
    with editable(folder, reload=False) as (url, _):
        assert get(url, EDIT_PATH)[0] == 404
        assert post_edit(url, {}, token="x")[0] == 404


def test_a_deck_served_to_the_network_cannot_be_edited(tmp_path) -> None:
    deck_md = tmp_path / "deck.md"
    deck_md.write_text("# Hi\n")
    server = _DeckServer(
        ("0.0.0.0", 0),
        _DeckHandler,
        hub=_ReloadHub(),
        root=tmp_path,
        edit_file=deck_md,
    )
    try:
        assert server.edit_file is None
    finally:
        server.server_close()


def test_a_served_source_deck_carries_the_editor(folder, monkeypatch, capsys):
    bodies: list[str] = []

    def wait() -> None:
        url = capsys.readouterr().out.split("Slide deck: ")[1].split()[0]
        bodies.append(get(url)[1])
        bodies.append(get(url, "/mkdeck-assets/mkdeck-edit.js")[1])

    monkeypatch.setattr(server_module, "_wait_for_stop", wait)
    load_source(folder).serve(port=0)
    page, client = bodies
    assert f'data-endpoint="{EDIT_PATH}"' in page
    assert 'data-mkd-slide="0"' in page
    assert "X-Mkdeck-Token" in client


def test_the_page_reads_a_slide_with_the_token_and_saves_it_whole(
    folder,
) -> None:
    with editable(folder) as (url, deck_md):
        token = json.loads(get(url, EDIT_PATH)[1])["token"]
        assert get(url, EDIT_PATH + "?slide=0")[0] == 403  # no token
        request = urllib.request.Request(
            url.rstrip("/") + EDIT_PATH + "?slide=0",
            headers={"X-Mkdeck-Token": token},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            source = json.loads(response.read())["text"]
        assert source == "# Hello\n\nHi."
        edit = {"slide": 0, "key": "slide", "expected": source}
        edit["text"] = "# Hello\n\n- one\n- two"
        assert post_edit(url, edit, token=token)[0] == 200
        assert deck_md.read_text().endswith("# Hello\n\n- one\n- two\n")


def test_the_deck_downloads_as_one_html_file_with_its_saved_edits(
    folder,
) -> None:
    with editable(folder) as (url, deck_md):
        token = json.loads(get(url, EDIT_PATH)[1])["token"]
        assert get(url, EXPORT_PATH)[0] == 403  # no token
        deck_md.write_text("---\ntitle: T\n---\n\n# Saved edit\n\nHi.\n")
        request = urllib.request.Request(
            url.rstrip("/") + EXPORT_PATH, headers={"X-Mkdeck-Token": token}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            disposition = response.headers["Content-Disposition"]
            page = response.read().decode()
        assert disposition == 'attachment; filename="deck.html"'
        assert "Saved edit" in page
        assert 'src="mkdeck-assets/' not in page  # everything is inlined
        assert 'href="mkdeck-assets/' not in page
        assert "data-mkd-edit" not in page and "EventSource" not in page


def test_a_deck_that_does_not_parse_is_not_exported(folder) -> None:
    with editable(folder) as (url, deck_md):
        token = json.loads(get(url, EDIT_PATH)[1])["token"]
        deck_md.write_text("---\ntitle: [unclosed\n---\n")
        request = urllib.request.Request(
            url.rstrip("/") + EXPORT_PATH, headers={"X-Mkdeck-Token": token}
        )
        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=30)
        assert raised.value.code == 422


def test_every_file_is_checked_again_before_the_browser_reuses_it(
    folder,
) -> None:
    with dev_server(Builds(), watch_paths=[folder], port=0) as url:
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.headers["Cache-Control"] == "no-cache"
        with urllib.request.urlopen(url + "only-1.txt", timeout=5) as response:
            assert response.headers["Cache-Control"] == "no-cache"
