"""The command line: the five commands, and what a bad deck prints."""

import pytest
from typer.testing import CliRunner

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
    for command in ("new", "serve", "build", "check", "export"):
        assert command in result.output


def test_no_arguments_shows_the_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "Usage" in result.output


def test_build_writes_the_page(deck_file, tmp_path) -> None:
    result = runner.invoke(app, ["build", str(deck_file), "-o", str(tmp_path / "site")])
    assert result.exit_code == 0, result.output
    index = tmp_path / "site" / "index.html"
    assert index.is_file()
    assert '<span class="mkd-num">0.65 m</span>' in index.read_text()


def test_new_scaffolds_a_deck_that_builds(tmp_path) -> None:
    folder = tmp_path / "vault-runs"
    assert runner.invoke(app, ["new", str(folder)]).exit_code == 0
    assert (folder / "deck.md").is_file()
    assert (folder / "deck.yml").is_file()
    assert (folder / "assets").is_dir()
    result = runner.invoke(app, ["build", str(folder), "-o", str(tmp_path / "site")])
    assert result.exit_code == 0, result.output
    assert "Vault Runs" in (tmp_path / "site" / "index.html").read_text()


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
    from mkdeck.errors import DeckError

    def missing() -> None:
        raise DeckError(check_module.INSTALL_HINT)

    monkeypatch.setattr(check_module, "require_playwright", missing)
    result = runner.invoke(app, ["check", str(deck_file), "--out", str(tmp_path / "report")])
    assert result.exit_code == 1
    assert "mkdeck[check]" in result.output
