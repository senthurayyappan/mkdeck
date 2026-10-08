"""Turn a `mkdeck.model.Deck` into HTML.

This module owns the HTML contract: every element, class and `data-` attribute a
slide emits is decided here, and `assets/mkdeck.js` reads them back. Neither
side may change the contract on its own.

The number highlighting is done here rather than with a client-side regex, so a
deck saved from the browser keeps it. The pattern's negative lookbehind is what
keeps the `2` in `Go2` grey. Inline math is only marked up here, as an empty
`.mkd-math` span carrying its source; KaTeX draws it in the browser.

The text of a sentence, a bullet, a label or a table cell is inline Markdown. An
HTML element written in it, with its closing tag, is copied to the page as
written.
"""

import posixpath
import re
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
)
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from markupsafe import Markup, escape
from mdit_py_plugins.dollarmath import dollarmath_plugin

from mkdeck._messages import warn_deck
from mkdeck.errors import DeckError
from mkdeck.markdown import MATH_RULES
from mkdeck.model import (
    DEFAULT_UNITS,
    Deck,
    Embed,
    Slide,
    Table,
    deck_has_rollouts,
    resolve_embed_kind,
    resolve_layout,
    validate_deck,
)
from mkdeck.paths import (
    ASSET_BASE,
    ASSET_ROOT,
    ASSETS_DIRNAME,
    is_remote,
    local_path,
    relative_url,
)

__all__ = [
    "EDIT_PATH",
    "EXPORT_PATH",
    "RELOAD_PATH",
    "highlight_numbers",
    "render_deck",
    "render_slide",
    "render_text",
]

TEMPLATE_DIR = ASSET_ROOT / "templates"
_TEMPLATE_NAME = "deck.html.jinja"

RELOAD_PATH = "/__mkdeck__/events"
"""Endpoint a live-reload page listens on for rebuild events.

The dev server serves it.
"""

EDIT_PATH = "/__mkdeck__/edit"
"""Endpoint the page posts a text edit to; the dev server serves it."""

EXPORT_PATH = "/__mkdeck__/export"
"""Endpoint the page downloads the deck from as one HTML file."""

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
_TAG_NAME = re.compile(r"</?(?P<name>[A-Za-z][\w-]*)")
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


@lru_cache(maxsize=32)
def _number_pattern(units: tuple[str, ...]) -> re.Pattern[str]:
    """Build the number-highlighting pattern for one unit list.

    Args:
        units: Unit spellings a number may carry, in any order; the longest is
            tried first.

    Returns:
        A compiled pattern matching one standalone number and its unit.
    """
    pattern = r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?"
    if units:
        alternatives = "|".join(
            re.escape(unit) for unit in sorted(units, key=len, reverse=True)
        )
        pattern += rf"(?: ?(?:{alternatives}))?"
    return re.compile(pattern + r"(?![A-Za-z0-9])")


def highlight_numbers(
    text: str, *, units: Sequence[str] = DEFAULT_UNITS
) -> Markup:
    """Wrap every standalone number in `<span class="mkd-num">`.

    A number glued to letters is left alone, so the `2` in `Go2` stays grey.

    Args:
        text: Plain text; it is HTML-escaped on the way out.
        units: Unit spellings a number may carry.

    Returns:
        Escaped markup with the numbers wrapped.
    """
    source = str(text)
    pattern = _number_pattern(tuple(units))
    pieces: list[Markup] = []
    last = 0
    for match in pattern.finditer(source):
        pieces.append(escape(source[last : match.start()]))
        pieces.append(
            Markup('<span class="mkd-num">{}</span>').format(match.group(0))
        )
        last = match.end()
    pieces.append(escape(source[last:]))
    return Markup("").join(pieces)


