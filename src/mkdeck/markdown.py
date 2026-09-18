"""Markdown to :class:`~mkdeck.model.Deck`.

A deck file opens with YAML frontmatter, and its slides are separated by ``---`` on a
line of its own. Per-slide options follow the separator as an HTML comment holding YAML,
so the file still reads as ordinary Markdown everywhere else::

    ---
    title: Quadruped Vault Runs
    date: 2026-09-18
    ---

    # Quadruped Vault Runs

    ---
    <!--
    id: a1-crate
    -->

    The Go2 finishes standing on the 0.60 m crate.

    ![Unitree Go2](assets/a1_go2_crate.html)
    ![Barkour CAD](assets/a1_cad_crate.html)

The body is parsed with ``markdown-it-py`` in CommonMark mode, with tables enabled and
with the container, definition-list and dollar-math plugins. Text is carried into the
model as its raw Markdown source, so inline ``$...$`` math survives to the renderer.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.container import container_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin

from mkdeck.config import DeckConfig, coerce_text, coerce_text_list, parse_yaml, suggest
from mkdeck.errors import DeckError
from mkdeck.model import (
    LAYOUTS,
    Deck,
    Embed,
    Slide,
    Table,
    resolve_embed_kind,
    slide_name,
    validate_deck,
    validate_slide,
)

SLIDE_OPTION_KEYS: tuple[str, ...] = (
    "id",
    "layout",
    "title",
    "sentence",
    "bullets",
    "math",
    "notes",
    "date",
    "classes",
)
"""Every key accepted in the HTML comment that opens a slide."""

BODY_ONLY_KEYS: tuple[str, ...] = ("embeds", "table", "html")
"""Slide fields that are written in the Markdown body, never in the options comment."""

_SEPARATOR = re.compile(r"^---[ \t]*$")
_FENCE = re.compile(r"^(?P<marker>`{3,}|~{3,})")
_OPTIONS = re.compile(r"\A\s*<!--(?P<body>.*?)-->[ \t]*\n?", re.DOTALL)
_FRONTMATTER_END = ("---", "...")
_TEXT_CHILDREN = frozenset({"text", "code_inline"})
_IGNORED_TOKENS = frozenset({"hr"})


def _build_parser() -> MarkdownIt:
    """Build the Markdown parser the deck format uses.

    Returns:
        A CommonMark parser with tables, the ``figures`` and ``notes`` containers,
        definition lists and dollar math enabled.
    """
    md = MarkdownIt("commonmark")
    md.enable("table")
    md.use(container_plugin, "figures")
    md.use(container_plugin, "notes")
    md.use(deflist_plugin)
    md.use(dollarmath_plugin)
    return md


PARSER = _build_parser()
"""The shared parser instance. Building one costs more than parsing a small deck."""


@dataclass(slots=True)
class _Draft:
    """What the Markdown body of one slide holds, before the options are applied."""

    title: str | None = None
    sentences: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    math: list[str] = field(default_factory=list)
    embeds: list[Embed] = field(default_factory=list)
    table: Table | None = None
    html: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def split_frontmatter(text: str, *, source: Path | str) -> tuple[dict[str, Any], str]:
    """Split the deck frontmatter from the slides.

    Args:
        text: The whole Markdown file.
        source: The file the text came from, used in the error messages.

    Returns:
        The frontmatter mapping, empty when the file has none, and the rest of the file.

    Raises:
        DeckError: If the frontmatter block is never closed, holds unreadable YAML, or
            does not hold a mapping.
    """
    body = text.lstrip("﻿")
    lines = body.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, body
    for number, line in enumerate(lines[1:], start=1):
        if line.strip() in _FRONTMATTER_END:
            data = parse_yaml("\n".join(lines[1:number]), origin=source)
            if data is None:
                return {}, "\n".join(lines[number + 1 :])
            if not isinstance(data, Mapping):
                raise DeckError(
                    "opens with frontmatter that does not hold deck settings; "
                    "write it as key: value lines, or delete the block.",
                    source=source,
                )
            return dict(data), "\n".join(lines[number + 1 :])
    raise DeckError(
        "opens with a frontmatter block that is never closed; add a line holding --- after the deck settings.",
        source=source,
    )


def parse_markdown(text: str, *, source: Path) -> Deck:
    """Parse a Markdown deck file into a :class:`~mkdeck.model.Deck`.

    The deck takes its title, date and other settings from the frontmatter alone. A
    ``deck.yml`` beside the file is merged in later by :func:`mkdeck.config.load_config`.

    Args:
        text: The whole Markdown file.
        source: The path of the file, used in the error messages. It is never read.

    Returns:
        The parsed deck, already validated.

    Raises:
        DeckError: If the file, or one of its slides, breaks a rule of the format.
    """
    frontmatter, body = split_frontmatter(text, source=source)
    config = DeckConfig.from_mapping(frontmatter, origin=source)
    deck = Deck(
        title=config.title,
        date=config.date,
        theme=config.theme,
        extra_css=list(config.extra_css),
        extra_js=list(config.extra_js),
        reveal=dict(config.reveal),
        title_slide=config.title_slide,
    )
    for chunk in _split_slides(body):
        slide = _parse_slide(chunk, index=len(deck.slides), source=source)
        if slide is not None:
            deck.slides.append(slide)
    validate_deck(deck, source=source)
    return deck


def _split_slides(body: str) -> list[str]:
    """Cut the body of a deck file at every ``---`` line outside a code fence.

    Args:
        body: The deck file with its frontmatter removed.

    Returns:
        One piece of text per slide, in order.
    """
    chunks: list[list[str]] = [[]]
    fence: str | None = None
    for line in body.split("\n"):
        stripped = line.strip()
        if fence is not None:
            chunks[-1].append(line)
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
            continue
        opening = _FENCE.match(stripped)
        if opening is not None:
            fence = opening.group("marker")
            chunks[-1].append(line)
            continue
        if _SEPARATOR.match(line):
            chunks.append([])
            continue
        chunks[-1].append(line)
    return ["\n".join(chunk) for chunk in chunks]


def _parse_slide(chunk: str, *, index: int, source: Path) -> Slide | None:
    """Parse one piece of the deck file into a slide.

    Args:
        chunk: The text between two slide separators.
        index: The zero-based position the slide will take, used to name it.
        source: The path of the deck file, used in the error messages.

    Returns:
        The slide, or ``None`` when the piece holds nothing at all.

    Raises:
        DeckError: If the slide breaks a rule of the format or of the model.
    """
    options, body = _take_options(chunk, index=index, source=source)
    if not options and not body.strip():
        return None

    name = slide_name(Slide(id=_option_id(options)), index)

    def fail(message: str) -> DeckError:
        return DeckError(message, slide=name, source=source)

    draft = _Draft()
    _consume(PARSER.parse(body), draft, fail=fail)
    slide = Slide(
        title=draft.title,
        sentence="\n\n".join(draft.sentences) or None,
        bullets=draft.bullets,
        math=draft.math,
        embeds=draft.embeds,
        table=draft.table,
        html="\n".join(draft.html) or None,
        notes="\n\n".join(draft.notes) or None,
    )
    _apply_options(slide, options, fail=fail)
    if slide.layout == "auto" and slide.title and _is_bare_title(slide):
        slide.layout = "title"
    validate_slide(slide, index=index, source=source)
    return slide


def _option_id(options: Mapping[str, Any]) -> str | None:
    """Read the id out of the slide options, for naming the slide in an error.

    Args:
        options: The options mapping, which has not been validated yet.

    Returns:
        The id as text, or ``None`` when the slide has none.
    """
    raw = options.get("id")
    return None if raw is None else str(raw)


def _take_options(chunk: str, *, index: int, source: Path) -> tuple[dict[str, Any], str]:
    """Split the options comment off the front of a slide.

    A comment that does not hold a YAML mapping is an ordinary Markdown comment: it is
    invisible in every Markdown renderer and it stays invisible here.

    Args:
        chunk: The text of the slide.
        index: The zero-based position of the slide, used to name it.
        source: The path of the deck file, used in the error messages.

    Returns:
        The options mapping, empty when the slide has none, and the rest of the slide.

    Raises:
        DeckError: If the comment holds YAML that cannot be read.
    """
    match = _OPTIONS.match(chunk)
    if match is None:
        return {}, chunk
    try:
        data = parse_yaml(match.group("body"), origin=source)
    except DeckError as error:
        raise DeckError(error.message, slide=slide_name(Slide(), index), source=source) from error
    if not isinstance(data, Mapping):
        return {}, chunk[match.end() :]
    return dict(data), chunk[match.end() :]


def _apply_options(slide: Slide, options: Mapping[str, Any], *, fail: Callable[[str], DeckError]) -> None:
    """Put the options of a slide onto the slide, in place.

    Args:
        slide: The slide built from the Markdown body.
        options: The mapping from the options comment.
        fail: A callable that turns a message into a :class:`DeckError`.

    Raises:
        DeckError: If an option is unknown, has the wrong shape, or repeats something the
            Markdown body already said.
    """
    for key, raw in options.items():
        name = str(key)
        if name in BODY_ONLY_KEYS:
            raise fail(
                f'sets "{name}" in its options, but embeds, tables and raw HTML are written in the Markdown '
                "body; move it there."
            )
        if name not in SLIDE_OPTION_KEYS:
            raise fail(f'has the unknown option "{name}". {suggest(name, SLIDE_OPTION_KEYS)}')
        if raw is None:
            continue
        value = _option_value(name, raw, fail=fail)
        current = getattr(slide, name)
        if _is_set(name, current) and current != value:
            raise fail(f'sets "{name}" in its options and in its Markdown body; keep one of the two.')
        setattr(slide, name, value)


def _option_value(name: str, raw: Any, *, fail: Callable[[str], DeckError]) -> Any:
    """Coerce one option value to the type its field holds.

    Args:
        name: The option key.
        raw: The value the author wrote.
        fail: A callable that turns a message into a :class:`DeckError`.

    Returns:
        The coerced value.

    Raises:
        DeckError: If the value has the wrong shape, or names a layout that does not exist.
    """
    if name in {"bullets", "math", "classes"}:
        return coerce_text_list(raw, key=name, fail=fail)
    value = coerce_text(raw, key=name, fail=fail)
    if name == "layout" and value not in LAYOUTS:
        raise fail(f'has the unknown layout "{value}". {suggest(value, LAYOUTS)}')
    return value


def _is_set(name: str, value: Any) -> bool:
    """Say whether a slide field already holds something the Markdown body put there.

    Args:
        name: The field name.
        value: The value the field holds.

    Returns:
        ``True`` when the field is not at its default.
    """
    if name == "layout":
        return value != "auto"
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _is_bare_title(slide: Slide) -> bool:
    """Say whether a slide holds nothing but its heading.

    Args:
        slide: The slide to check.

    Returns:
        ``True`` when the heading is the only content, which makes it a title slide.
    """
    return not (slide.sentence or slide.bullets or slide.math or slide.embeds or slide.table or slide.html)


def _consume(tokens: list[Token], draft: _Draft, *, fail: Callable[[str], DeckError]) -> None:
    """Walk a run of block tokens and pour them into a draft slide.

    Args:
        tokens: The tokens of the slide body, or of one container inside it.
        draft: The draft to fill.
        fail: A callable that turns a message into a :class:`DeckError`.

    Raises:
        DeckError: If the body holds a second heading or a construct with no home in the
            slide model.
    """
    index = 0
    while index < len(tokens):
        token = tokens[index]
        kind = token.type
        if kind == "heading_open":
            end = _close(tokens, index)
            heading = _inline_text(tokens[index + 1 : end])
            if draft.title is not None:
                raise fail("holds two headings, but a slide takes one; move the second onto a new slide.")
            draft.title = heading
            index = end + 1
        elif kind == "paragraph_open":
            end = _close(tokens, index)
            _consume_paragraph(tokens[index + 1 : end], draft)
            index = end + 1
        elif kind in {"bullet_list_open", "ordered_list_open"}:
            end = _close(tokens, index)
            draft.bullets.extend(_list_items(tokens[index + 1 : end]))
            index = end + 1
        elif kind == "dl_open":
            end = _close(tokens, index)
            draft.bullets.extend(_definition_items(tokens[index + 1 : end]))
            index = end + 1
        elif kind in {"math_block", "math_block_label"}:
            draft.math.append(token.content.strip())
            index += 1
        elif kind == "table_open":
            end = _close(tokens, index)
            draft.table = _parse_table(tokens[index : end + 1])
            index = end + 1
        elif kind in {"fence", "code_block"}:
            draft.html.append(_code_html(token))
            index += 1
        elif kind == "html_block":
            _consume_html(token, draft)
            index += 1
        elif kind == "container_figures_open":
            end = _close(tokens, index)
            _consume(tokens[index + 1 : end], draft, fail=fail)
            index = end + 1
        elif kind == "container_notes_open":
            end = _close(tokens, index)
            draft.notes.append(_inline_text(tokens[index + 1 : end], join="\n\n"))
            index = end + 1
        elif kind in _IGNORED_TOKENS:
            index += 1
        else:
            raise fail(
                f"holds {_describe_token(kind)}, which has no place on a slide; "
                "write it as bullets, a table, or raw HTML."
            )


def _close(tokens: list[Token], start: int) -> int:
    """Find the token that closes the one at ``start``.

    Args:
        tokens: The run of tokens.
        start: The index of an opening token.

    Returns:
        The index of the matching closing token, or the last index when the run is cut
        short, which the parser does not produce.
    """
    depth = 0
    for index in range(start, len(tokens)):
        depth += tokens[index].nesting
        if depth == 0:
            return index
    return len(tokens) - 1


def _inline_text(tokens: list[Token], *, join: str = " ") -> str:
    """Collect the source text of every inline token in a run.

    Args:
        tokens: The run of tokens.
        join: What to put between the pieces.

    Returns:
        The joined text, as it was written in the Markdown.
    """
    pieces = [token.content.strip() for token in tokens if token.type == "inline"]
    return join.join(piece for piece in pieces if piece)


def _consume_paragraph(tokens: list[Token], draft: _Draft) -> None:
    """Turn one paragraph into embeds, a sentence, or both.

    A paragraph of images is a row of figures. Any other paragraph keeps its Markdown
    source, so that inline ``$...$`` math reaches the renderer untouched.

    Args:
        tokens: The tokens between ``paragraph_open`` and ``paragraph_close``.
        draft: The draft to fill.
    """
    inline = next((token for token in tokens if token.type == "inline"), None)
    if inline is None:
        return
    children = inline.children or []
    images = [child for child in children if child.type == "image"]
    if not images:
        text = inline.content.strip()
        if text:
            draft.sentences.append(text)
        return
    for child in images:
        src = str(child.attrGet("src") or "")
        label = child.content.strip()
        draft.embeds.append(Embed(src=src, label=label or None, kind=resolve_embed_kind(Embed(src=src))))
    leftover = " ".join(
        child.content.strip() for child in children if child.type in _TEXT_CHILDREN and child.content.strip()
    )
    if leftover:
        draft.sentences.append(leftover)


def _list_items(tokens: list[Token]) -> list[str]:
    """Read the items of a list.

    Args:
        tokens: The tokens between the list open and close.

    Returns:
        One piece of Markdown text per item.
    """
    items: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index].type == "list_item_open":
            end = _close(tokens, index)
            text = _inline_text(tokens[index + 1 : end])
            if text:
                items.append(text)
            index = end + 1
        else:
            index += 1
    return items


def _definition_items(tokens: list[Token]) -> list[str]:
    """Read a definition list as bullets of the form ``term: definition``.

    Args:
        tokens: The tokens between ``dl_open`` and ``dl_close``.

    Returns:
        One bullet per definition.
    """
    items: list[str] = []
    term = ""
    index = 0
    while index < len(tokens):
        kind = tokens[index].type
        if kind in {"dt_open", "dd_open"}:
            end = _close(tokens, index)
            text = _inline_text(tokens[index + 1 : end])
            if kind == "dt_open":
                term = text
            elif text:
                items.append(f"{term}: {text}" if term else text)
            index = end + 1
        else:
            index += 1
    return items


def _parse_table(tokens: list[Token]) -> Table:
    """Read a GFM table.

    Args:
        tokens: The tokens from ``table_open`` to ``table_close``.

    Returns:
        The table, with the header cells as its columns.
    """
    columns: list[str] = []
    rows: list[list[str]] = []
    row: list[str] | None = None
    section = ""
    for token in tokens:
        if token.type in {"thead_open", "tbody_open"}:
            section = token.type
        elif token.type == "tr_open" and section == "tbody_open":
            row = []
        elif token.type == "tr_close" and row is not None:
            rows.append(row)
            row = None
        elif token.type == "inline":
            text = token.content.strip()
            if section == "thead_open":
                columns.append(text)
            elif row is not None:
                row.append(text)
    return Table(columns=columns, rows=rows)


def _code_html(token: Token) -> str:
    """Turn a code block into the raw HTML a slide carries.

    A ``mermaid`` fence becomes a ``<deck-mermaid>`` element, which the front-end renders
    on the slides that hold one. Every other fence becomes a highlightable code block.

    Args:
        token: The ``fence`` or ``code_block`` token.

    Returns:
        The HTML for the block, with the code escaped.
    """
    info = token.info.strip().split()[0].lower() if token.info.strip() else ""
    code = html_escape(token.content.strip(), quote=False)
    if info == "mermaid":
        return f"<deck-mermaid>{code}</deck-mermaid>"
    language = f' class="language-{html_escape(info)}"' if info else ""
    return f"<pre><code{language}>{code}</code></pre>"


def _consume_html(token: Token, draft: _Draft) -> None:
    """Take a raw HTML block, or the speaker notes hidden in a comment.

    Args:
        token: The ``html_block`` token.
        draft: The draft to fill.
    """
    raw = token.content.strip()
    if raw.startswith("<!--") and raw.endswith("-->"):
        inner = raw[4:-3].strip()
        if inner.lower().startswith("notes:"):
            note = inner[len("notes:") :].strip()
            if note:
                draft.notes.append(note)
        return
    if raw:
        draft.html.append(raw)


def _describe_token(kind: str) -> str:
    """Name a block token for an error message.

    Args:
        kind: The token type, such as ``blockquote_open``.

    Returns:
        A phrase such as ``a block quote``.
    """
    name = kind.removesuffix("_open").replace("_", " ")
    article = "an" if name[:1] in {"a", "e", "i", "o", "u"} else "a"
    return f"{article} {name}"
