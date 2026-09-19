"""The slide model: the one intermediate representation of a deck.

The Markdown parser in :mod:`mkdeck.markdown` produces these dataclasses and the Python
API builds them directly, so both paths render through the same code. Nothing here
touches the filesystem or emits HTML; it only holds the deck and states the rules a deck
has to keep.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from mkdeck.errors import DeckError

if TYPE_CHECKING:  # mkdeck.config imports this module, so the name is only for annotations.
    from mkdeck.config import DeckConfig

Layout = Literal["auto", "title", "statement", "figures", "table"]
"""How a slide is laid out. ``"auto"`` is resolved by :func:`resolve_layout`."""

EmbedKind = Literal["auto", "iframe", "image", "rollout"]
"""How an embed is drawn. ``"auto"`` is resolved by :func:`resolve_embed_kind`."""

LAYOUTS: tuple[Layout, ...] = ("auto", "title", "statement", "figures", "table")
"""Every accepted value of :attr:`Slide.layout`."""

EMBED_KINDS: tuple[EmbedKind, ...] = ("auto", "iframe", "image", "rollout")
"""Every accepted value of :attr:`Embed.kind`."""

MAX_EMBEDS = 2
"""The number of embeds a single slide can hold."""

IFRAME_SUFFIXES: tuple[str, ...] = (".html", ".htm")
"""The file suffixes that an ``"auto"`` embed draws as an iframe."""

ROLLOUT_SUFFIXES: tuple[str, ...] = (".rollout", ".rbundle")
"""The file suffixes that an ``"auto"`` embed draws in the rollout viewer.

