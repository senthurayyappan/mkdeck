"""The slide model: the one intermediate representation of a deck.

The Markdown parser in `mkdeck.markdown` produces these dataclasses and the Python API
builds them directly, so both paths render through the same code. Nothing here emits HTML
or reads a file; it only holds the deck and states the rules a deck has to keep.
"""

from dataclasses import dataclass, field
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any, Literal, get_args

from mkdeck.errors import DeckError
from mkdeck.paths import asset_path_error, local_path, theme_error, validate_src

__all__ = [
    "DEFAULT_UNITS",
    "EMBED_KINDS",
    "LAYOUTS",
    "MAX_EMBEDS",
    "ROLLOUT_SUFFIXES",
    "Deck",
    "Embed",
    "EmbedKind",
    "Layout",
    "Slide",
    "Table",
    "deck_has_rollouts",
    "resolve_embed_kind",
    "resolve_layout",
    "slide_name",
    "validate_deck",
    "validate_slide",
]

Layout = Literal["auto", "title", "statement", "figures", "table"]
"""How a slide is laid out. `"auto"` is resolved by `resolve_layout`."""

EmbedKind = Literal["auto", "iframe", "image", "rollout"]
"""How an embed is drawn. `"auto"` is resolved by `resolve_embed_kind`."""

LAYOUTS: tuple[Layout, ...] = get_args(Layout)
"""Every accepted value of `Slide.layout`."""

EMBED_KINDS: tuple[EmbedKind, ...] = get_args(EmbedKind)
"""Every accepted value of `Embed.kind`."""

MAX_EMBEDS = 2
"""The number of embeds a single slide can hold."""

ROLLOUT_SUFFIXES: tuple[str, ...] = (".rollout", ".rbundle")
"""The file suffixes that an `"auto"` embed draws in the rollout viewer.

`.rollout` is what `mkdeck.rollout` writes; a whole `.rbundle`, meshes included, is read
unconverted by the same viewer.
"""

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
"""The units a number may carry and still be highlighted, when a deck does not set its own.

The order does not matter: the renderer tries the longest spelling first.
"""


@dataclass(slots=True)
class Embed:
    """A figure on a slide: an iframe page, an image or an animation.

    Attributes:
        src: The page or image, relative to the deck source folder. An `http` or
            `https` URL is also accepted; an absolute path is not. A query or fragment,
            as in `plot.html?seed=2`, is kept in the document and left off the file name.
        label: The caption drawn above the frame, or `None` for no caption.
        kind: `"iframe"`, `"image"` or `"rollout"`, or `"auto"` to pick from the suffix
            of `src`.
    """

    src: str
    label: str | None = None
    kind: EmbedKind = "auto"


@dataclass(slots=True)
class Table:
    """A table on a slide.

    Attributes:
        columns: The header cells, at least one. Each is shown with `str()`.
        rows: The body rows; every row holds one cell per column, each shown with `str()`.
    """

    columns: list[str]
    rows: list[list[str]]


@dataclass(slots=True)
class Slide:
    """One slide of a deck.

    Attributes:
        id: A stable identifier, emitted as `data-id`, or `None`.
        layout: How the slide is laid out; `"auto"` picks from the content.
        title: The heading, drawn above the rest of the slide. A slide that holds
            nothing else is a title slide.
        sentence: The visible headline. Inline Markdown and `$...$` math are allowed,
            and so is an HTML element, which is kept as written.
        bullets: A compact list drawn under the sentence, with the same inline syntax.
        math: Display formulas, one per line, drawn above the sentence.
        embeds: The figures on the slide, at most `MAX_EMBEDS` of them. A slide takes
            figures or a table, not both.
        table: The table on the slide, or `None`.
        html: Raw HTML drawn with the rest of the slide. The escape hatch.
        notes: Speaker notes, shown in reveal's presenter view.
        date: On `layout="title"`, the date that restamps every later slide.
        classes: Extra CSS classes put on the `<section>`.
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
        units: The units the number highlighting recognises, in any order.
        extra_css: Extra stylesheets, linked after the theme.
        extra_js: Extra scripts, loaded after `mkdeck.js`.
        reveal: Options merged into `Reveal.initialize`.
        title_slide: Whether to generate the opening title slide.
    """

    title: str
    date: str | None = None
    theme: str = "minimal"
    slides: list[Slide] = field(default_factory=list)
    units: list[str] = field(default_factory=lambda: list(DEFAULT_UNITS))
    extra_css: list[str] = field(default_factory=list)
    extra_js: list[str] = field(default_factory=list)
    reveal: dict[str, Any] = field(default_factory=dict)
    title_slide: bool = True

    # build and serve import inside the method body on purpose: mkdeck.build and
    # mkdeck.server both import this module, so a module-scope import would be circular,
    # and `import mkdeck` should not load the file watcher.

    def build(
        self,
        out: Path | str = "site",
        *,
        source: Path | str | None = None,
        single_file: bool = False,
    ) -> Path:
        """Write this deck to an output folder.

        Building again into the same folder brings it up to date: every file is copied
        afresh, and a file the previous build wrote that this one no longer needs is
        removed.

        Args:
            out: The output folder, or the HTML file when `single_file` is set and the
                path ends in `.html`.
            source: The folder the deck's assets live in; the current directory when
                omitted.
            single_file: True to inline every stylesheet and script.

        Returns:
            The path of the written HTML document.

        Raises:
            DeckError: If the deck or a slide breaks a rule of the model, the output
                folder is the source folder, or a file the deck names is outside the
                source folder.
        """
        from mkdeck.build import build_deck

        return build_deck(self, out, source=source, single_file=single_file)

    def serve(
        self,
        *,
        source: Path | str | None = None,
        host: str = "127.0.0.1",
        port: int = 5020,
        open_browser: bool = False,
        reload: bool = True,
    ) -> None:
        """Serve this deck until interrupted.

        Args:
            source: The folder the deck's assets live in; it is watched when given.
            host: The interface to bind.
            port: The port to bind.
            open_browser: True to open the deck in a browser once it is up.
            reload: True to watch `source` and push reloads.

        Raises:
            DeckError: If the deck cannot be rendered or the port is taken.
        """
        from mkdeck.server import serve_deck

        serve_deck(
            self,
            source=source,
            host=host,
            port=port,
            open_browser=open_browser,
            reload=reload,
        )


