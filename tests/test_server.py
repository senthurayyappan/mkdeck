"""The development server's own behaviour, apart from the build it serves."""

from mkdeck.server import _DeckHandler, _DeckServer, _ReloadHub, inject_reload


def _server():
    return _DeckServer(("127.0.0.1", 0), _DeckHandler, hub=_ReloadHub())


def test_a_page_that_walks_away_mid_download_is_not_a_traceback(capsys):
    server = _server()
    try:
        try:
            raise ConnectionResetError(104, "Connection reset by peer")
        except ConnectionResetError:
            server.handle_error(server.socket, ("127.0.0.1", 33136))
    finally:
        server.server_close()
    assert capsys.readouterr().err == ""


def test_a_real_failure_still_shows(capsys):
    server = _server()
    try:
        try:
            raise ValueError("the deck is on fire")
        except ValueError:
            server.handle_error(server.socket, ("127.0.0.1", 33136))
    finally:
        server.server_close()
    assert "the deck is on fire" in capsys.readouterr().err


def test_the_reload_client_goes_in_once(tmp_path):
    index = tmp_path / "index.html"
    index.write_text("<html><body><p>Runs</p></body></html>")
    inject_reload(index)
    inject_reload(index)
    assert index.read_text().count("EventSource") == 1
