"""The command line: every command, and what a bad deck or a bad disk prints."""

import base64
import json
import sys
import zlib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mkdeck import Deck, DeckSource, cli, load_source
from mkdeck.cli import app

runner = CliRunner()

DECK = """---
title: Runs
date: 2026-09-18
---

Five seeds cross the wall at 0.65 m.
"""


@pytest.fixture
def deck_file(tmp_path):
    path = tmp_path / "deck.md"
    path.write_text(DECK)
    return path


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("new", "serve", "build", "check", "export", "rollout"):
        assert command in result.output


def test_version_names_the_installed_release() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    try:
        installed = version("mkdeck")
    except PackageNotFoundError:  # run from a bare source tree
        installed = "unknown"
    assert result.output.strip() == f"mkdeck {installed}"


def test_version_falls_back_when_mkdeck_is_not_installed(monkeypatch) -> None:
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(cli, "version", missing)
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == "mkdeck unknown"


def test_a_command_shows_library_warnings_the_mkdeck_way(deck_file, monkeypatch) -> None:
    installed = []
    monkeypatch.setattr(cli, "install_warning_formatter", lambda: installed.append(True))
    assert runner.invoke(app, ["build", str(deck_file), "-o", str(deck_file.parent / "site")]).exit_code == 0
    assert installed == [True]


def test_no_arguments_shows_the_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "Usage" in result.output


def test_build_writes_the_page(deck_file, tmp_path) -> None:
    result = runner.invoke(app, ["build", str(deck_file), "-o", str(tmp_path / "site")])
    assert result.exit_code == 0, result.output
    index = tmp_path / "site" / "index.html"
    assert index.is_file()
    assert '<span class="mkd-num">0.65 m</span>' in index.read_text(encoding="utf-8")


def test_new_scaffolds_a_deck_that_builds(tmp_path) -> None:
    folder = tmp_path / "vault-runs"
    assert runner.invoke(app, ["new", str(folder)]).exit_code == 0
    assert (folder / "deck.md").is_file()
    assert (folder / "deck.yml").is_file()
    assert (folder / "assets").is_dir()
    result = runner.invoke(app, ["build", str(folder), "-o", str(tmp_path / "site")])
    assert result.exit_code == 0, result.output
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "Vault Runs" in html
    assert '<span class="mkd-num">134 N m</span>' in html  # the scaffold's own example of a highlighted number
    assert html.count("<section") == 4  # the scaffold's heading is its title slide, so none is generated


def test_new_refuses_a_folder_that_holds_something(tmp_path) -> None:
    folder = tmp_path / "taken"
    folder.mkdir()
    (folder / "keep.txt").write_text("mine")
    result = runner.invoke(app, ["new", str(folder)])
    assert result.exit_code == 1
    assert "not empty" in result.output


def test_a_deck_error_prints_without_a_traceback(tmp_path) -> None:
    result = runner.invoke(app, ["build", str(tmp_path / "gone.md"), "-o", str(tmp_path / "site")])
    assert result.exit_code == 1
    assert "does not exist" in result.output
    assert "Traceback" not in result.output


def test_an_unknown_slide_option_names_the_slide(tmp_path) -> None:
    path = tmp_path / "deck.md"
    path.write_text("---\ntitle: Runs\n---\n\n<!--\nid: a1\nnope: 1\n-->\n\nHi.\n")
    result = runner.invoke(app, ["build", str(path), "-o", str(tmp_path / "site")])
    assert result.exit_code == 1
    assert "a1" in result.output
    assert "nope" in result.output


def test_a_bad_viewport_is_refused_before_the_browser_starts(deck_file, tmp_path) -> None:
    result = runner.invoke(app, ["check", str(deck_file), "--size", "wide", "--out", str(tmp_path / "report")])
    assert result.exit_code == 1
    assert "WIDTHxHEIGHT" in result.output


def test_check_says_how_to_install_playwright(deck_file, tmp_path, monkeypatch) -> None:
    from mkdeck import check as check_module
    from mkdeck.browser import INSTALL_HINT
    from mkdeck.errors import DeckError

    def missing() -> None:
        raise DeckError(INSTALL_HINT)

    monkeypatch.setattr(check_module, "require_playwright", missing)
    result = runner.invoke(app, ["check", str(deck_file), "--out", str(tmp_path / "report")])
    assert result.exit_code == 1
    assert "mkdeck[check]" in result.output
    assert "uv tool install" in result.output


