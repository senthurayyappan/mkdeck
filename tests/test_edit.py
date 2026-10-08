"""Editing slide text on the served page: where each piece of text sits in
the file, how an edit is written back, and when it is refused.
"""

import pytest

from mkdeck import DeckError
from mkdeck.edit import EditConflictError, apply_edit, edit_file
from mkdeck.markdown import locate_text, parse_markdown

DECK = """---
title: Runs
---

# Results

First sentence. Second sentence
wraps here.

- one
- two
  continued

---

| Cap | Cross \\| ings |
| --- | --- |
| 18 N m | 2 |
"""


def edit(text: str, slide: int, key: str, replacement: str) -> str:
    expected = locate_text(text, source="deck.md")[slide][key].text
    edited = apply_edit(
        text,
        slide=slide,
        key=key,
        expected=expected,
        replacement=replacement,
    )
    parse_markdown(edited, source="deck.md")  # still a deck
    return edited


def test_each_piece_is_found_on_the_lines_of_the_whole_file() -> None:
    first, second = locate_text(DECK, source="deck.md")
    assert first["title"].lines == (4, 5)
    assert first["sentence:0"].lines == (6, 8)
    assert first["bullet:1"].text == "two\ncontinued"
    assert first["bullet:1"].lines == (10, 12)
    assert second["cell:-1:1"].text == "Cross | ings"
    assert second["cell:0:0"].lines == (17, 18)


def test_the_keys_match_the_parsed_slides() -> None:
    deck = parse_markdown(DECK, source="deck.md")
    first, second = locate_text(DECK, source="deck.md")
    assert first["title"].text == deck.slides[0].title
    assert first["sentence:0"].text == deck.slides[0].sentence
    assert [first[f"bullet:{n}"].text for n in range(2)] == (
        deck.slides[0].bullets
    )
    assert deck.slides[1].table is not None
    assert second["cell:-1:1"].text == deck.slides[1].table.columns[1]


def test_text_with_no_single_place_is_not_offered() -> None:
    text = (
        "<!--\ntitle: Set in options\nbullets: [a, b]\n-->\n\n"
        "Words ![fig](a.png) around a figure.\n\n"
        "---\n\n- one\n\n  two\n\nterm\n: definition\n"
    )
    first, second = locate_text(text, source="deck.md")
    assert first == {}
    assert second == {}


def test_a_blank_line_splits_a_sentence_into_two_paragraphs() -> None:
    edited = edit(DECK, 0, "sentence:0", "First sentence.\n\nSecond one.")
    slide = parse_markdown(edited, source="deck.md").slides[0]
    assert slide.sentence == "First sentence.\n\nSecond one."


def test_a_sentence_loses_its_trailing_spaces() -> None:
    edited = edit(DECK, 0, "sentence:0", "First. \n\nSecond.  ")
    assert "\nFirst.\n\nSecond.\n" in edited


def test_a_title_keeps_its_level_and_takes_one_line() -> None:
    edited = edit(DECK.replace("# Results", "## Results"), 0, "title", "A\nB")
    assert "\n## A B\n" in edited


def test_each_line_of_a_bullet_is_a_bullet_and_empty_text_deletes_it() -> None:
    edited = edit(DECK, 0, "bullet:1", "two more\nthree")
    assert "- one\n- two more\n- three\n" in edited
    edited = edit(edited, 0, "bullet:0", "  ")
    assert parse_markdown(edited, source="deck.md").slides[0].bullets == [
        "two more",
        "three",
    ]


def test_an_ordered_bullet_keeps_its_marker() -> None:
    text = "1. one\n2. two\n"
    assert edit(text, 0, "bullet:1", "deux") == "1. one\n2. deux\n"


def test_a_cell_is_replaced_in_its_row_and_a_pipe_is_escaped() -> None:
    edited = edit(DECK, 1, "cell:-1:1", "A|B")
    assert "| Cap | A\\|B |" in edited
    edited = edit(edited, 1, "cell:0:0", "20 N m")
    table = parse_markdown(edited, source="deck.md").slides[1].table
    assert table is not None
    assert table.columns == ["Cap", "A|B"]
    assert table.rows == [["20 N m", "2"]]


def test_a_cell_the_row_leaves_out_cannot_be_edited() -> None:
    text = "| a | b |\n| - | - |\n| 1 |\n"
    with pytest.raises(DeckError, match="not written in the row"):
        edit(text, 0, "cell:0:1", "x")


def test_line_endings_and_the_byte_order_mark_are_kept() -> None:
    text = "﻿" + DECK.replace("\n", "\r\n")
    edited = edit(text, 0, "title", "New")
    assert edited.startswith("﻿---\r\n")
    assert "\n" not in edited.replace("\r\n", "")
    assert "# New\r\n" in edited


def test_an_edit_to_text_that_changed_is_refused() -> None:
    with pytest.raises(EditConflictError):
        apply_edit(
            DECK, slide=0, key="title", expected="Old", replacement="New"
        )
    with pytest.raises(EditConflictError):
        apply_edit(DECK, slide=9, key="title", expected="", replacement="x")


def test_text_set_in_the_options_is_refused_with_a_reason() -> None:
    text = "<!--\ntitle: Set in options\n-->\n\nWords.\n"
    with pytest.raises(DeckError, match="slide options") as raised:
        apply_edit(
            text,
            slide=0,
            key="title",
            expected="Set in options",
            replacement="x",
        )
    assert not isinstance(raised.value, EditConflictError)


def test_an_empty_title_is_refused() -> None:
    with pytest.raises(DeckError, match="cannot be empty"):
        edit(DECK, 0, "title", " ")


def test_the_file_is_rewritten_in_place(tmp_path) -> None:
    path = tmp_path / "deck.md"
    path.write_bytes(DECK.encode())
    edit_file(
        path, slide=0, key="title", expected="Results", replacement="Done"
    )
    assert "# Done\n" in path.read_text()
    assert [entry.name for entry in tmp_path.iterdir()] == ["deck.md"]
