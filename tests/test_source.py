"""Loading a deck from disk, and building or serving it from what was loaded."""

from pathlib import Path

import pytest

from mkdeck import DeckError, DeckSource, load_source
from mkdeck.source import find_markdown

DECK = """---
title: Quadruped Vault Runs
date: 2026-09-18
---

# Quadruped Vault Runs

---

Body load falls from 134 to 86 N s.

![18 N m](assets/g3_18.html)
"""


@pytest.fixture
def deck_folder(tmp_path):
    folder = tmp_path / "deck"
    (folder / "assets").mkdir(parents=True)
    (folder / "assets" / "g3_18.html").write_text("<!doctype html><title>g3</title>")
    (folder / "deck.md").write_text(DECK)
    return folder


def test_a_deck_folder_needs_a_deck_file(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(DeckError, match=r"deck\.md"):
        find_markdown(tmp_path / "empty")


def test_a_missing_path_says_so(tmp_path):
    with pytest.raises(DeckError, match="does not exist"):
        find_markdown(tmp_path / "gone")


def test_slides_md_is_found_too(tmp_path):
    (tmp_path / "slides.md").write_text(DECK)
    assert find_markdown(tmp_path).name == "slides.md"


def test_the_frontmatter_wins_over_deck_yml(deck_folder):
    (deck_folder / "deck.yml").write_text("title: From the file\ntheme: minimal\nunits: [apples]\n")
    loaded = load_source(deck_folder)
    assert loaded.deck.title == "Quadruped Vault Runs"
    assert loaded.deck.units == ["apples"]
    assert loaded.directory == deck_folder
    assert loaded.markdown == deck_folder / "deck.md"


def test_a_deck_file_that_is_not_utf8_names_the_file(deck_folder):
    (deck_folder / "deck.md").write_bytes(b"---\ntitle: caf\xe9\n---\n")
    with pytest.raises(DeckError, match="not valid UTF-8") as caught:
        load_source(deck_folder)
    assert str(deck_folder / "deck.md") in str(caught.value)


def test_a_loaded_deck_builds_with_one_call(deck_folder, tmp_path):
    index = load_source(deck_folder).build(tmp_path / "site")
    assert index == tmp_path / "site" / "index.html"
    assert "Quadruped Vault Runs" in index.read_text(encoding="utf-8")
    assert (tmp_path / "site" / "assets" / "g3_18.html").is_file()


def test_a_loaded_deck_builds_into_one_file(deck_folder, tmp_path):
    index = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True)
    assert index == tmp_path / "one" / "deck.html"
    assert "<style>" in index.read_text(encoding="utf-8")


def test_a_loaded_deck_may_be_changed_before_it_is_built(deck_folder, tmp_path):
    loaded = load_source(deck_folder)
    loaded.deck.units.append("apples")
    loaded.deck.title = "Renamed"
    assert "Renamed" in loaded.build(tmp_path / "site").read_text(encoding="utf-8")


def test_the_loaded_deck_is_frozen_but_names_its_files(deck_folder):
    loaded = load_source(deck_folder / "deck.md")
    assert isinstance(loaded, DeckSource)
    assert loaded.directory == deck_folder
    with pytest.raises(AttributeError):
        loaded.directory = Path("elsewhere")  # ty: ignore[invalid-assignment]


def test_deck_yml_and_the_frontmatter_are_read_once_into_the_deck(deck_folder):
    (deck_folder / "deck.yml").write_text("theme: dark\nreveal: {hash: true, transition: none}\n")
    (deck_folder / "deck.md").write_text("---\nreveal: {transition: fade}\n---\n\nHi.\n")
    deck = load_source(deck_folder).deck
    assert deck.theme == "dark"
    assert deck.reveal == {"hash": True, "transition": "fade"}
    assert deck.title == "Slide Deck"
