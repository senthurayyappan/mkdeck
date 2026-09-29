import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from mkdeck.config import CONFIG_KEYS, find_config_file, merge_settings, normalize_settings, read_config_file
from mkdeck.errors import DeckError
from mkdeck.markdown import parse_markdown
from mkdeck.model import DEFAULT_UNITS, Deck

# The settings of the barkour deck, as deck.yml would hold them.
DECK_YML = """
title: "Barkour vault: model mismatch, lean formulation, open problems"
date: 2026-09-16
theme: minimal
units:
  - N m s/rad
  - body weights
  - N m
  - percent
extra_css:
  - assets/lab.css
reveal:
  hash: true
  transition: none
"""


def write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def test_the_settings_are_exactly_the_deck_fields_that_are_not_slides() -> None:
    assert set(CONFIG_KEYS) == {field.name for field in dataclasses.fields(Deck)} - {"slides"}


def test_a_deck_starts_from_the_default_settings() -> None:
    deck = Deck(title="Slide Deck")
    assert deck.theme == "minimal"
    assert deck.date is None
    assert deck.title_slide is True
    assert deck.units == list(DEFAULT_UNITS)
    assert deck.extra_css == []
    assert deck.reveal == {}


def test_the_barkour_settings_are_read(tmp_path: Path) -> None:
    settings = read_config_file(write(tmp_path, "deck.yml", DECK_YML))
    assert settings["title"].startswith("Barkour vault")
    assert settings["date"] == "2026-09-16"
    assert settings["units"] == ["N m s/rad", "body weights", "N m", "percent"]
    assert settings["extra_css"] == ["assets/lab.css"]
    assert settings["reveal"] == {"hash": True, "transition": "none"}
    assert Deck(**settings).theme == "minimal"


def test_a_bare_yaml_date_becomes_iso_text() -> None:
    assert normalize_settings({"date": dt.date(2026, 9, 18)}, origin="deck.md") == {"date": "2026-09-18"}


def test_a_lone_extra_stylesheet_becomes_a_list() -> None:
    assert normalize_settings({"extra_css": "assets/lab.css"}, origin="deck.yml") == {"extra_css": ["assets/lab.css"]}


def test_a_null_value_is_left_out_so_the_default_stands() -> None:
    assert normalize_settings({"date": None, "theme": None}, origin="deck.yml") == {}


def test_a_remote_stylesheet_is_allowed() -> None:
    settings = normalize_settings({"extra_css": "https://example.com/a.css"}, origin="deck.yml")
    assert settings == {"extra_css": ["https://example.com/a.css"]}


def test_a_stylesheet_that_leaves_the_deck_is_refused() -> None:
    with pytest.raises(DeckError, match="inside the deck folder"):
        normalize_settings({"extra_css": ["../secret.css"]}, origin="deck.yml")


def test_an_unknown_key_is_an_error_that_suggests_the_right_one() -> None:
    with pytest.raises(DeckError) as caught:
        normalize_settings({"them": "minimal"}, origin="deck.yml")
    message = str(caught.value)
    assert message.startswith('deck.yml: The file has the unknown key "them".')
    assert 'Did you mean "theme"?' in message


def test_an_unknown_key_without_a_near_match_lists_the_keys() -> None:
    with pytest.raises(DeckError) as caught:
        normalize_settings({"slides": []}, origin="deck.yml")
    assert "The keys are: title, date, theme, units," in str(caught.value)


def test_a_value_of_the_wrong_shape_is_an_error() -> None:
    with pytest.raises(DeckError, match="but true or false was expected"):
        normalize_settings({"title_slide": "yes"}, origin="deck.yml")
    with pytest.raises(DeckError, match="but a mapping was expected"):
        normalize_settings({"reveal": ["hash"]}, origin="deck.yml")
    with pytest.raises(DeckError, match="but a list of text was expected"):
        normalize_settings({"units": {"N m": True}}, origin="deck.yml")
    with pytest.raises(DeckError, match="but a piece of text was expected"):
        normalize_settings({"title": ["a", "b"]}, origin="deck.yml")


def test_a_deck_without_a_config_file_has_no_settings_from_it(tmp_path: Path) -> None:
    source = write(tmp_path, "deck.md", "# Quadruped Vault Runs\n")
    assert find_config_file(source) is None
    assert read_config_file(source) == {}