def _math_span(tex: str, *, block: bool = False) -> Markup:
    """Emit the placeholder KaTeX fills in in the browser.

    The formula source is escaped into `data-tex`, so a KaTeX failure leaves an
    empty span rather than a broken slide; the front-end then writes the source
    in as text.

    Args:
        tex: The formula source.
        block: True for a display formula on a line of its own.

    Returns:
        A `<span class="mkd-math">` element with no text content.
    """
    classes = "mkd-math mkd-math-block" if block else "mkd-math"
    return Markup('<span class="{}" data-tex="{}"></span>').format(
        classes, str(tex)
    )


def _text_rule(
    renderer: RendererHTML,
    tokens: Sequence[Token],
    idx: int,
    options: OptionsDict,
    env: EnvType,
) -> str:
    """Draw a run of text, with its numbers highlighted.

    The highlighting is skipped when the text sits in author HTML.
    """
    token = tokens[idx]
    if token.meta.get("raw") or not env["numbers"]:
        return str(escape(token.content))
    return str(highlight_numbers(token.content, units=env["units"]))


def _html_rule(
    renderer: RendererHTML,
    tokens: Sequence[Token],
    idx: int,
    options: OptionsDict,
    env: EnvType,
) -> str:
    """Draw an HTML tag as written.

    It is drawn as text when `_pair_html` found it has no partner.
    """
    token = tokens[idx]
    return (
        str(escape(token.content))
        if token.meta.get("escape")
        else token.content
    )


def _math_rule(
    renderer: RendererHTML,
    tokens: Sequence[Token],
    idx: int,
    options: OptionsDict,
    env: EnvType,
) -> str:
    """Draw an inline formula as the empty span KaTeX fills in."""
    return str(_math_span(tokens[idx].content))


def _image_rule(
    renderer: RendererHTML,
    tokens: Sequence[Token],
    idx: int,
    options: OptionsDict,
    env: EnvType,
) -> str:
    """Draw an image inside text.

    Say so when it is a file the build will not copy.

    A build copies the `assets` folder and the files of figures, and a figure is
    a paragraph made of images. An image in a bullet or a table cell that sits
    outside `assets` is copied by nothing, so it would break.
    """
    src = str(tokens[idx].attrGet("src") or "")
    if (
        src
        and not is_remote(src)
        and not posixpath.normpath(local_path(src)).startswith(
            f"{ASSETS_DIRNAME}/"
        )
    ):
        warn_deck(
            f'The text holds the image "{src}", which is not copied into the '
            f"build; "
            f"move the file under {ASSETS_DIRNAME}/, or write the image on a "
            f"line of its own so that it becomes a figure."
        )
    return renderer.image(tokens, idx, options, env)


def _build_inline_parser() -> MarkdownIt:
    """Build the parser that renders the text of a sentence, a bullet or a cell.

    Returns:
        A CommonMark inline parser whose text, HTML and math draw the mkdeck
        way. The dollar rule is the one the Markdown parser uses: an opening `$`
        is not followed by a space, and a closing one is not preceded by a space
        or followed by a digit, so "costs $5 and $10" is text. A backslash
        before a dollar sign makes it a literal one.
    """
    md = MarkdownIt("commonmark")
    md.use(dollarmath_plugin, **MATH_RULES)
    md.add_render_rule("text", _text_rule)
    md.add_render_rule("html_inline", _html_rule)
    md.add_render_rule("math_inline", _math_rule)
    md.add_render_rule("image", _image_rule)
    return md


_INLINE = _build_inline_parser()