def slide_name(slide: Slide, index: int | None = None) -> str:
    """Name a slide for an error message.

    Args:
        slide: The slide to name.
        index: Its zero-based position in the deck, or `None` when it is not in one.

    Returns:
        `slide 4 "g3-paired"` when the slide carries an id, `slide 4` otherwise, and
        without the number when the slide has no position.
    """
    number = "" if index is None else f" {index + 1}"
    return f'slide{number} "{slide.id}"' if slide.id else f"slide{number}"


def resolve_layout(slide: Slide) -> Layout:
    """Resolve `layout="auto"` from the content of a slide.

    Embeds win over a table, and a slide with neither is a statement. A layout the
    author set is returned unchanged.

    Args:
        slide: The slide to resolve.

    Returns:
        One of `"title"`, `"statement"`, `"figures"` or `"table"`.
    """
    if slide.layout != "auto":
        return slide.layout
    if slide.embeds:
        return "figures"
    if slide.table is not None:
        return "table"
    return "statement"


def resolve_embed_kind(embed: Embed) -> Literal["iframe", "image", "rollout"]:
    """Resolve `kind="auto"` from the suffix of the embed source.

    Args:
        embed: The embed to resolve.

    Returns:
        `"rollout"` for a `.rollout` or `.rbundle` source, `"iframe"` for an `.html` or
        `.htm` one, `"image"` for everything else. A query or fragment is ignored.
    """
    if embed.kind != "auto":
        return embed.kind
    suffix = PurePosixPath(local_path(embed.src)).suffix.lower()
    if suffix in ROLLOUT_SUFFIXES:
        return "rollout"
    return "iframe" if suffix in {".html", ".htm"} else "image"


def deck_has_rollouts(deck: Deck) -> bool:
    """Say whether any slide draws a rollout.

    The viewer and its renderer are a megabyte, so a deck that shows no robot neither
    loads nor carries them.

    Args:
        deck: The deck to look through.

    Returns:
        True when at least one embed resolves to a rollout.
    """
    return any(resolve_embed_kind(embed) == "rollout" for slide in deck.slides for embed in slide.embeds)


def validate_slide(slide: Slide, *, index: int | None = None, source: Path | str | None = None) -> None:
    """Check one slide against the rules of the model.

    Args:
        slide: The slide to check.
        index: Its zero-based position in the deck, used to name it.
        source: The deck file or folder, used in the error message.

    Raises:
        DeckError: If a field holds the wrong type, or the layout, the embeds or the
            table of the slide break a rule.
    """
    fail = partial(DeckError, slide=slide_name(slide, index), source=source)
    for name in ("id", "title", "sentence", "html", "notes", "date"):
        _expect_text(getattr(slide, name), name, fail=fail, optional=True)
    for name in ("bullets", "math", "classes"):
        _expect_list(getattr(slide, name), name, fail=fail, item=_expect_text)
    _expect_list(slide.embeds, "embeds", fail=fail, item=_expect_embed)
    if slide.table is not None:
        _validate_table(slide.table, fail=fail)
    if slide.layout not in LAYOUTS:
        raise fail(
            f'This slide has the layout "{slide.layout}", which is not one of {", ".join(LAYOUTS)}; '
            "use one of those names."
        )
    if len(slide.embeds) > MAX_EMBEDS:
        raise fail(
            f"This slide has {len(slide.embeds)} embeds, but a slide takes at most {MAX_EMBEDS}; "
            "move the extra figures onto a new slide."
        )
    if slide.embeds and slide.table is not None:
        raise fail(
            "This slide holds both figures and a table, but a slide takes one of the two; move one onto a new slide."
        )


