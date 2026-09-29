"""Read YAML and coerce its values, for the frontmatter, `deck.yml` and slide options.

Every failure is a `DeckError` whose message says which key held what, so the author sees
the mistake in their own words rather than a YAML or type error.
"""

import datetime as dt
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from mkdeck.errors import DeckError

__all__ = ["Fail", "coerce_bool", "coerce_mapping", "coerce_text", "coerce_text_list", "describe", "parse_yaml"]

Fail = Callable[[str], DeckError]
"""Turns a message into the `DeckError` to raise, with the file and slide already filled in."""


def parse_yaml(text: str, *, origin: Path | str) -> Any:
    """Parse YAML and report a failure as a `DeckError`.

    Args:
        text: The YAML source.
        origin: The file the source came from, used in the error message.

    Returns:
        Whatever the YAML holds, which may be `None` for an empty document.

    Raises:
        DeckError: If the YAML cannot be parsed.
    """
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        detail = str(error).replace("\n", " ").strip()
        raise DeckError(f"The YAML could not be read: {detail}", source=origin) from error


def coerce_text(value: Any, *, key: str, fail: Fail) -> str:
    """Coerce a YAML scalar to text.

    A bare YAML date such as `2026-09-18` arrives as a `datetime.date`, so it is written
    back out in ISO form rather than rejected. A whole number is kept as written. A
    decimal is refused, because YAML has already turned `1.10` into `1.1`, and so is a
    bare `no`, `yes` or `on`, which YAML reads as true or false.

    Args:
        value: The value to coerce.
        key: The key it was written under, used in the error message.
        fail: A callable that turns a message into a `DeckError`.

    Returns:
        The value as text.

    Raises:
        DeckError: If the value is not a scalar.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, bool) or not isinstance(value, int):
        hint = ""
        if isinstance(value, bool | float):
            hint = (
                " YAML reads a bare no, yes or on as true or false and 1.10 as the number 1.1; "
                "put the value in quotes to keep it as written."
            )
        raise fail(f'The key "{key}" holds {describe(value)}, but a piece of text was expected.{hint}')
    return str(value)


def coerce_text_list(value: Any, *, key: str, fail: Fail) -> list[str]:
    """Coerce a YAML scalar or sequence to a list of text.

    Args:
        value: The value to coerce. A lone scalar becomes a one-item list.
        key: The key it was written under, used in the error message.
        fail: A callable that turns a message into a `DeckError`.

    Returns:
        The value as a list of text.

    Raises:
        DeckError: If the value, or one of its items, is not a scalar.
    """
    if isinstance(value, Mapping):
        raise fail(f'The key "{key}" holds a mapping, but a list of text was expected.')
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        return [coerce_text(value, key=key, fail=fail)]
    return [coerce_text(item, key=key, fail=fail) for item in value]


def coerce_bool(value: Any, *, key: str, fail: Fail) -> bool:
    """Coerce a YAML value to a boolean.

    Args:
        value: The value to coerce.
        key: The key it was written under, used in the error message.
        fail: A callable that turns a message into a `DeckError`.

    Returns:
        The value as a boolean.

    Raises:
        DeckError: If the value is not a boolean.
    """
    if isinstance(value, bool):
        return value
    raise fail(f'The key "{key}" holds {describe(value)}, but true or false was expected.')


def coerce_mapping(value: Any, *, key: str, fail: Fail) -> dict[str, Any]:
    """Coerce a YAML value to a mapping.

    Args:
        value: The value to coerce.
        key: The key it was written under, used in the error message.
        fail: A callable that turns a message into a `DeckError`.

    Returns:
        The value as a dictionary.

    Raises:
        DeckError: If the value is not a mapping.
    """
    if isinstance(value, Mapping):
        return {str(name): item for name, item in value.items()}
    raise fail(f'The key "{key}" holds {describe(value)}, but a mapping was expected.')


def describe(value: Any) -> str:
    """Name the shape of a value for an error message.

    Args:
        value: The value to describe.

    Returns:
        A short phrase such as `a list` or `the number 3`.
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