def test_the_config_file_is_found_beside_the_markdown_and_by_the_folder(tmp_path: Path) -> None:
    write(tmp_path, "deck.yml", DECK_YML)
    source = write(tmp_path, "deck.md", "# Quadruped Vault Runs\n")
    assert find_config_file(source) == tmp_path / "deck.yml"
    assert find_config_file(tmp_path) == tmp_path / "deck.yml"
    assert read_config_file(source)["date"] == "2026-09-16"


def test_the_yaml_suffix_is_accepted_too(tmp_path: Path) -> None:
    write(tmp_path, "deck.yaml", "title: Quadruped Vault Runs\n")
    assert find_config_file(tmp_path) == tmp_path / "deck.yaml"


def test_the_frontmatter_wins_over_the_config_file(tmp_path: Path) -> None:
    write(tmp_path, "deck.yml", DECK_YML)
    source = write(tmp_path, "deck.md", "---\ndate: 2026-09-18\ntitle_slide: false\n---\n")
    deck = parse_markdown(source.read_text(), source=source, defaults=read_config_file(source))
    assert deck.date == "2026-09-18"
    assert deck.title_slide is False
    assert deck.title.startswith("Barkour vault")
    assert deck.units == ["N m s/rad", "body weights", "N m", "percent"]


def test_the_two_reveal_mappings_are_merged_option_by_option() -> None:
    merged = merge_settings({"reveal": {"hash": True, "transition": "none"}}, {"reveal": {"transition": "fade"}})
    assert merged == {"reveal": {"hash": True, "transition": "fade"}}
    assert merge_settings({"reveal": {"hash": True}}, {"title": "x"}) == {"reveal": {"hash": True}, "title": "x"}


def test_a_bad_key_names_the_file_it_came_from(tmp_path: Path) -> None:
    path = write(tmp_path, "deck.yml", "titel: Quadruped Vault Runs\n")
    source = write(tmp_path, "deck.md", "")
    with pytest.raises(DeckError, match=str(path)):
        read_config_file(source)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(DeckError, match=r"other\.md"):
        parse_markdown("---\ntitel: x\n---\n", source=write(other, "other.md", ""))


def test_unreadable_yaml_is_an_error(tmp_path: Path) -> None:
    source = write(tmp_path, "deck.md", "")
    write(tmp_path, "deck.yml", "title: [unclosed\n")
    with pytest.raises(DeckError, match="could not be read"):
        read_config_file(source)


def test_a_config_file_that_is_not_a_mapping_is_an_error(tmp_path: Path) -> None:
    write(tmp_path, "deck.yml", "- Quadruped Vault Runs\n")
    with pytest.raises(DeckError, match="but a mapping of deck settings was expected"):
        read_config_file(tmp_path)


def test_an_empty_config_file_sets_nothing(tmp_path: Path) -> None:
    write(tmp_path, "deck.yml", "\n")
    assert read_config_file(tmp_path) == {}


def test_an_unknown_theme_is_an_error_that_suggests_the_right_one() -> None:
    with pytest.raises(DeckError) as caught:
        normalize_settings({"theme": "nope"}, origin="deck.yml")
    assert str(caught.value).startswith('deck.yml: The theme "nope" does not exist.')
    assert "The themes are: dark, minimal." in str(caught.value)
    with pytest.raises(DeckError, match='Did you mean "minimal"'):
        normalize_settings({"theme": "minimla"}, origin="deck.yml")


def test_a_theme_cannot_climb_out_of_the_theme_folder() -> None:
    with pytest.raises(DeckError, match="does not exist"):
        normalize_settings({"theme": "../../x"}, origin="deck.yml")


def test_every_shipped_theme_is_accepted() -> None:
    for theme in ("minimal", "dark"):
        assert normalize_settings({"theme": theme}, origin="deck.yml") == {"theme": theme}


def test_a_bare_no_is_refused_with_a_hint_to_quote_it() -> None:
    with pytest.raises(DeckError, match='The key "title" holds the value false') as caught:
        normalize_settings({"title": False}, origin="deck.yml")  # what YAML makes of a bare `no`
    assert "put the value in quotes" in str(caught.value)


def test_a_decimal_is_refused_because_yaml_has_already_rewritten_it() -> None:
    with pytest.raises(DeckError, match="put the value in quotes"):
        normalize_settings({"title": 1.1}, origin="deck.yml")  # what YAML makes of `1.10`
    assert normalize_settings({"title": 2026}, origin="deck.yml") == {"title": "2026"}


def test_a_config_file_that_is_not_utf8_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "deck.yml"
    path.write_bytes(b"title: caf\xe9\n")
    with pytest.raises(DeckError, match="not valid UTF-8") as caught:
        read_config_file(tmp_path)
    assert str(path) in str(caught.value)