def validate_deck(deck: Deck, *, source: Path | str | None = None) -> None:
    """Check a whole deck: its settings, every slide, and that the slide ids are unique.

    Args:
        deck: The deck to check.
        source: The deck file or folder, used in the error messages.

    Raises:
        DeckError: If a setting or a slide breaks a rule, or two slides share an id.
    """
    fail = partial(DeckError, source=source)
    _expect_text(deck.title, "title", fail=fail)
    _expect_text(deck.date, "date", fail=fail, optional=True)
    _expect_text(deck.theme, "theme", fail=fail)
    reason = theme_error(deck.theme)
    if reason is not None:
        raise fail(reason)
    _expect_list(deck.units, "units", fail=fail, item=_expect_text)
    for key, paths in (("extra_css", deck.extra_css), ("extra_js", deck.extra_js)):
        _expect_list(paths, key, fail=fail, item=_expect_text)
        for path in paths:
            message = asset_path_error(path, key=key)
            if message is not None:
                raise fail(message)
    if not isinstance(deck.reveal, dict):
        raise fail(
            f'The deck setting "reveal" has to be a mapping, but it holds a value of type {type(deck.reveal).__name__}.'
        )
    if not isinstance(deck.title_slide, bool):
        raise fail(
            f'The deck setting "title_slide" has to be true or false, not a value of type {type(deck.title_slide).__name__}.'
        )
    if not isinstance(deck.slides, list) or not all(isinstance(slide, Slide) for slide in deck.slides):
        raise fail("The deck's slides have to be a list of Slide objects.")
    seen: dict[str, int] = {}
    for index, slide in enumerate(deck.slides):
        validate_slide(slide, index=index, source=source)
        if slide.id:
            first = seen.get(slide.id)
            if first is not None:
                raise DeckError(
                    f"This slide repeats the id of slide {first + 1}; give every slide its own id, or drop one of the two.",
                    slide=slide_name(slide, index),
                    source=source,
                )
            seen[slide.id] = index


def _expect_text(value: object, name: str, *, fail: partial[DeckError], optional: bool = False) -> None:
    """Check that a field holds text.

    Args:
        value: The value to check.
        name: The field it came from, used in the message.
        fail: Builds the `DeckError` to raise from a message.
        optional: True when `None` is allowed too.

    Raises:
        DeckError: If the value is not text.
    """
    if isinstance(value, str) or (optional and value is None):
        return
    raise fail(f'The field "{name}" has to be text, but it holds a value of type {type(value).__name__}.')


def _expect_list(value: object, name: str, *, fail: partial[DeckError], item: Any) -> None:
    """Check that a field holds a list whose items pass a check.

    Args:
        value: The value to check.
        name: The field it came from, used in the message.
        fail: Builds the `DeckError` to raise from a message.
        item: The check for one item, called as `item(value, name, fail=fail)`.

    Raises:
        DeckError: If the value is not a list, or an item fails its check.
    """
    if not isinstance(value, list):
        raise fail(f'The field "{name}" has to be a list, but it holds a value of type {type(value).__name__}.')
    for entry in value:
        item(entry, name, fail=fail)


def _expect_embed(value: object, name: str, *, fail: partial[DeckError]) -> None:
    """Check one embed of a slide.

    Args:
        value: The embed to check.
        name: The field it came from, used in the message.
        fail: Builds the `DeckError` to raise from a message.

    Raises:
        DeckError: If the embed is not an `Embed`, or its src, label or kind is wrong.
    """
    if not isinstance(value, Embed):
        raise fail(
            f'The field "{name}" has to hold Embed objects, but it holds a value of type {type(value).__name__}.'
        )
    _expect_text(value.src, "src", fail=fail)
    _expect_text(value.label, "label", fail=fail, optional=True)
    if value.kind not in EMBED_KINDS:
        raise fail(
            f'This slide has an embed of kind "{value.kind}", which is not one of {", ".join(EMBED_KINDS)}; '
            "use one of those names."
        )
    reason = validate_src(value.src)
    if reason is not None:
        raise fail(reason)


def _validate_table(table: object, *, fail: partial[DeckError]) -> None:
    """Check the columns and rows of a table.

    Args:
        table: The table to check.
        fail: Builds the `DeckError` to raise from a message.

    Raises:
        DeckError: If the table has no columns, or a row does not match them.
    """
    if not isinstance(table, Table) or not isinstance(table.columns, list) or not isinstance(table.rows, list):
        raise fail("This slide has a table that is not a Table of a list of columns and a list of rows.")
    if not table.columns:
        raise fail("This slide has a table with no columns; give the table a header row.")
    width = len(table.columns)
    for number, row in enumerate(table.rows, start=1):
        if not isinstance(row, list) or len(row) != width:
            held = f"{len(row)} cells" if isinstance(row, list) else "no list of cells"
            raise fail(
                f"This slide has a table whose row {number} holds {held} but the header holds {width}; "
                "give every row one cell per column."
            )
