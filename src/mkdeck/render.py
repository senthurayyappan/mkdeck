"""Turn a :class:`mkdeck.model.Deck` into HTML.

This module owns the HTML contract: every element, class and ``data-`` attribute
a slide emits is decided here, and ``assets/mkdeck.js`` reads them back. Neither
side may change the contract on its own.

The number highlighting is done here rather than with a client-side regex, so a
deck saved from the browser keeps it. The pattern is the one the deck this
package replaces used, negative lookbehind included, which is what keeps the
``2`` in ``Go2`` grey.
"""

import base64
import re
import sys
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from markupsafe import Markup, escape

from mkdeck.config import DEFAULT_UNITS, DeckConfig
from mkdeck.errors import DeckError
from mkdeck.model import (
    Deck,
    Embed,
    Slide,
    Table,
    resolve_embed_kind,
    resolve_layout,
    validate_slide,
)

__all__ = [
    "ASSET_ROOT",
    "DEFAULT_ASSET_BASE",
    "DEFAULT_UNITS",
    "TEMPLATE_NAME",
    "highlight_numbers",
    "inline_assets",
    "math_span",
    "render_deck",
    "render_slide",
    "render_text",
]

ASSET_ROOT = Path(__file__).resolve().parent / "assets"
"""Folder holding the front-end assets shipped inside the wheel."""

TEMPLATE_DIR = ASSET_ROOT / "templates"
TEMPLATE_NAME = "deck.html.jinja"

DEFAULT_ASSET_BASE = "mkdeck-assets"
"""Folder the vendored assets are copied into, next to ``index.html``."""

REMOTE_PREFIXES: tuple[str, ...] = ("http://", "https://", "//", "data:")
"""Sources that are fetched rather than read from the deck folder."""

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
_CSS_URL = re.compile(r"""url\(\s*(?P<quote>['"]?)(?P<target>[^'")]+)(?P=quote)\s*\)""")
_LINK_TAG = re.compile(r"""<link\b[^>]*\brel=["']stylesheet["'][^>]*>""", re.IGNORECASE)
_SCRIPT_TAG = re.compile(r"""<script\b[^>]*\bsrc=["'](?P<src>[^"']+)["'][^>]*>\s*</script>""", re.IGNORECASE)
_HREF = re.compile(r"""\bhref=["'](?P<href>[^"']+)["']""", re.IGNORECASE)