def _pair_html(children: list[Token]) -> None:
    """Find the HTML elements the author wrote in a run of inline tokens.

    A tag the author closed is an element: it is drawn as written, and the text
    inside it is copied through without number highlighting. A tag left open, or
    a closing tag with no opening one, is not an element, so it is drawn as
    text. Elements of the same name nest.

    Args:
        children: The inline tokens; their `meta` is marked in place.
    """
    open_tags: list[tuple[str, int]] = []
    for index, token in enumerate(children):
        if token.type != "html_inline":
            continue
        found = _TAG_NAME.match(token.content)
        if found is None or token.content.endswith(
            "/>"
        ):  # a comment or a self-closing tag
            continue
        name = found.group("name").lower()
        if name in _VOID_TAGS:
            continue
        if not token.content.startswith("</"):
            open_tags.append((name, index))
            continue
        partner = next(
            (
                at
                for at in range(len(open_tags) - 1, -1, -1)
                if open_tags[at][0] == name
            ),
            None,
        )
        if partner is None:
            token.meta["escape"] = True
            continue
        for _, unmatched in open_tags[partner + 1 :]:
            children[unmatched].meta["escape"] = True
        for inner in children[open_tags[partner][1] : index]:
            inner.meta["raw"] = True
        del open_tags[partner:]
    for _, unmatched in open_tags:
        children[unmatched].meta["escape"] = True


def render_text(
    text: str, *, units: Sequence[str] = DEFAULT_UNITS, numbers: bool = True
) -> Markup:
    """Render one piece of slide text.

    Inline Markdown, inline math and number highlighting are applied.

    The text is inline Markdown, so `**bold**`, `*emphasis*`, `` `code` `` and
    `[links](https://example.org)` work. Text between dollar signs becomes an
    inline `.mkd-math` span, and the text around it keeps its number
    highlighting. An HTML element with its closing tag is copied through as the
    author wrote it, including the text inside it; that is raw HTML, so it is
    not escaped. Anything else that looks like a tag is shown as text.

    Args:
        text: The text to render.
        units: Unit spellings a number may carry.
        numbers: False to leave the numbers alone, which is what a figure label
            and a table header do so that they keep one weight.

    Returns:
        The rendered markup.
    """
    env: dict[str, Any] = {"units": tuple(units), "numbers": numbers}
    tokens = _INLINE.parseInline(str(text), env)
    for token in tokens:
        _pair_html(token.children or [])
    return Markup(_INLINE.renderer.render(tokens, _INLINE.options, env))


def _paragraphs(text: str) -> list[str]:
    """Split a block of text at its blank lines.

    Args:
        text: The text to split.

    Returns:
        One piece per paragraph, blank pieces dropped.
    """
    return [
        piece.strip()
        for piece in _PARAGRAPH_BREAK.split(text.strip())
        if piece.strip()
    ]


def _render_figure(embed: Embed) -> Markup:
    """Render one figure: an optional caption above an iframe or an image.

    A label carries inline math but never number highlighting, so a run label
    such as `18 N m` keeps one weight.

    Args:
        embed: The embed to render.

    Returns:
        A `<figure class="mkd-figure">` element.
    """
    parts: list[Markup] = []
    if embed.label:
        parts.append(
            Markup('<figcaption class="mkd-label">{}</figcaption>').format(
                render_text(embed.label, numbers=False)
            )
        )
    kind = resolve_embed_kind(embed)
    src = relative_url(embed.src)
    if kind == "rollout":
        parts.append(
            Markup('<deck-rollout src="{}"></deck-rollout>').format(src)
        )
    elif kind == "iframe":
        parts.append(Markup('<deck-embed src="{}"></deck-embed>').format(src))
    else:
        parts.append(
            Markup('<img class="mkd-image" src="{}" alt="{}">').format(
                src, embed.label or ""
            )
        )
    return Markup('<figure class="mkd-figure">{}</figure>').format(
        Markup("").join(parts)
    )


def _editable(key: str, text: str, *, editable: bool) -> Markup:
    """Write the attributes that let the dev server edit a piece of text.

    Args:
        key: The key of the piece, such as `bullet:2`.
        text: Its Markdown source, as the slide holds it.
        editable: False to write nothing.

    Returns:
        The attributes, with a leading space, or nothing.
    """
    if not editable:
        return Markup("")
    return Markup(' data-mkd-edit="{}" data-mkd-text="{}"').format(key, text)