``.rollout`` is what :mod:`mkdeck.rollout` writes; ``.rbundle`` is the whole
bundle an artifacts server holds, which the same viewer reads unconverted.
"""

REMOTE_SCHEMES: tuple[str, ...] = ("http", "https")
"""The URL schemes an embed source may carry; everything else must be a relative path."""

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_URL_SCHEME = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*):(?://)?")


@dataclass(slots=True)
class Embed:
    """A figure on a slide: an iframe page, an image or an animation.

    Attributes:
        src: The page or image, relative to the deck source folder. An ``http`` or
            ``https`` URL is also accepted; an absolute path is not.
        label: The caption drawn above the frame, or ``None`` for no caption.
        kind: ``"iframe"``, ``"image"``, or ``"auto"`` to pick from the suffix of ``src``.
    """

    src: str
    label: str | None = None
    kind: EmbedKind = "auto"


@dataclass(slots=True)
class Table:
    """A table on a slide.

    Attributes:
        columns: The header cells, at least one.
        rows: The body rows; every row holds one cell per column.
    """

    columns: list[str]
    rows: list[list[str]]


@dataclass(slots=True)
class Slide:
    """One slide of a deck.

    Attributes:
        id: A stable identifier, emitted as ``data-id``, or ``None``.
        layout: How the slide is laid out; ``"auto"`` picks from the content.
        title: The heading, rendered only on ``layout="title"``.
        sentence: The visible headline. Inline ``$...$`` math is allowed.
        bullets: A compact list drawn under the sentence.
        math: Display formulas, one per line, drawn above the sentence.
        embeds: The figures on the slide, at most :data:`MAX_EMBEDS` of them.
        table: The table on the slide, or ``None``.
        html: Raw body HTML that replaces everything above it. The escape hatch.
        notes: Speaker notes, shown in reveal's presenter view.
        date: On ``layout="title"``, the date that restamps every later slide.
        classes: Extra CSS classes put on the ``<section>``.
    """

    id: str | None = None
    layout: Layout = "auto"
    title: str | None = None
    sentence: str | None = None
    bullets: list[str] = field(default_factory=list)
    math: list[str] = field(default_factory=list)
    embeds: list[Embed] = field(default_factory=list)
    table: Table | None = None
    html: str | None = None
    notes: str | None = None
    date: str | None = None
    classes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Deck:
    """A whole deck.

    Attributes:
        title: The deck title, shown on the generated opening slide.
        date: The deck date, shown on the opening slide and in the chrome.
        theme: The name of the theme stylesheet to link.
        slides: The slides, in the order they are shown.
        extra_css: Extra stylesheets, linked after the theme.
        extra_js: Extra scripts, loaded after ``mkdeck.js``.
        reveal: Options merged into ``Reveal.initialize``.
        title_slide: Whether to generate the opening title slide.
    """

    title: str
    date: str | None = None
    theme: str = "minimal"
    slides: list[Slide] = field(default_factory=list)
    extra_css: list[str] = field(default_factory=list)
    extra_js: list[str] = field(default_factory=list)
    reveal: dict[str, Any] = field(default_factory=dict)
    title_slide: bool = True

    # build and serve import inside the method body on purpose: mkdeck.build and
    # mkdeck.server both import this module, so a module-scope import would be circular.

    def build(
        self,
        out: Path | str = "site",
        *,
        config: "DeckConfig | None" = None,
        source: Path | None = None,
        single_file: bool = False,
    ) -> Path:
        """Write this deck to an output folder.

        Args:
            out: The output folder, or the HTML file when ``single_file`` is set.
            config: The merged deck configuration.
            source: The folder the deck's assets live in.
            single_file: True to inline every stylesheet and script.

        Returns:
            The path of the written HTML document.
        """
        from mkdeck.build import build_deck

        return build_deck(self, out, config=config, source=source, single_file=single_file)

    def serve(
        self,
        *,
        config: "DeckConfig | None" = None,
        source: Path | None = None,
        host: str = "127.0.0.1",
        port: int = 5020,
        open_browser: bool = False,
        reload: bool = True,
    ) -> None:
        """Serve this deck until interrupted.

        Args:
            config: The merged deck configuration.
            source: The folder the deck's assets live in; it is watched when given.
            host: The interface to bind.
            port: The port to bind.
            open_browser: True to open the deck in a browser once it is up.
            reload: True to watch ``source`` and push reloads.
        """
        from mkdeck.server import serve_deck

        serve_deck(
            self,
            config=config,
            source=source,
            host=host,
            port=port,
            open_browser=open_browser,
            reload=reload,
        )


def slide_name(slide: Slide, index: int) -> str:
    """Name a slide for an error message.

    Args:
        slide: The slide to name.
        index: Its zero-based position in the deck.

    Returns:
        ``slide 4 "g3-paired"`` when the slide carries an id, ``slide 4`` otherwise.
    """
    if slide.id:
        return f'slide {index + 1} "{slide.id}"'
    return f"slide {index + 1}"


def resolve_layout(slide: Slide) -> Layout:
    """Resolve ``layout="auto"`` from the content of a slide.

    Embeds win over a table, and a slide with neither is a statement. A layout the
    author set is returned unchanged.

    Args:
        slide: The slide to resolve.

    Returns:
        One of ``"title"``, ``"statement"``, ``"figures"`` or ``"table"``.
    """
    if slide.layout != "auto":
        return slide.layout
    if slide.embeds:
        return "figures"
    if slide.table is not None:
        return "table"
    return "statement"


def resolve_embed_kind(embed: Embed) -> Literal["iframe", "image", "rollout"]:
    """Resolve ``kind="auto"`` from the suffix of the embed source.

    Args:
        embed: The embed to resolve.

    Returns:
        ``"rollout"`` for a ``.rollout`` or ``.rbundle`` source, ``"iframe"``
        for an ``.html`` or ``.htm`` one, ``"image"`` for everything else.
    """
    if embed.kind != "auto":
        return embed.kind
    suffix = PurePosixPath(embed.src.split("?", 1)[0].split("#", 1)[0]).suffix.lower()
    if suffix in ROLLOUT_SUFFIXES:
        return "rollout"
    return "iframe" if suffix in IFRAME_SUFFIXES else "image"


def validate_src(src: str) -> str | None:
    """Check that an embed source stays inside the deck source folder.

    Args:
        src: The source to check.

    Returns:
        The reason the source is rejected, or ``None`` when it is fine.
    """
    text = src.strip()
    if not text:
        return "an embed with an empty src; point it at a page or an image under the deck folder."
    scheme = _URL_SCHEME.match(text)
    if _WINDOWS_DRIVE.match(text):
        return f'an embed with the absolute src "{src}"; make it relative to the deck folder.'
    if scheme is not None and scheme.group("scheme").lower() not in REMOTE_SCHEMES:
        return (
            f'an embed with the src "{src}", whose "{scheme.group("scheme")}:" scheme is not supported; '
            "use a path relative to the deck folder, or an http(s) URL."
        )
    if scheme is not None:
        return None
    if text.startswith(("/", "\\")):
        return f'an embed with the absolute src "{src}"; make it relative to the deck folder.'
    depth = 0
    for part in text.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return (
                    f'an embed with the src "{src}", which leaves the deck folder; copy the file under the deck folder.'
                )
        else:
            depth += 1
    return None


def validate_slide(slide: Slide, *, index: int, source: Path | str | None = None) -> None:
    """Check one slide against the rules of the model.

    Args:
        slide: The slide to check.
        index: Its zero-based position in the deck, used to name it.
        source: The deck file or folder, used in the error message.

    Raises:
        DeckError: If the layout, the embeds or the table of the slide break a rule.
    """
    name = slide_name(slide, index)

    def fail(message: str) -> DeckError:
        return DeckError(message, slide=name, source=source)

    if slide.layout not in LAYOUTS:
        raise fail(
            f'has the layout "{slide.layout}", which is not one of {", ".join(LAYOUTS)}; use one of those names.'
        )
    if len(slide.embeds) > MAX_EMBEDS:
        raise fail(
            f"has {len(slide.embeds)} embeds, but a slide takes at most {MAX_EMBEDS}; "
            "move the extra figures onto a new slide."
        )
    for embed in slide.embeds:
        if embed.kind not in EMBED_KINDS:
            raise fail(
                f'has an embed of kind "{embed.kind}", which is not one of {", ".join(EMBED_KINDS)}; '
                "use one of those names."
            )
        reason = validate_src(embed.src)
        if reason is not None:
            raise fail(f"has {reason}")
    if slide.table is not None:
        _validate_table(slide.table, fail=fail)


def validate_deck(deck: Deck, *, source: Path | str | None = None) -> None:
    """Check every slide of a deck, and check that the slide ids are unique.

    Args:
        deck: The deck to check.
        source: The deck file or folder, used in the error messages.

    Raises:
        DeckError: If a slide breaks a rule, or two slides share an id.
    """
    seen: dict[str, int] = {}
    for index, slide in enumerate(deck.slides):
        validate_slide(slide, index=index, source=source)
        if slide.id:
            first = seen.get(slide.id)
            if first is not None:
                raise DeckError(
                    f"repeats the id of slide {first + 1}; give every slide its own id, or drop one of the two.",
                    slide=slide_name(slide, index),
                    source=source,
                )
            seen[slide.id] = index


def _validate_table(table: Table, *, fail: Callable[[str], DeckError]) -> None:
    """Check the columns and rows of a table.

    Args:
        table: The table to check.
        fail: A callable that turns a message into a :class:`DeckError`.

    Raises:
        DeckError: If the table has no columns, or a row does not match them.
    """
    if not table.columns:
        raise fail("has a table with no columns; give the table a header row.")
    width = len(table.columns)
    for number, row in enumerate(table.rows, start=1):
        if len(row) != width:
            raise fail(
                f"has a table whose row {number} holds {len(row)} cells but the header holds {width}; "
                "give every row one cell per column."
            )