_MEDIA_TYPES = {
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _warn(message: str) -> None:
    """Print a non-fatal warning to standard error.

    Args:
        message: The text to show, without a trailing newline.
    """
    print(f"mkdeck: warning: {message}", file=sys.stderr)


@lru_cache(maxsize=32)
def _number_pattern(units: tuple[str, ...]) -> re.Pattern[str]:
    """Build the number-highlighting pattern for one unit list.

    Args:
        units: Unit spellings a number may carry, longest first.

    Returns:
        A compiled pattern matching one standalone number and its unit.
    """
    pattern = r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?"
    if units:
        alternatives = "|".join(re.escape(unit) for unit in units)
        pattern += rf"(?: ?(?:{alternatives}))?"
    return re.compile(pattern + r"(?![A-Za-z0-9])")


def highlight_numbers(text: str, *, units: Sequence[str] = DEFAULT_UNITS) -> Markup:
    """Wrap every standalone number in ``<span class="mkd-num">``.

    A number glued to letters is left alone, so the ``2`` in ``Go2`` stays grey.

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
        pieces.append(Markup('<span class="mkd-num">{}</span>').format(match.group(0)))
        last = match.end()
    pieces.append(escape(source[last:]))
    return Markup("").join(pieces)


def math_span(tex: str, *, block: bool = False) -> Markup:
    """Emit the placeholder KaTeX fills in on the client.

    The formula source is escaped into ``data-tex``, so a KaTeX failure leaves an
    empty span rather than a broken slide; the front-end then writes the source
    in as text.

    Args:
        tex: The formula source.
        block: True for a display formula on a line of its own.

    Returns:
        A ``<span class="mkd-math">`` element with no text content.
    """
    classes = "mkd-math mkd-math-block" if block else "mkd-math"
    return Markup('<span class="{}" data-tex="{}"></span>').format(classes, str(tex))


def render_text(text: str, *, units: Sequence[str] = DEFAULT_UNITS, numbers: bool = True) -> Markup:
    """Render one line of slide text: inline math, then number highlighting.

    Text between dollar signs becomes an inline ``.mkd-math`` span, and the text
    around it keeps its number highlighting. A line with an odd number of dollar
    signs is plain text, as in the deck this package replaces.

    Args:
        text: The line to render.
        units: Unit spellings a number may carry.
        numbers: False to leave the numbers alone, which is what a figure label
            and a table header do so that they keep one weight.

    Returns:
        The rendered markup.
    """

    def plain(piece: str) -> Markup:
        return highlight_numbers(piece, units=units) if numbers else escape(piece)

    source = str(text)
    parts = source.split("$")
    if len(parts) % 2 == 0:
        return plain(source)
    pieces: list[Markup] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            if part:
                pieces.append(plain(part))
        else:
            pieces.append(math_span(part))
    return Markup("").join(pieces)


def _paragraphs(text: str) -> list[str]:
    """Split a block of text at its blank lines.

    Args:
        text: The text to split.

    Returns:
        One piece per paragraph, blank pieces dropped.
    """
    return [piece.strip() for piece in _PARAGRAPH_BREAK.split(text.strip()) if piece.strip()]


def _render_figure(embed: Embed) -> Markup:
    """Render one figure: an optional caption above an iframe or an image.

    A label carries inline math but never number highlighting, so a run label
    such as ``18 N m`` keeps one weight.

    Args:
        embed: The embed to render.

    Returns:
        A ``<figure class="mkd-figure">`` element.
    """
    parts: list[Markup] = []
    if embed.label:
        parts.append(
            Markup('<figcaption class="mkd-label">{}</figcaption>').format(render_text(embed.label, numbers=False))
        )
    if resolve_embed_kind(embed) == "iframe":
        parts.append(Markup('<deck-embed src="{}"></deck-embed>').format(embed.src))
    else:
        parts.append(Markup('<img class="mkd-image" src="{}" alt="{}">').format(embed.src, embed.label or ""))
    return Markup('<figure class="mkd-figure">{}</figure>').format(Markup("").join(parts))


def _render_table(table: Table, *, units: Sequence[str]) -> Markup:
    """Render a table slide's body.

    Header cells take inline math but no number highlighting, so a column named
    ``18 N m`` keeps the header weight; body cells take both.

    Args:
        table: The table to render.
        units: Unit spellings a number may carry.

    Returns:
        A ``<div class="mkd-table-wrap">`` wrapping the table.
    """
    head = Markup("").join(
        Markup("<th>{}</th>").format(render_text(str(column), numbers=False)) for column in table.columns
    )
    body = Markup("").join(
        Markup("<tr>{}</tr>").format(
            Markup("").join(Markup("<td>{}</td>").format(render_text(str(cell), units=units)) for cell in row)
        )
        for row in table.rows
    )
    return Markup(
        '<div class="mkd-table-wrap"><table class="mkd-table"><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'
    ).format(head, body)


def render_slide(
    slide: Slide,
    *,
    date: str | None = None,
    units: Sequence[str] = DEFAULT_UNITS,
    index: int = 0,
) -> Markup:
    """Render one slide as a reveal ``<section>``.

    Args:
        slide: The slide to render.
        date: The effective date for this slide, shown by the title layout.
        units: Unit spellings a number may carry.
        index: The slide's zero-based position, used to name it in an error.

    Returns:
        The slide's markup.

    Raises:
        DeckError: If the slide breaks a rule of the model.
    """
    validate_slide(slide, index=index)
    layout = resolve_layout(slide)
    effective_date = slide.date or date

    attributes: list[tuple[str, str]] = [
        ("class", " ".join(["mkd-slide", *(str(name) for name in slide.classes)])),
        ("data-layout", layout),
    ]
    if slide.id:
        attributes.append(("data-id", str(slide.id)))
    if slide.date:
        attributes.append(("data-date", str(slide.date)))
    elif layout == "title" and effective_date:
        attributes.append(("data-date", str(effective_date)))
    opening = Markup("").join(Markup(' {}="{}"').format(name, value) for name, value in attributes)

    body: list[Markup] = []
    if layout == "title" and slide.title:
        body.append(Markup('<h1 class="mkd-title">{}</h1>').format(slide.title))
    body.extend(math_span(formula, block=True) for formula in slide.math)
    if slide.sentence:
        body.extend(
            Markup('<p class="mkd-sentence">{}</p>').format(render_text(piece, units=units))
            for piece in _paragraphs(slide.sentence)
        )
    if slide.bullets:
        items = Markup("").join(
            Markup("<li>{}</li>").format(render_text(bullet, units=units)) for bullet in slide.bullets
        )
        body.append(Markup('<ul class="mkd-bullets">{}</ul>').format(items))
    if slide.embeds:
        figures = Markup("").join(_render_figure(embed) for embed in slide.embeds)
        body.append(Markup('<div class="mkd-figures" data-count="{}">{}</div>').format(len(slide.embeds), figures))
    elif slide.table is not None:
        body.append(_render_table(slide.table, units=units))
    if slide.html:
        body.append(Markup(slide.html))
    if layout == "title" and effective_date:
        body.append(Markup('<p class="mkd-date">{}</p>').format(effective_date))

    section: list[Markup] = [Markup('<div class="mkd-body">{}</div>').format(Markup("").join(body))]
    if slide.notes:
        notes = Markup("").join(Markup("<p>{}</p>").format(piece) for piece in _paragraphs(slide.notes))
        section.append(Markup('<aside class="notes">{}</aside>').format(notes))
    return Markup("<section{}>{}</section>").format(opening, Markup("").join(section))


def _writes_its_own_title(deck: Deck) -> bool:
    """Say whether the deck already opens with its own title slide.

    A deck file that writes ``# Deck title`` as its first slide would otherwise
    show that slide twice, once generated and once written, so the generated one
    is dropped.

    Args:
        deck: The deck to inspect.

    Returns:
        True when the first slide is a title slide holding the deck title.
    """
    if not deck.slides:
        return False
    first = deck.slides[0]
    return resolve_layout(first) == "title" and (first.title or "").strip() == (deck.title or "").strip()


def render_slides(deck: Deck, *, units: Sequence[str] = DEFAULT_UNITS) -> Markup:
    """Render every slide of a deck, including the generated title slide.

    A title slide carrying a date of its own restamps every slide after it,
    which is what the chrome in the bottom left reads.

    Args:
        deck: The deck to render.
        units: Unit spellings a number may carry.

    Returns:
        The slide markup, one ``<section>`` per line.

    Raises:
        DeckError: If a slide breaks a rule of the model.
    """
    rendered: list[Markup] = []
    if deck.title_slide and not _writes_its_own_title(deck):
        opening = Slide(layout="title", title=deck.title, date=deck.date)
        rendered.append(render_slide(opening, date=deck.date, units=units))
    effective_date = deck.date
    for index, slide in enumerate(deck.slides):
        if resolve_layout(slide) == "title" and slide.date:
            effective_date = slide.date
        rendered.append(render_slide(slide, date=effective_date, units=units, index=index))
    return Markup("\n").join(rendered)


@lru_cache(maxsize=1)
def _environment() -> Environment:
    """Build the Jinja environment the deck template is loaded from.

    Autoescaping stays on: everything the renderer builds is
    :class:`markupsafe.Markup`, so only text that has not been through this
    module can reach the page unescaped.

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
    deck: Deck,
    *,
    config: DeckConfig | None = None,
    asset_base: str = DEFAULT_ASSET_BASE,
) -> str:
    """Render a deck to a complete HTML document.

    Every path the document holds is relative, so a built deck works from a
    ``file://`` URL and from any subdirectory of a site.

    Args:
        deck: The deck to render. Its own fields carry the merged configuration,
            which :func:`mkdeck.config.apply_config` puts there.
        config: The merged deck configuration; only ``units`` is read from it,
            because every other key already sits on the deck.
        asset_base: Folder the vendored assets sit in, relative to the document.

    Returns:
        The rendered HTML document.

    Raises:
        DeckError: If a slide breaks a rule of the model, or the template is
            missing from the installation.
    """
    units = tuple(config.units) if config is not None and config.units else DEFAULT_UNITS
    base = asset_base.strip("/")
    slides = render_slides(deck, units=units)
    generated = deck.title_slide and not _writes_its_own_title(deck)
    context: dict[str, Any] = {
        "lang": "en",
        "title": deck.title or "Slide Deck",
        "date": deck.date,
        "theme": deck.theme or "minimal",
        "slides": slides,
        "slides_html": slides,
        "slide_count": len(deck.slides) + (1 if generated else 0),
        "assets": f"{base}/" if base else "",
        "asset_base": base,
        "extra_css": list(deck.extra_css),
        "extra_js": list(deck.extra_js),
        "reveal": dict(deck.reveal),
        "units": list(units),
    }
    try:
        template = _environment().get_template(TEMPLATE_NAME)
    except TemplateNotFound as exc:
        raise DeckError(
            "is missing from this installation of mkdeck; reinstall the package to restore it.",
            source=TEMPLATE_DIR / TEMPLATE_NAME,
        ) from exc
    return template.render(**context)


