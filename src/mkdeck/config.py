"""Deck configuration: ``deck.yml`` beside the Markdown, the frontmatter, or both.

A deck takes its settings from a ``deck.yml`` next to its Markdown file and from the YAML
frontmatter that opens the file. Both are optional and the frontmatter wins, key by key,
so a folder of decks can share a ``deck.yml`` and a single deck can still override one
setting. The loader validates with the same discipline as the model: an unknown key is an
error naming the file it came from, never a silent ignore.
"""

import datetime as dt
import difflib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mkdeck.errors import DeckError
from mkdeck.model import Deck

DEFAULT_UNITS: tuple[str, ...] = (
    "N m s/rad",
    "kg m^2",
    "rad/s",
    "body weights",
    "N m",
    "mm",
    "ms",
    "Hz",
    "kg",
    "m",
    "s",
    "percent",
    "degrees",
)
"""The units a number may carry and still be highlighted, longest match first.

The renderer builds the number-highlighting pattern from this list. A deck replaces it
with its own ``units:`` key.
"""

CONFIG_KEYS: tuple[str, ...] = (
    "title",
    "date",
    "theme",
    "units",
    "extra_css",
    "extra_js",
    "reveal",
    "title_slide",
)
"""Every key accepted in ``deck.yml`` and in the deck frontmatter."""

CONFIG_FILENAMES: tuple[str, ...] = ("deck.yml", "deck.yaml")
"""The config filenames looked for beside the Markdown, in order."""


@dataclass(slots=True)
class DeckConfig:
    """The settings of a deck, merged from ``deck.yml`` and the frontmatter.

    Attributes:
        title: The deck title, shown on the generated opening slide.
        date: The deck date, shown on the opening slide and in the chrome.
        theme: The name of the theme stylesheet to link.
        units: The units the number highlighting recognises.
        extra_css: Extra stylesheets, linked after the theme.
        extra_js: Extra scripts, loaded after ``mkdeck.js``.
        reveal: Options merged into ``Reveal.initialize``.
        title_slide: Whether to generate the opening title slide.
    """

    title: str = "Slide Deck"
    date: str | None = None
    theme: str = "minimal"
    units: list[str] = field(default_factory=lambda: list(DEFAULT_UNITS))
    extra_css: list[str] = field(default_factory=list)
    extra_js: list[str] = field(default_factory=list)
    reveal: dict[str, Any] = field(default_factory=dict)
    title_slide: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, origin: Path | str) -> "DeckConfig":
        """Build a config from one mapping of settings.

        Args:
            data: The settings, from ``deck.yml`` or from the frontmatter.
            origin: The file the settings came from, used in the error messages.

        Returns:
            The config, with every key the mapping leaves out at its default.

        Raises:
            DeckError: If a key is unknown or a value has the wrong shape.
        """
        return cls(**normalize_config(data, origin=origin))


def normalize_config(data: Mapping[str, Any], *, origin: Path | str) -> dict[str, Any]:
    """Check one mapping of deck settings and coerce its values.

    Args:
        data: The settings, from ``deck.yml`` or from the frontmatter.
        origin: The file the settings came from, used in the error messages.

    Returns:
        Only the keys the mapping actually sets, with their values coerced.

    Raises:
        DeckError: If a key is unknown or a value has the wrong shape.
    """

    def fail(message: str) -> DeckError:
        return DeckError(message, source=origin)

    if not isinstance(data, Mapping):
        raise fail(f"holds {_describe(data)} where a mapping of deck settings was expected.")
    values: dict[str, Any] = {}
    for key, value in data.items():
        name = str(key)
        if name not in CONFIG_KEYS:
            raise fail(f'has the unknown key "{name}". {suggest(name, CONFIG_KEYS)}')
        if value is None:
            continue
        if name in {"title", "theme", "date"}:
            values[name] = coerce_text(value, key=name, fail=fail)
        elif name in {"units", "extra_css", "extra_js"}:
            values[name] = coerce_text_list(value, key=name, fail=fail)
        elif name == "reveal":
            values[name] = coerce_mapping(value, key=name, fail=fail)
        else:
            values[name] = coerce_bool(value, key=name, fail=fail)
    return values


def find_config_file(source: Path) -> Path | None:
    """Find the ``deck.yml`` that belongs to a deck source.

    Args:
        source: The Markdown file of the deck, or the folder holding it.

    Returns:
        The config file, or ``None`` when the deck has none.
    """
    folder = source if source.is_dir() else source.parent
    for name in CONFIG_FILENAMES:
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def load_config(source: Path, *, frontmatter: Mapping[str, Any] | None = None) -> DeckConfig:
    """Load the settings of a deck from ``deck.yml`` and the frontmatter.

    The frontmatter wins key by key, except for ``reveal``, whose two mappings are merged
    with the frontmatter winning per option.

    Args:
        source: The Markdown file of the deck, or the folder holding it.
        frontmatter: The frontmatter mapping, from
            :func:`mkdeck.markdown.split_frontmatter`.

    Returns:
        The merged config.

    Raises:
        DeckError: If either file holds an unknown key, a value of the wrong shape, or
            YAML that cannot be read.
    """
    values: dict[str, Any] = {}
    config_file = find_config_file(source)
    if config_file is not None:
        values = normalize_config(read_yaml_mapping(config_file), origin=config_file)
    if frontmatter:
        front = normalize_config(frontmatter, origin=source)
        reveal = {**values.get("reveal", {}), **front.get("reveal", {})}
        values.update(front)
        if reveal:
            values["reveal"] = reveal
    return DeckConfig(**values)