def _render_table(
    table: Table, *, units: Sequence[str], editable: bool = False
) -> Markup:
    """Render a table slide's body.

    Header cells take inline math but no number highlighting, so a column named
    `18 N m` keeps the header weight; body cells take both.

    Args:
        table: The table to render.
        units: Unit spellings a number may carry.
        editable: True to mark each cell for the dev server's editor.

    Returns:
        A `<div class="mkd-table-wrap">` wrapping the table.
    """
    head = Markup("").join(
        Markup("<th{}>{}</th>").format(
            _editable(f"cell:-1:{c}", str(column), editable=editable),
            render_text(str(column), numbers=False),
        )
        for c, column in enumerate(table.columns)
    )
    body = Markup("").join(
        Markup("<tr>{}</tr>").format(
            Markup("").join(
                Markup("<td{}>{}</td>").format(
                    _editable(f"cell:{r}:{c}", str(cell), editable=editable),
                    render_text(str(cell), units=units),
                )
                for c, cell in enumerate(row)
            )
        )
        for r, row in enumerate(table.rows)
    )
    return Markup(
        '<div class="mkd-table-wrap"><table '
        'class="mkd-table"><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'
    ).format(head, body)


def render_slide(
    slide: Slide,
    *,
    date: str | None = None,
    units: Sequence[str] = DEFAULT_UNITS,
    index: int | None = None,
) -> Markup:
    """Render one slide as a reveal `<section>`.

    The slide is not validated; `render_deck` does that.

    Args:
        slide: The slide to render.
        date: The effective date for this slide, shown by the title layout.
        units: Unit spellings a number may carry.
        index: The position of the slide in the deck, to mark its text for
            the dev server's editor; `None` marks nothing.

    Returns:
        The slide's markup.
    """
    layout = resolve_layout(slide)
    effective_date = slide.date or date

    attributes: list[tuple[str, str]] = [
        ("class", " ".join(["mkd-slide", *slide.classes])),
        ("data-layout", layout),
    ]
    if slide.id:
        attributes.append(("data-id", slide.id))
    if slide.date:
        attributes.append(("data-date", slide.date))
    elif layout == "title" and effective_date:
        attributes.append(("data-date", effective_date))
    editable = index is not None
    if editable:
        attributes.append(("data-mkd-slide", str(index)))
    opening = Markup("").join(
        Markup(' {}="{}"').format(name, value) for name, value in attributes
    )

    body: list[Markup] = []
    if slide.title:
        body.append(
            Markup('<h1 class="mkd-title"{}>{}</h1>').format(
                _editable("title", slide.title, editable=editable),
                render_text(slide.title, numbers=False),
            )
        )
    body.extend(_math_span(formula, block=True) for formula in slide.math)
    if slide.sentence:
        body.extend(
            Markup('<p class="mkd-sentence"{}>{}</p>').format(
                _editable(f"sentence:{n}", piece, editable=editable),
                render_text(piece, units=units),
            )
            for n, piece in enumerate(_paragraphs(slide.sentence))
        )
    if slide.bullets:
        items = Markup("").join(
            Markup("<li{}>{}</li>").format(
                _editable(f"bullet:{n}", bullet, editable=editable),
                render_text(bullet, units=units),
            )
            for n, bullet in enumerate(slide.bullets)
        )
        body.append(Markup('<ul class="mkd-bullets">{}</ul>').format(items))
    if slide.embeds:
        figures = Markup("").join(
            _render_figure(embed) for embed in slide.embeds
        )
        body.append(
            Markup('<div class="mkd-figures" data-count="{}">{}</div>').format(
                len(slide.embeds), figures
            )
        )
    if slide.table is not None:
        body.append(_render_table(slide.table, units=units, editable=editable))
    if slide.html:
        body.append(Markup(slide.html))
    if layout == "title" and effective_date:
        body.append(Markup('<p class="mkd-date">{}</p>').format(effective_date))

    section: list[Markup] = [
        Markup('<div class="mkd-body">{}</div>').format(Markup("").join(body))
    ]
    if slide.notes:
        notes = Markup("").join(
            Markup("<p>{}</p>").format(piece)
            for piece in _paragraphs(slide.notes)
        )
        section.append(Markup('<aside class="notes">{}</aside>').format(notes))
    return Markup("<section{}>{}</section>").format(
        opening, Markup("").join(section)
    )


