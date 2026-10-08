"""Write an edit made on a served slide back into its Markdown file.

The dev server marks each piece of slide text it can trace to one place in
the deck file. The page sends back the slide, the key of the piece, the text
it showed, and the new text. The edit is written only if the file still holds
the text the page showed at that place, so an edit made in an editor in the
meantime is never overwritten.

What the new text means depends on the piece:

* A title is one line; line breaks become spaces.
* A sentence is Markdown, so a blank line starts a new paragraph.
* A bullet becomes one bullet per line, and empty text deletes it.
* A table cell is one line; a `|` in it is escaped.
"""

import os
import re
import tempfile
from pathlib import Path

from mkdeck.errors import DeckError
from mkdeck.markdown import TextSource, locate_text
from mkdeck.paths import read_text

__all__ = ["EditConflictError", "apply_edit", "edit_file"]

_HEADING = re.compile(r"^[ \t]*#{1,6}(?:[ \t]+|$)")
_MARKER = re.compile(r"^[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+")
_SPACES = re.compile(r"\s+")
_CHANGED = (
    "The deck file changed since this page was built, so the edit was not "
    "saved; wait for the page to reload and edit it again."
)


class EditConflictError(DeckError):
    """The deck file no longer holds the text the page showed."""


def apply_edit(
    text: str, *, slide: int, key: str, expected: str, replacement: str
) -> str:
    """Replace one piece of slide text in the source of a deck file.

    Args:
        text: The whole Markdown file.
        slide: The index of the slide among the parsed slides of the deck.
        key: The key of the piece, as `mkdeck.markdown.locate_text` names it.
        expected: The text the page showed for the piece.
        replacement: The new text.

    Returns:
        The whole file with the edit made. Its line endings and byte-order
        mark are kept.

    Raises:
        EditConflictError: If the file no longer holds `expected` at that place.
        DeckError: If the piece cannot be edited from the page.
    """
    slides = locate_text(text, source="deck")
    if not 0 <= slide < len(slides):
        raise EditConflictError(_CHANGED)
    found = slides[slide].get(key)
    if found is None:
        raise DeckError(
            "This text is not written in one place in the deck file: it is "
            "set in the slide options, or shares its paragraph or list item "
            "with something else. Edit it in the file."
        )
    if found.text != expected:
        raise EditConflictError(_CHANGED)
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = (
        text.removeprefix(bom)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    )
    start, end = found.lines
    lines[start:end] = _rewrite(key, found, lines[start:end], replacement)
    return bom + newline.join(lines)


def _rewrite(
    key: str, found: TextSource, lines: list[str], replacement: str
) -> list[str]:
    """Write the new source lines of one piece.

    Args:
        key: The key of the piece.
        found: Where the piece sits.
        lines: Its current source lines.
        replacement: The new text.

    Returns:
        The lines that take the place of `lines`.

    Raises:
        DeckError: If the piece cannot hold the new text.
    """
    kind = key.split(":", 1)[0]
    flat = _SPACES.sub(" ", replacement).strip()
    if kind == "title":
        if not flat:
            raise DeckError("A title cannot be empty; delete it in the file.")
        prefix = _HEADING.match(lines[0])
        assert prefix is not None  # the parser read a heading on this line
        return [prefix.group(0).rstrip() + " " + flat]
    if kind == "sentence":
        # Trailing spaces would be a hard line break in Markdown, and noise.
        lines = [line.rstrip() for line in replacement.strip().split("\n")]
        return lines if replacement.strip() else []
    if kind == "bullet":
        marker = _MARKER.match(lines[0])
        if marker is None:
            raise DeckError(
                "This bullet does not start on the line of its marker; "
                "edit it in the file."
            )
        prefix = marker.group(0)
        items = [
            _SPACES.sub(" ", line).strip() for line in replacement.split("\n")
        ]
        return [prefix + item for item in items if item]
    if kind == "cell":
        return [_rewrite_cell(lines[0], found, flat)]
    raise DeckError(f'The piece "{key}" cannot be edited from the page.')


def _rewrite_cell(line: str, found: TextSource, text: str) -> str:
    """Replace one cell of a table row.

    Args:
        line: The source line of the row.
        found: Where the cell sits.
        text: The new text of the cell, on one line.

    Returns:
        The new line.

    Raises:
        DeckError: If the row has no cell of its own at that column.
    """
    spans = _cell_spans(line)
    column = found.column if found.column is not None else -1
    if not 0 <= column < len(spans):
        raise DeckError(
            "This cell is not written in the row; add it in the file first."
        )
    start, end = spans[column]
    return line[:start] + " " + text.replace("|", "\\|") + " " + line[end:]


def _cell_spans(line: str) -> list[tuple[int, int]]:
    """Find the cells of a table row.

    The row is split at every `|` that is not escaped, the way markdown-it
    splits it, and the empty pieces before the first pipe and after the last
    are dropped.

    Args:
        line: The source line of the row.

    Returns:
        The start and end of each cell between its pipes.
    """
    left = len(line) - len(line.lstrip())
    right = len(line.rstrip())
    spans: list[tuple[int, int]] = []
    start = left
    escaped = False
    for position in range(left, right):
        character = line[position]
        if character == "|" and not escaped:
            spans.append((start, position))
            start = position + 1
        escaped = character == "\\"
    spans.append((start, right))
    if spans and spans[0][0] == spans[0][1]:
        spans.pop(0)
    if spans and spans[-1][0] == spans[-1][1]:
        spans.pop()
    return spans


def edit_file(
    path: Path, *, slide: int, key: str, expected: str, replacement: str
) -> None:
    """Make one edit in a deck file on disk.

    The file is replaced in one step, so the file watcher never reads it
    half-written.

    Args:
        path: The Markdown file of the deck.
        slide: The index of the slide among the parsed slides of the deck.
        key: The key of the piece.
        expected: The text the page showed for the piece.
        replacement: The new text.

    Raises:
        EditConflictError: If the file no longer holds `expected` at that place.
        DeckError: If the piece cannot be edited, or the file cannot be read
            or written.
    """
    text = read_text(path)
    edited = apply_edit(
        text, slide=slide, key=key, expected=expected, replacement=replacement
    )
    if edited == text:
        return
    handle, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            file.write(edited)
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    except OSError as error:
        Path(temporary).unlink(missing_ok=True)
        raise DeckError(
            f"The edit could not be saved: {error.strerror}.", source=path
        ) from error