def _media_type(path: Path) -> str:
    """Guess the media type of a file inlined as a ``data:`` URI.

    Args:
        path: The file being inlined.

    Returns:
        A media type string.
    """
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _inline_css_urls(text: str, *, base: Path) -> str:
    """Rewrite the relative ``url(...)`` references of a stylesheet to data URIs.

    Args:
        text: The stylesheet source.
        base: The folder the stylesheet was read from.

    Returns:
        The stylesheet with every resolvable local reference inlined.
    """

    def replace(match: re.Match[str]) -> str:
        target = match.group("target").strip()
        if not target or target.startswith(REMOTE_PREFIXES):
            return match.group(0)
        path = base / target.split("?", 1)[0].split("#", 1)[0]
        if not path.is_file():
            return match.group(0)
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"url(data:{_media_type(path)};base64,{payload})"

    return _CSS_URL.sub(replace, text)


def _resolve_asset(href: str, *, asset_base: str, source: Path | None) -> Path | None:
    """Find the file a stylesheet or script reference points at.

    Args:
        href: The reference as the document holds it.
        asset_base: Folder the vendored assets sit in.
        source: The deck source folder, for the deck's own extras.

    Returns:
        The file, or ``None`` when it is remote or cannot be found.
    """
    if not href or href.startswith(REMOTE_PREFIXES):
        return None
    base = asset_base.strip("/")
    if base and href.startswith(f"{base}/"):
        candidate = ASSET_ROOT / href[len(base) + 1 :]
        return candidate if candidate.is_file() else None
    if source is not None:
        candidate = Path(source) / href
        if candidate.is_file():
            return candidate
    return None


