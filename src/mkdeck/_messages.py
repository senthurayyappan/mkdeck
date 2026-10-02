"""Helpers that word what mkdeck tells the author.

That is a warning, and a hint at the right name.
"""

import difflib
import warnings
from collections.abc import Iterable

from mkdeck.errors import DeckWarning

__all__ = ["install_warning_formatter", "suggest", "warn_deck"]


def warn_deck(message: str) -> None:
    """Raise a `DeckWarning`.

    This is the one way the library reports a non-fatal problem.

    Args:
        message: A complete sentence saying what is wrong and what it affects.
    """
    warnings.warn(message, DeckWarning, stacklevel=3)


_standard_format = warnings.formatwarning


def _format_warning(
    message: Warning | str,
    category: type[Warning],
    filename: str,
    lineno: int,
    line: str | None = None,
) -> str:
    """Write a `DeckWarning` as one line.

    Any other warning is written the standard way.
    """
    if issubclass(category, DeckWarning):
        return f"mkdeck: warning: {message}\n"
    return _standard_format(message, category, filename, lineno, line)


def install_warning_formatter() -> None:
    """Show a `DeckWarning` as `mkdeck: warning: <message>`.

    It is shown every time it happens.

    A command line tool calls this once at start-up. Other warnings keep the
    standard format, and calling it again changes nothing.
    """
    warnings.formatwarning = _format_warning  # ty: ignore[invalid-assignment]
    warnings.simplefilter("always", DeckWarning)


def suggest(name: str, options: Iterable[str], *, noun: str = "keys") -> str:
    """Write the "the keys are ..." half of an unknown-name message.

    Args:
        name: The name the author wrote.
        options: The names that are accepted.
        noun: What the names are called in the message.

    Returns:
        A sentence listing the accepted names, with a closest match when there
        is one.
    """
    choices = list(options)
    close = difflib.get_close_matches(name, choices, n=1)
    listing = ", ".join(choices)
    if close:
        return f'Did you mean "{close[0]}"? The {noun} are: {listing}.'
    return f"The {noun} are: {listing}."