# --------------------------------------------------------------------------- #
# mkdeck new
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("folder", "title"),
    [
        ("vault-runs", "Vault Runs"),
        pytest.param(
            "a:b", "A:b", marks=pytest.mark.skipif(sys.platform == "win32", reason="a folder cannot hold a colon")
        ),
        ("q3 #1", "Q3 #1"),
        ("[x]", "[x]"),
        ("it's", "It's"),
        ("yes", "Yes"),
        ("{x}", "{x}"),
        ("null", "Null"),
        ("naïve_talk", "Naïve Talk"),
    ],
)
def test_new_writes_any_folder_name_as_a_title_that_survives(tmp_path, folder, title) -> None:
    deck = tmp_path / folder
    assert runner.invoke(app, ["new", str(deck)]).exit_code == 0
    assert load_source(deck).deck.title == title
    result = runner.invoke(app, ["build", str(deck), "-o", str(tmp_path / "site")])
    assert result.exit_code == 0, result.output


def test_new_refuses_a_file(tmp_path) -> None:
    afile = tmp_path / "afile"
    afile.write_text("mine")
    result = runner.invoke(app, ["new", str(afile)])
    assert result.exit_code == 1
    assert "not a folder" in result.output
    assert "Traceback" not in result.output
    assert afile.read_text(encoding="utf-8") == "mine"


# --------------------------------------------------------------------------- #
# A disk that says no
# --------------------------------------------------------------------------- #


def test_an_output_path_that_is_a_file_is_a_message_not_a_traceback(deck_file, tmp_path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder")
    result = runner.invoke(app, ["build", str(deck_file), "-o", str(blocker)])
    assert result.exit_code == 1
    assert result.output.startswith("mkdeck: ")
    assert "Traceback" not in result.output


def test_a_permission_error_is_a_message_not_a_traceback(deck_file, tmp_path, monkeypatch) -> None:
    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(tmp_path / "site"))

    monkeypatch.setattr(Deck, "build", refuse)
    result = runner.invoke(app, ["build", str(deck_file)])
    assert result.exit_code == 1
    assert "mkdeck: Permission denied" in result.output
    assert "site" in result.output


def test_a_deck_that_is_not_utf8_is_a_message_not_a_traceback(tmp_path) -> None:
    path = tmp_path / "deck.md"
    path.write_bytes(b"---\ntitle: T\n---\n\n\xff\xfe not utf-8\n")
    result = runner.invoke(app, ["build", str(path), "-o", str(tmp_path / "site")])
    assert result.exit_code == 1
    assert result.output.startswith("mkdeck: ")
    assert "Traceback" not in result.output


# --------------------------------------------------------------------------- #
# serve, check, export: what the command hands the library and prints back
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("flags", "reload"),
    [([], True), (["--reload"], True), (["--no-reload"], False)],
)
def test_serve_watches_unless_told_not_to(deck_file, monkeypatch, flags, reload) -> None:
    seen = {}
    monkeypatch.setattr(DeckSource, "serve", lambda self, **options: seen.update(options))
    assert runner.invoke(app, ["serve", str(deck_file), *flags]).exit_code == 0
    assert seen["reload"] is reload
    assert seen["open_browser"] is False


def test_check_prints_the_report_it_wrote(deck_file, tmp_path, monkeypatch) -> None:
    records = [{"n": 1, "id": "intro", "layout": "title", "flags": []}]
    monkeypatch.setattr(cli, "check_deck", lambda path, **options: records)
    result = runner.invoke(app, ["check", str(deck_file), "--size", "800x600"])
    assert result.exit_code == 0
    assert result.output.startswith(f"viewport 800x600, deck {deck_file}\n")
    assert "intro" in result.output


def test_export_says_where_the_pdf_went(deck_file, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "export_deck", lambda path, out, **options: out)
    result = runner.invoke(app, ["export", str(deck_file), "-o", str(tmp_path / "talk.pdf")])
    assert result.exit_code == 0
    assert result.output.strip() == f"Wrote {tmp_path / 'talk.pdf'}"


# --------------------------------------------------------------------------- #
# mkdeck rollout
# --------------------------------------------------------------------------- #


def brax_page(*, frames: int = 2, break_it: bool = False) -> str:
    """A minimal Brax playback page: one link, one box, a few frames."""
    scene = {
        "opt": {"timestep": 0.02},
        "link_names": ["torso"],
        "geoms": {
            "torso": [
                {
                    "name": "Box",
                    "link_idx": 0,
                    "pos": [0, 0, 0],
                    "rot": [1, 0, 0, 0],
                    "rgba": [1, 1, 1, 1],
                    "size": [1, 1, 1],
                }
            ]
        },
        "states": {"x": [{"pos": [[0.0, 0.0, 0.1 * t]], "rot": [[1.0, 0.0, 0.0, 0.0]]} for t in range(frames)]},
    }
    if break_it:
        del scene["states"]["x"][0]["pos"]
    blob = base64.b64encode(zlib.compress(json.dumps(scene).encode())).decode()
    return f'<html><script>var system = "{blob}";</script></html>'


