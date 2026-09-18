import datetime as dt
from pathlib import Path

import pytest

from mkdeck.config import (
    DEFAULT_UNITS,
    DeckConfig,
    apply_config,
    find_config_file,
    load_config,
    normalize_config,
    read_yaml_mapping,
)
from mkdeck.errors import DeckError
from mkdeck.model import Deck

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


def test_defaults_match_the_reference_deck() -> None:
    config = DeckConfig()
    assert config.title == "Slide Deck"
    assert config.theme == "minimal"
    assert config.date is None
    assert config.title_slide is True
    assert config.units == list(DEFAULT_UNITS)
    assert config.extra_css == []
    assert config.reveal == {}


def test_default_units_keep_the_longest_first() -> None:
    assert DEFAULT_UNITS[0] == "N m s/rad"
    assert DEFAULT_UNITS.index("N m") > DEFAULT_UNITS.index("N m s/rad")
    assert DEFAULT_UNITS.index("m") > DEFAULT_UNITS.index("mm")
    assert "body weights" in DEFAULT_UNITS


def test_from_mapping_reads_the_barkour_settings(tmp_path: Path) -> None:
    config = DeckConfig.from_mapping(read_yaml_mapping(write(tmp_path, "deck.yml", DECK_YML)), origin="deck.yml")
    assert config.title.startswith("Barkour vault")
    assert config.date == "2026-09-16"
    assert config.units == ["N m s/rad", "body weights", "N m", "percent"]
    assert config.extra_css == ["assets/lab.css"]
    assert config.reveal == {"hash": True, "transition": "none"}


def test_a_bare_yaml_date_becomes_iso_text() -> None:
    config = DeckConfig.from_mapping({"date": dt.date(2026, 9, 18)}, origin="deck.md")
    assert config.date == "2026-09-18"


def test_a_lone_extra_stylesheet_becomes_a_list() -> None:
    config = DeckConfig.from_mapping({"extra_css": "assets/lab.css"}, origin="deck.yml")
    assert config.extra_css == ["assets/lab.css"]


def test_a_null_value_falls_back_to_the_default() -> None:
    config = DeckConfig.from_mapping({"date": None, "theme": None}, origin="deck.yml")
    assert config.date is None
    assert config.theme == "minimal"


def test_an_unknown_key_is_an_error_that_suggests_the_right_one() -> None:
    with pytest.raises(DeckError) as caught:
        normalize_config({"them": "minimal"}, origin="deck.yml")
    message = str(caught.value)
    assert message.startswith('deck.yml: has the unknown key "them".')
    assert 'Did you mean "theme"?' in message


def test_an_unknown_key_without_a_near_match_lists_the_keys() -> None:
    with pytest.raises(DeckError) as caught:
        normalize_config({"slides": []}, origin="deck.yml")
    assert "The keys are: title, date, theme, units," in str(caught.value)


def test_a_value_of_the_wrong_shape_is_an_error() -> None:
    with pytest.raises(DeckError, match="where true or false was expected"):
        normalize_config({"title_slide": "yes"}, origin="deck.yml")
    with pytest.raises(DeckError, match="where a mapping was expected"):
        normalize_config({"reveal": ["hash"]}, origin="deck.yml")
    with pytest.raises(DeckError, match="where a list of text was expected"):
        normalize_config({"units": {"N m": True}}, origin="deck.yml")
    with pytest.raises(DeckError, match="where a piece of text was expected"):
        normalize_config({"title": ["a", "b"]}, origin="deck.yml")


def test_a_deck_without_a_config_file_takes_the_defaults(tmp_path: Path) -> None:
    source = write(tmp_path, "deck.md", "# Quadruped Vault Runs\n")
    assert find_config_file(source) is None
    assert load_config(source) == DeckConfig()


def test_the_config_file_is_found_beside_the_markdown_and_by_the_folder(tmp_path: Path) -> None:
    write(tmp_path, "deck.yml", DECK_YML)
    source = write(tmp_path, "deck.md", "# Quadruped Vault Runs\n")
    assert find_config_file(source) == tmp_path / "deck.yml"
    assert find_config_file(tmp_path) == tmp_path / "deck.yml"
    assert load_config(source).date == "2026-09-16"


def test_the_yaml_suffix_is_accepted_too(tmp_path: Path) -> None:
    write(tmp_path, "deck.yaml", "title: Quadruped Vault Runs\n")
    assert find_config_file(tmp_path) == tmp_path / "deck.yaml"


def test_the_frontmatter_wins_over_the_config_file(tmp_path: Path) -> None:
    write(tmp_path, "deck.yml", DECK_YML)
    source = write(tmp_path, "deck.md", "")
    config = load_config(source, frontmatter={"date": "2026-09-18", "title_slide": False})
    assert config.date == "2026-09-18"
    assert config.title_slide is False
    assert config.title.startswith("Barkour vault")
    assert config.units == ["N m s/rad", "body weights", "N m", "percent"]


def test_the_two_reveal_mappings_are_merged_option_by_option(tmp_path: Path) -> None:
    write(tmp_path, "deck.yml", DECK_YML)
    source = write(tmp_path, "deck.md", "")
    config = load_config(source, frontmatter={"reveal": {"transition": "fade"}})
    assert config.reveal == {"hash": True, "transition": "fade"}


def test_a_bad_key_names_the_file_it_came_from(tmp_path: Path) -> None:
    path = write(tmp_path, "deck.yml", "titel: Quadruped Vault Runs\n")
    source = write(tmp_path, "deck.md", "")
    with pytest.raises(DeckError, match=str(path)):
        load_config(source)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(DeckError, match=r"other\.md"):
        load_config(write(other, "other.md", ""), frontmatter={"titel": "x"})


def test_unreadable_yaml_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path, "deck.yml", "title: [unclosed\n")
    with pytest.raises(DeckError, match="could not be read"):
        read_yaml_mapping(path)


def test_a_config_file_that_is_not_a_mapping_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path, "deck.yml", "- Quadruped Vault Runs\n")
    with pytest.raises(DeckError, match="where a mapping of deck settings was expected"):
        read_yaml_mapping(path)


def test_an_empty_config_file_is_an_empty_mapping(tmp_path: Path) -> None:
    assert read_yaml_mapping(write(tmp_path, "deck.yml", "\n")) == {}


def test_apply_config_puts_the_merged_settings_on_the_deck() -> None:
    deck = Deck(title="Slide Deck")
    config = DeckConfig(title="Quadruped Vault Runs", date="2026-09-18", theme="dark", title_slide=False)
    apply_config(deck, config)
    assert deck.title == "Quadruped Vault Runs"
    assert deck.date == "2026-09-18"
    assert deck.theme == "dark"
    assert deck.title_slide is False