def _opens_with_title_slide(deck: Deck) -> bool:
    """Say whether the deck already opens with a title slide of its own.

    A deck file that writes `# Deck title` alone as its first slide would
    otherwise show two title slides, once generated and once written, so the
    generated one is dropped. Whatever the written one says, it is the author's
    opening slide.

    Args:
        deck: The deck to inspect.

    Returns:
        True when the first slide is a title slide.
    """
    return bool(deck.slides) and resolve_layout(deck.slides[0]) == "title"


def _render_slides(deck: Deck, *, editable: bool = False) -> Markup:
    """Render every slide of a validated deck.

    The generated title slide is included.

    A title slide carrying a date of its own restamps every slide after it,
    which is what the chrome in the bottom left reads.

    Args:
        deck: The deck to render.
        editable: True to mark the text of each slide for the dev server's
            editor. The generated title slide is never marked.

    Returns:
        The slide markup, one `<section>` per line.
    """
    rendered: list[Markup] = []
    if deck.title_slide and not _opens_with_title_slide(deck):
        opening = Slide(layout="title", title=deck.title, date=deck.date)
        rendered.append(render_slide(opening, date=deck.date, units=deck.units))
    effective_date = deck.date
    for index, slide in enumerate(deck.slides):
        if resolve_layout(slide) == "title" and slide.date:
            effective_date = slide.date
        rendered.append(
            render_slide(
                slide,
                date=effective_date,
                units=deck.units,
                index=index if editable else None,
            )
        )
    return Markup("\n").join(rendered)


@lru_cache(maxsize=1)
def _environment() -> Environment:
    """Build the Jinja environment the deck template is loaded from.

    Autoescaping stays on: everything the renderer builds is
    `markupsafe.Markup`, so only text that has not been through this module can
    reach the page unescaped.

    Returns:
        The environment.
    """
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


def render_deck(
    deck: Deck, *, live_reload: bool = False, editable: bool = False
) -> str:
    """Render a deck to a complete HTML document.

    Every path the document holds is relative, so a built deck works from a
    `file://` URL and from any subdirectory of a site.

    Args:
        deck: The deck to render.
        live_reload: True to add the client that reloads the page when the dev
            server rebuilds the deck. Only the dev server sets it.
        editable: True to mark the slide text and add the client that edits
            it through the dev server. It takes effect with `live_reload`.

    Returns:
        The rendered HTML document.

    Raises:
        DeckError: If the deck or one of its slides breaks a rule of the model,
            or the template is missing from the installation.
    """
    validate_deck(deck)
    context: dict[str, Any] = {
        "title": deck.title,
        "date": deck.date,
        "theme": deck.theme,
        "slides": _render_slides(deck, editable=editable and live_reload),
        "assets": f"{ASSET_BASE}/",
        "extra_css": list(deck.extra_css),
        "extra_js": list(deck.extra_js),
        "reveal": dict(deck.reveal),
        "rollouts": deck_has_rollouts(deck),
        "reload_path": RELOAD_PATH if live_reload else None,
        "edit_path": EDIT_PATH if editable and live_reload else None,
        "export_path": EXPORT_PATH,
    }
    try:
        template = _environment().get_template(_TEMPLATE_NAME)
    except TemplateNotFound as exc:
        raise DeckError(
            "The deck template is missing from this installation of mkdeck; "
            "reinstall the package to restore it.",
            source=TEMPLATE_DIR / _TEMPLATE_NAME,
        ) from exc
    return template.render(**context)
