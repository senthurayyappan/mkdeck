"""The single user-facing exception of mkdeck.

Every failure an author can cause — a malformed deck file, an unknown option, a slide
that breaks one of the model rules — is reported as a :class:`DeckError` carrying a
message that names the offending slide and says what to do about it. The CLI catches it
and prints the message without a traceback.
"""

from pathlib import Path


class DeckError(Exception):
    """A deck could not be read, validated or rendered.

    The string form of the error is ``<source>: <slide>: <message>``, with the parts
    that are known. Build it with :func:`mkdeck.model.slide_name` so that every message
    names the offending slide the same way.

    Attributes:
        message: What went wrong and what the author should do about it.
        slide: The offending slide, already named, or ``None`` for a deck-level problem.
        source: The deck file or folder the problem came from, or ``None``.
    """

    def __init__(self, message: str, *, slide: str | None = None, source: Path | str | None = None) -> None:
        """Create the error.

        Args:
            message: What went wrong and what the author should do about it. Write it as
                a continuation of the prefix, for example ``"has 3 embeds, but a slide
                takes at most 2; move one onto a new slide."``.
            slide: The offending slide, named by :func:`mkdeck.model.slide_name`.
            source: The deck file or folder the problem came from.
        """
        self.message = message
        self.slide = slide
        self.source = str(source) if source is not None else None
        super().__init__(self._format())

    def _format(self) -> str:
        prefix = ": ".join(part for part in (self.source, self.slide) if part)
        return f"{prefix}: {self.message}" if prefix else self.message

    def __str__(self) -> str:
        """Return the full message, source and slide included.

        Returns:
            The message the CLI prints.
        """
        return self._format()
