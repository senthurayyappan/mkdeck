"""The exception and the warning of mkdeck.

Every failure an author can cause (a malformed deck file, an unknown option, a slide that
breaks one of the model rules) is reported as a `DeckError` carrying a message that names
the offending slide and says what to do about it. The CLI catches it and prints the message
without a traceback. A problem that leaves the deck usable, such as a figure that is not
where the slide says it is, is a `DeckWarning` instead; it goes through the `warnings`
module, so `warnings.filterwarnings` can silence it or turn it into an error.
"""

from pathlib import Path

__all__ = ["DeckError", "DeckWarning"]


class DeckError(Exception):
    """A deck could not be read, validated or rendered.

    The string form of the error is `<source>: <slide>: <message>`, with the parts that
    are known. Name the slide with `mkdeck.model.slide_name` so that every message names
    it the same way.

    Attributes:
        message: What went wrong and what the author should do about it.
        slide: The offending slide, already named, or `None` for a deck-level problem.
        source: The deck file or folder the problem came from, or `None`.
    """

    def __init__(self, message: str, *, slide: str | None = None, source: Path | str | None = None) -> None:
        """Create the error.

        Args:
            message: What went wrong and what the author should do about it. Write it as
                a complete sentence with its own subject, because it is also shown
                without the prefix, for example `"This slide has 3 embeds, but a slide
                takes at most 2; move one onto a new slide."`.
            slide: The offending slide, named by `mkdeck.model.slide_name`.
            source: The deck file or folder the problem came from.
        """
        self.message = message
        self.slide = slide
        self.source = str(source) if source is not None else None
        prefix = ": ".join(part for part in (self.source, self.slide) if part)
        super().__init__(f"{prefix}: {message}" if prefix else message)


class DeckWarning(UserWarning):
    """A problem that leaves the deck usable, such as an embed that is not on disk."""