def inline_assets(html: str, *, asset_base: str = DEFAULT_ASSET_BASE, source: Path | None = None) -> str:
    """Fold every stylesheet and script of a rendered deck into the document.

    Fonts and images a stylesheet refers to become ``data:`` URIs, so the result
    opens from a ``file://`` URL with only the deck's own figures left outside.
    A reference that cannot be resolved, such as one to a CDN, is left alone.

    Args:
        html: The rendered document.
        asset_base: Folder the vendored assets sit in.
        source: The deck source folder, for the deck's own extras.

    Returns:
        The document with its stylesheets and scripts inlined.
    """

    def fold_link(match: re.Match[str]) -> str:
        found = _HREF.search(match.group(0))
        if found is None:
            return match.group(0)
        path = _resolve_asset(found.group("href"), asset_base=asset_base, source=source)
        if path is None:
            _warn(f"stylesheet left linked, it was not found: {found.group('href')}")
            return match.group(0)
        text = _inline_css_urls(path.read_text(encoding="utf-8"), base=path.parent)
        return f"<style>{text.replace('</style', '<\\/style')}</style>"

    def fold_script(match: re.Match[str]) -> str:
        path = _resolve_asset(match.group("src"), asset_base=asset_base, source=source)
        if path is None:
            _warn(f"script left linked, it was not found: {match.group('src')}")
            return match.group(0)
        text = path.read_text(encoding="utf-8")
        return f"<script>{text.replace('</script', '<\\/script')}</script>"

    return _SCRIPT_TAG.sub(fold_script, _LINK_TAG.sub(fold_link, html))
