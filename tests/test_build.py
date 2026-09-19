"""Building a deck folder into a site, and loading one from disk."""

import pytest

from mkdeck import Deck, DeckError, Embed, Slide, build_source, load_source
from mkdeck.build import find_markdown

DECK = """---
title: Quadruped Vault Runs
date: 2026-09-18
---

<!--
id: g3-paired
-->

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


def test_a_build_writes_the_page_the_assets_and_the_vendored_tree(deck_folder, tmp_path):
    index = build_source(deck_folder, tmp_path / "site")
    assert index == tmp_path / "site" / "index.html"
    assert (tmp_path / "site" / "assets" / "g3_18.html").is_file()
    assert (tmp_path / "site" / "mkdeck-assets" / "mkdeck.js").is_file()
    assert (tmp_path / "site" / "mkdeck-assets" / "reveal.js" / "dist" / "reveal.js").is_file()
    assert 'src="assets/g3_18.html"' in index.read_text()


def test_a_single_file_build_leaves_only_the_deck_assets_outside(deck_folder, tmp_path):
    index = build_source(deck_folder, tmp_path / "one" / "deck.html", single_file=True)
    html = index.read_text()
    assert index.name == "deck.html"
    assert not (tmp_path / "one" / "mkdeck-assets").exists()
    assert (tmp_path / "one" / "assets" / "g3_18.html").is_file()
    assert 'rel="stylesheet"' not in html
    assert "<script src=" not in html
    assert "<style>" in html
    assert "data:font/woff2;base64," in html


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
    assert loaded.config.units == ["apples"]
    assert deck_folder / "deck.yml" in loaded.watched


def test_a_large_embed_is_called_out(deck_folder, tmp_path, capsys):
    (deck_folder / "assets" / "g3_18.html").write_bytes(b"x" * 2_500_000)
    build_source(deck_folder, tmp_path / "site")
    assert "2.5 MB" in capsys.readouterr().err


def test_an_embed_shown_twice_is_called_out_once(deck_folder, tmp_path, capsys):
    (deck_folder / "assets" / "g3_18.html").write_bytes(b"x" * 2_500_000)
    (deck_folder / "deck.md").write_text(f"{DECK}\n---\n\nThe same run, seen again.\n\n![18 N m](assets/g3_18.html)\n")
    build_source(deck_folder, tmp_path / "site")
    assert capsys.readouterr().err.count("2.5 MB") == 1


def test_building_over_the_source_is_refused(deck_folder):
    with pytest.raises(DeckError, match="source folder"):
        build_source(deck_folder, deck_folder)


def test_a_python_deck_builds_through_its_own_method(tmp_path):
    deck = Deck(title="Runs", date="2026-09-18")
    deck.slides.append(Slide(sentence="Five seeds cross.", embeds=[Embed("assets/g1.html", label="18 N m")]))
    index = deck.build(tmp_path / "site")
    assert index.is_file()
    assert '<deck-embed src="assets/g1.html">' in index.read_text()


def test_the_stylesheets_and_scripts_a_deck_adds_are_copied(deck_folder, tmp_path):
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").write_text(":root { --mkd-accent: #b4532a; }")
    (deck_folder / "theme" / "marks.js").write_text('console.log("marks");')
    (deck_folder / "deck.yml").write_text("extra_css: [theme/mine.css]\nextra_js: [theme/marks.js]\n")

    index = build_source(deck_folder, tmp_path / "site")

    assert 'href="theme/mine.css"' in index.read_text()
    assert (tmp_path / "site" / "theme" / "mine.css").is_file()
    assert (tmp_path / "site" / "theme" / "marks.js").is_file()


def test_a_stylesheet_that_is_not_there_is_called_out(deck_folder, tmp_path, capsys):
    (deck_folder / "deck.yml").write_text("extra_css: [theme/nope.css]\n")
    build_source(deck_folder, tmp_path / "site")
    assert "theme/nope.css" in capsys.readouterr().err


def test_a_python_deck_cannot_repeat_a_slide_id(tmp_path):
    deck = Deck(title="Runs", slides=[Slide(id="g3", sentence="One."), Slide(id="g3", sentence="Two.")])
    with pytest.raises(DeckError, match="repeats the id"):
        deck.build(tmp_path / "site")
