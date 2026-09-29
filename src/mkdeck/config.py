"""Deck settings: `deck.yml` beside the Markdown, the frontmatter, or both.

A deck takes its settings from a `deck.yml` next to its Markdown file and from the YAML
frontmatter that opens the file. Both are optional and the frontmatter wins, key by key,
so a folder of decks can share a `deck.yml` and a single deck can still override one
setting. Each key is a field of `mkdeck.model.Deck`, and this module turns YAML into the
values those fields hold. It validates with the same discipline as the model: an unknown
key is an error naming the file it came from, never a silent ignore.
"""

from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path
from typing import Any

from mkdeck._coerce import (
    Fail,
    coerce_bool,
    coerce_mapping,
    coerce_text,
    coerce_text_list,
    describe,
    parse_yaml,
)
from mkdeck._messages import suggest
from mkdeck.errors import DeckError
from mkdeck.paths import asset_path_error, read_text, theme_error

__all__ = [
    "CONFIG_FILENAMES",
    "CONFIG_KEYS",
    "DEFAULT_TITLE",
    "find_config_file",
    "merge_settings",
    "normalize_settings",
    "read_config_file",
]

DEFAULT_TITLE = "Slide Deck"
"""The title of a deck whose file and `deck.yml` name none."""

CONFIG_FILENAMES: tuple[str, ...] = ("deck.yml", "deck.yaml")
"""The config filenames looked for beside the Markdown, in order."""


def _theme(value: Any, *, key: str, fail: Fail) -> str:
    """Coerce a theme name, and check that a stylesheet of that name ships with mkdeck."""
    theme = coerce_text(value, key=key, fail=fail)
    if (message := theme_error(theme)) is not None:
        raise fail(message)
    return theme


def _asset_paths(value: Any, *, key: str, fail: Fail) -> list[str]:
    """Coerce a list of stylesheet or script paths, and check each stays inside the deck folder."""
    paths = coerce_text_list(value, key=key, fail=fail)
    for path in paths:
        if (message := asset_path_error(path, key=key)) is not None:
            raise fail(message)
    return paths


_COERCERS: dict[str, Callable[..., Any]] = {
    "title": coerce_text,
    "date": coerce_text,
    "theme": _theme,
    "units": coerce_text_list,
    "extra_css": _asset_paths,
    "extra_js": _asset_paths,
    "reveal": coerce_mapping,
    "title_slide": coerce_bool,
}
"""How each setting is read. The keys are the fields of `Deck` that are not its slides."""

CONFIG_KEYS: tuple[str, ...] = tuple(_COERCERS)
"""Every key accepted in `deck.yml` and in the deck frontmatter."""


def normalize_settings(data: Mapping[str, Any], *, origin: Path | str) -> dict[str, Any]:
    """Check one mapping of deck settings and coerce its values.

    Args:
        data: The settings, from `deck.yml` or from the frontmatter.
        origin: The file the settings came from, used in the error messages.

    Returns:
        Only the keys the mapping actually sets, with their values coerced. They are
        the keyword arguments of `mkdeck.model.Deck`.

    Raises:
        DeckError: If a key is unknown or a value has the wrong shape.
    """
    fail = partial(DeckError, source=origin)
    if not isinstance(data, Mapping):
        raise fail(f"The file holds {describe(data)}, but a mapping of deck settings was expected.")
    values: dict[str, Any] = {}
    for key, value in data.items():
        name = str(key)
        if name not in _COERCERS:
            raise fail(f'The file has the unknown key "{name}". {suggest(name, CONFIG_KEYS)}')
        if value is not None:
            values[name] = _COERCERS[name](value, key=name, fail=fail)
    return values


def merge_settings(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Lay one set of settings over another.

    The override wins key by key, except for `reveal`, whose two mappings are merged with
    the override winning per option.

    Args:
        base: Settings from `normalize_settings`, such as those of `deck.yml`.
        override: Settings from `normalize_settings`, such as those of the frontmatter.

    Returns:
        The merged settings.
    """
    merged = {**base, **override}
    if "reveal" in base and "reveal" in override:
        merged["reveal"] = {**base["reveal"], **override["reveal"]}
    return merged


def find_config_file(source: Path) -> Path | None:
    """Find the `deck.yml` that belongs to a deck source.

    Args:
        source: The Markdown file of the deck, or the folder holding it.

    Returns:
        The config file, or `None` when the deck has none.
    """
    folder = source if source.is_dir() else source.parent
    for name in CONFIG_FILENAMES:
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def read_config_file(source: Path) -> dict[str, Any]:
    """Read the `deck.yml` beside a deck, if it has one.

    Args:
        source: The Markdown file of the deck, or the folder holding it.

    Returns:
        The settings the file sets, coerced; empty when there is no file or it is empty.

    Raises:
        DeckError: If the file holds YAML that cannot be read, a mapping of the wrong
            shape, an unknown key, or a value of the wrong shape.
    """
    path = find_config_file(source)
    if path is None:
        return {}
    data = parse_yaml(read_text(path), origin=path)
    return normalize_settings({} if data is None else data, origin=path)
