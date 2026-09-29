"""The single-file build: stylesheets, scripts, fonts and rollouts folded into one document."""

import base64
import warnings

import pytest

from mkdeck import DeckError, DeckWarning, load_source
from mkdeck.inline import inline_assets

DECK = """---
title: Quadruped Vault Runs
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


def test_a_font_url_inside_the_deck_is_inlined(deck_folder, tmp_path):
    font = b"wOFF-test-bytes"
    (deck_folder / "assets" / "fonts").mkdir()
    (deck_folder / "assets" / "fonts" / "myhand.woff2").write_bytes(font)
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").write_text('@font-face { src: url("../assets/fonts/myhand.woff2"); }\n')
    (deck_folder / "deck.yml").write_text("extra_css: [theme/mine.css]\n")
    index = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True)
    assert base64.b64encode(font).decode("ascii") in index.read_text()


def test_a_font_url_outside_the_deck_is_not_inlined(deck_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-TOKEN")
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").write_text('body { background: url("../../secret.txt"); }\n')
    (deck_folder / "deck.yml").write_text("extra_css: [theme/mine.css]\n")
    with pytest.warns(DeckWarning, match="leaves the deck folder"):
        index = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True)
    html = index.read_text()
    assert "SECRET-TOKEN" not in html
    assert "../../secret.txt" not in html


def test_a_stylesheet_that_is_not_utf8_is_a_deck_error_in_a_single_file_build(deck_folder, tmp_path):
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").write_bytes(b"/* caf\xe9 */")
    (deck_folder / "deck.yml").write_text("extra_css: [theme/mine.css]\n")
    with pytest.raises(DeckError, match="not valid UTF-8"):
        load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True)


# --------------------------------------------------------------------------- #
# The single-file build
# --------------------------------------------------------------------------- #


def single_file_deck(folder, css: dict[str, str], *, extra: str | None = None):
    (folder / "theme").mkdir(exist_ok=True)
    for name, text in css.items():
        (folder / "theme" / name).write_text(text)
    names = ", ".join(f"theme/{name}" for name in css)
    (folder / "deck.yml").write_text(f"extra_css: [{names}]\n")
    if extra is not None:
        (folder / "deck.md").write_text(extra)


def test_a_stylesheet_import_is_inlined_with_what_it_refers_to(deck_folder, tmp_path):
    font = b"wOFF-import-bytes"
    (deck_folder / "assets" / "f.woff2").write_bytes(font)
    single_file_deck(
        deck_folder,
        {
            "mine.css": '@import "base.css";\n@import url(wide.css) screen and (min-width: 600px);\nbody { margin: 0; }',
            "base.css": '@font-face { src: url("../assets/f.woff2"); }',
            "wide.css": ".wide { color: teal; }",
        },
    )
    html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    assert "@import" not in html
    assert base64.b64encode(font).decode("ascii") in html
    assert "@media screen and (min-width: 600px) {.wide { color: teal; }}" in html


def test_a_remote_import_is_left_alone(deck_folder, tmp_path):
    single_file_deck(deck_folder, {"mine.css": '@import url("https://fonts.example.org/x.css");\nbody {}'})
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeckWarning)
        html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    assert '@import url("https://fonts.example.org/x.css");' in html


def test_an_import_that_is_missing_or_loops_is_reported(deck_folder, tmp_path):
    single_file_deck(
        deck_folder,
        {"mine.css": '@import "gone.css";\n@import "loop.css";', "loop.css": '@import "loop.css";\n.a {}'},
    )
    with pytest.warns(DeckWarning) as caught:
        html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    messages = " ".join(str(warning.message) for warning in caught)
    assert "gone.css" in messages
    assert "imports itself" in messages
    assert ".a {}" in html


def test_an_import_outside_the_deck_is_dropped(deck_folder, tmp_path):
    (tmp_path / "secret.css").write_text(".secret { content: 'SECRET-TOKEN'; }")
    single_file_deck(deck_folder, {"mine.css": '@import "../../secret.css";\nbody {}'})
    with pytest.warns(DeckWarning, match="leaves the deck folder"):
        html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    assert "SECRET-TOKEN" not in html


def test_a_url_that_points_at_nothing_is_reported_and_left_as_written(deck_folder, tmp_path):
    single_file_deck(deck_folder, {"mine.css": 'a { background: url("../assets/gone.png"); }\nb { fill: url(#clip); }'})
    with pytest.warns(DeckWarning, match="gone.png") as caught:
        html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    assert len(caught) == 1  # the fragment reference is not a file
    assert 'url("../assets/gone.png")' in html


def test_the_bundled_stylesheets_leave_nothing_unresolved(deck_folder, tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeckWarning)
        html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    assert "url(fonts/" not in html
    assert 'url("fonts/' not in html


def test_a_stylesheet_that_is_a_cdn_link_is_left_linked_without_a_warning(deck_folder, tmp_path):
    (deck_folder / "deck.yml").write_text(
        "extra_css: ['https://cdn.example.org/a.css']\nextra_js: ['//cdn.example.org/a.js']\n"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeckWarning)
        html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    assert '<link rel="stylesheet" href="https://cdn.example.org/a.css">' in html
    assert '<script src="//cdn.example.org/a.js"></script>' in html


def test_a_path_with_an_ampersand_is_found_when_inlining(deck_folder, tmp_path):
    single_file_deck(deck_folder, {"a&b.css": "body { color: teal; }"})
    html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    assert "body { color: teal; }" in html
    assert "a&amp;b.css" not in html


def test_a_script_cannot_end_its_element_or_open_a_comment(deck_folder, tmp_path):
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "marks.js").write_text('var a = "</script><!--"; var b = "<!-- <script>";')
    (deck_folder / "deck.yml").write_text("extra_js: [theme/marks.js]\n")
    html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    assert '"<\\/script><\\!--"' in html
    assert '"<\\!-- <script>"' in html
    assert '"</script><!--"' not in html
    assert '"<!-- <script>"' not in html


def test_the_authors_own_html_is_not_inlined(deck_folder, tmp_path):
    (deck_folder / "deck.md").write_text(
        '---\ntitle: T\n---\n\nHi.\n\n<link rel="stylesheet" href="mkdeck-assets/mkdeck.css">\n'
        '<script src="mkdeck-assets/mkdeck.js"></script>\n'
    )
    html = load_source(deck_folder).build(tmp_path / "one" / "deck.html", single_file=True).read_text()
    slides = html.split("<!--mkdeck-slides-->")[1].split("<!--/mkdeck-slides-->")[0]
    assert '<link rel="stylesheet" href="mkdeck-assets/mkdeck.css">' in slides
    assert '<script src="mkdeck-assets/mkdeck.js"></script>' in slides
    assert "<style>" in html  # the template's own tags were still inlined


# --------------------------------------------------------------------------- #
# inline_assets, on a document in hand
# --------------------------------------------------------------------------- #


def test_a_remote_stylesheet_and_script_are_left_linked(tmp_path):
    html = '<link rel="stylesheet" href="https://cdn.example.org/a.css"><script src="https://cdn.example.org/a.js"></script>'
    assert inline_assets(html, source=tmp_path) == html


def test_a_tag_of_the_template_is_replaced_and_the_slides_are_left_alone(tmp_path):
    (tmp_path / "a.css").write_text("body { color: teal; }")
    slide = '<link rel="stylesheet" href="a.css">'
    html = f'<link rel="stylesheet" href="a.css"><!--mkdeck-slides-->{slide}<!--/mkdeck-slides-->'
    folded = inline_assets(html, source=tmp_path)
    assert folded.startswith("<style>body { color: teal; }</style>")
    assert folded.endswith(f"{slide}<!--/mkdeck-slides-->")


def test_a_deck_without_a_payload_marker_gets_its_rollouts_at_the_end(deck_folder, tmp_path):
    from mkdeck.inline import inline_rollouts

    deck = load_source(deck_folder).deck
    with pytest.warns(DeckWarning, match="payload marker"):
        html = inline_rollouts("<html></html>", deck, source=deck_folder)
    assert html.startswith("<html></html><script")