def apply_config(deck: Deck, config: DeckConfig) -> None:
    """Copy the merged settings onto a deck, in place.

    The Markdown parser fills a deck from the frontmatter alone, because it never reads
    ``deck.yml``. The builder calls this once the config is merged so that the deck and
    the config agree.

    Args:
        deck: The deck to update.
        config: The merged config.
    """
    deck.title = config.title
    deck.date = config.date
    deck.theme = config.theme
    deck.extra_css = list(config.extra_css)
    deck.extra_js = list(config.extra_js)
    deck.reveal = dict(config.reveal)
    deck.title_slide = config.title_slide


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Read a YAML file that has to hold a mapping.

    Args:
        path: The file to read.

    Returns:
        The mapping, empty when the file is empty.

    Raises:
        DeckError: If the file cannot be read or does not hold a mapping.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise DeckError(f"could not be read: {error.strerror}.", source=path) from error
    data = parse_yaml(raw, origin=path)
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise DeckError(f"holds {_describe(data)} where a mapping of deck settings was expected.", source=path)
    return dict(data)


def parse_yaml(text: str, *, origin: Path | str) -> Any:
    """Parse YAML and report a failure as a :class:`DeckError`.

    Args:
        text: The YAML source.
        origin: The file the source came from, used in the error message.

    Returns:
        Whatever the YAML holds, which may be ``None`` for an empty document.

    Raises:
        DeckError: If the YAML cannot be parsed.
    """
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        detail = str(error).replace("\n", " ").strip()
        raise DeckError(f"holds YAML that could not be read: {detail}", source=origin) from error


def suggest(name: str, options: Iterable[str]) -> str:
    """Write the "the keys are ..." half of an unknown-key message.

    Args:
        name: The key the author wrote.
        options: The keys that are accepted.

    Returns:
        A sentence listing the accepted keys, with a closest match when there is one.
    """
    choices = list(options)
    close = difflib.get_close_matches(name, choices, n=1)
    listing = ", ".join(choices)
    if close:
        return f'Did you mean "{close[0]}"? The keys are: {listing}.'
    return f"The keys are: {listing}."


def coerce_text(value: Any, *, key: str, fail: Callable[[str], DeckError]) -> str:
    """Coerce a YAML scalar to text.

    A bare YAML date such as ``2026-09-18`` arrives as a :class:`datetime.date`, so it is
    written back out in ISO form rather than rejected.

    Args:
        value: The value to coerce.
        key: The key it was written under, used in the error message.
        fail: A callable that turns a message into a :class:`DeckError`.

    Returns:
        The value as text.

    Raises:
        DeckError: If the value is not a scalar.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise fail(f'has {_describe(value)} under "{key}", where a piece of text was expected.')
    return str(value)


def coerce_text_list(value: Any, *, key: str, fail: Callable[[str], DeckError]) -> list[str]:
    """Coerce a YAML scalar or sequence to a list of text.

    Args:
        value: The value to coerce. A lone scalar becomes a one-item list.
        key: The key it was written under, used in the error message.
        fail: A callable that turns a message into a :class:`DeckError`.

    Returns:
        The value as a list of text.

    Raises:
        DeckError: If the value, or one of its items, is not a scalar.
    """
    if isinstance(value, Mapping):
        raise fail(f'has a mapping under "{key}", where a list of text was expected.')
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        return [coerce_text(value, key=key, fail=fail)]
    return [coerce_text(item, key=key, fail=fail) for item in value]


def coerce_bool(value: Any, *, key: str, fail: Callable[[str], DeckError]) -> bool:
    """Coerce a YAML value to a boolean.

    Args:
        value: The value to coerce.
        key: The key it was written under, used in the error message.
        fail: A callable that turns a message into a :class:`DeckError`.

    Returns:
        The value as a boolean.

    Raises:
        DeckError: If the value is not a boolean.
    """
    if isinstance(value, bool):
        return value
    raise fail(f'has {_describe(value)} under "{key}", where true or false was expected.')


def coerce_mapping(value: Any, *, key: str, fail: Callable[[str], DeckError]) -> dict[str, Any]:
    """Coerce a YAML value to a mapping.

    Args:
        value: The value to coerce.
        key: The key it was written under, used in the error message.
        fail: A callable that turns a message into a :class:`DeckError`.

    Returns:
        The value as a dictionary.

    Raises:
        DeckError: If the value is not a mapping.
    """
    if isinstance(value, Mapping):
        return {str(name): item for name, item in value.items()}
    raise fail(f'has {_describe(value)} under "{key}", where a mapping was expected.')


def _describe(value: Any) -> str:
    """Name the shape of a value for an error message.

    Args:
        value: The value to describe.

    Returns:
        A short phrase such as ``a list`` or ``the number 3``.
    """
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return f"the value {str(value).lower()}"
    if isinstance(value, Mapping):
        return "a mapping"
    if isinstance(value, str):
        return f'the text "{value}"'
    if isinstance(value, int | float):
        return f"the number {value}"
    if isinstance(value, Iterable):
        return "a list"
    return f"a value of type {type(value).__name__}"