def write_page(folder: Path, name: str, text: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(text)
    return path


def test_rollout_converts_a_page_and_says_where_it_went(tmp_path) -> None:
    page = write_page(tmp_path, "run.html", brax_page())
    out = tmp_path / "assets"
    result = runner.invoke(app, ["rollout", str(page), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "run.html -> run.rollout (new meshes " in result.output
    assert (out / "run.rollout").is_file()
    assert len(list(out.glob("*.meshes"))) == 1


def test_rollout_skips_a_plot_among_the_playback_pages(tmp_path) -> None:
    good = write_page(tmp_path, "good.html", brax_page())
    plot = write_page(tmp_path, "plot.html", "<html>a plot</html>")
    result = runner.invoke(app, ["rollout", str(good), str(plot), "-o", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert "good.html -> good.rollout" in result.output
    assert "plot.html skipped" in result.output
    assert not (tmp_path / "out" / "plot.rollout").exists()


def test_rollout_with_nothing_to_convert_fails(tmp_path) -> None:
    plot = write_page(tmp_path, "plot.html", "<html>a plot</html>")
    result = runner.invoke(app, ["rollout", str(plot), "-o", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "nothing to convert" in result.output


def test_rollout_refuses_two_pages_that_would_share_an_output(tmp_path) -> None:
    first = write_page(tmp_path / "a", "run.html", brax_page(frames=2))
    second = write_page(tmp_path / "b", "run.html", brax_page(frames=5))
    out = tmp_path / "out"
    result = runner.invoke(app, ["rollout", str(first), str(second), "-o", str(out)])
    assert result.exit_code == 1
    assert "would both become run.rollout" in result.output
    assert str(first) in result.output and str(second) in result.output
    assert not out.exists()  # nothing was converted before the clash was found


def test_rollout_takes_the_same_page_twice_as_once(tmp_path) -> None:
    page = write_page(tmp_path, "run.html", brax_page())
    result = runner.invoke(app, ["rollout", str(page), str(page), "-o", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert result.output.count("run.html -> run.rollout") == 1


def test_rollout_names_a_page_that_is_malformed(tmp_path) -> None:
    bad = write_page(tmp_path, "bad.html", brax_page(break_it=True))
    result = runner.invoke(app, ["rollout", str(bad), "-o", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "bad.html" in result.output
    assert "Traceback" not in result.output


def test_rollout_converts_what_it_can_and_still_fails(tmp_path) -> None:
    bad = write_page(tmp_path, "bad.html", brax_page(break_it=True))
    good = write_page(tmp_path, "good.html", brax_page())
    out = tmp_path / "out"
    result = runner.invoke(app, ["rollout", str(bad), str(good), "-o", str(out)])
    assert result.exit_code == 1
    assert "bad.html" in result.output
    assert "good.html -> good.rollout" in result.output
    assert "1 of 2 pages could not be converted" in result.output
    assert (out / "good.rollout").is_file()
    assert not (out / "bad.rollout").exists()


@pytest.mark.parametrize(
    ("flags", "extra", "code"),
    [
        ([], ["--strict"], 0),
        (["OVERFLOW top 0px bottom 9px"], [], 0),
        (["OVERFLOW top 0px bottom 9px"], ["--strict"], 1),
    ],
)
def test_check_fails_on_a_flagged_slide_only_when_asked_to(
    deck_file, tmp_path, monkeypatch, flags, extra, code
) -> None:
    monkeypatch.setattr(cli, "check_deck", lambda *args, **kwargs: [{"n": 1, "flags": flags}])
    result = runner.invoke(app, ["check", str(deck_file), "--out", str(tmp_path / "report"), *extra])
    assert result.exit_code == code, result.output
    assert "viewport 1920x1080" in result.output
    if code:
        assert "1 of 1 slides are flagged" in result.output


def test_a_port_out_of_range_is_a_usage_error_not_a_traceback(deck_file) -> None:
    result = runner.invoke(app, ["serve", str(deck_file), "--port", "99999"])
    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert "65535" in result.output


def test_a_single_file_build_is_one_file_for_a_html_name_and_a_folder_for_any_other(deck_file, tmp_path) -> None:
    for name, produced in (("talk.html", "talk.html"), ("talk.txt", "talk.txt/index.html")):
        result = runner.invoke(app, ["build", str(deck_file), "--single-file", "-o", str(tmp_path / "out" / name)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "out" / produced).is_file()
        assert f"Wrote {tmp_path / 'out' / produced}" in result.output
