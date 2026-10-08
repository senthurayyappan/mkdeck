"""Markdown to `mkdeck.model.Deck`.

A deck file may open with YAML frontmatter, and its slides are separated by a
line of dashes (`---`) on its own. The separator is a thematic break in the
Markdown syntax tree, so a `---` inside a code fence, an HTML comment or a `$$`
block never cuts a slide. Setext headings (a line underlined with `---` or
`===`) are not supported, which is what lets a `---` right under a paragraph be
a separator; write headings with `#`.

Per-slide options follow the separator as an HTML comment holding YAML, so the
file still reads as ordinary Markdown everywhere else::

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

The first comment of a slide is read as options when one of its `key:` lines
names an option, or is close enough to one to be a typo of it (`layot:`). Any
other comment, such as `<!-- TODO: fix -->`, is an ordinary Markdown comment: it
stays invisible and is never checked. A comment that reads as options must be
valid YAML and hold only known options. The one exception is a comment that
starts with `notes:`. It is speaker notes, wherever it sits on the slide, and
everything after `notes:` is the text of the notes, as written, so a colon or a
`#` in it is just text. To set `notes` next to other options, list it after them
and quote it if it needs to be YAML.

The body is parsed with `markdown-it-py` in CommonMark mode, with tables enabled
and with the container, definition-list and dollar-math plugins. Text is carried
into the model as its raw Markdown source, so inline Markdown and `$...$` math
survive to the renderer.
"""

import difflib
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from functools import partial
from html import escape as html_escape
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.rules_inline import image as image_rule
from markdown_it.token import Token
from mdit_py_plugins.container import container_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin

from mkdeck._coerce import coerce_text, coerce_text_list, parse_yaml
from mkdeck._messages import suggest
from mkdeck.config import DEFAULT_TITLE, merge_settings, normalize_settings
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
)

__all__ = [
    "BODY_ONLY_KEYS",
    "MATH_RULES",
    "SLIDE_OPTION_KEYS",
    "TextSource",
    "locate_text",
    "parse_markdown",
    "split_frontmatter",
]

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
"""Slide fields written in the Markdown body.

They never appear in the options comment.
"""

MATH_RULES: dict[str, bool] = {"allow_space": False, "allow_digits": False}
"""How `$...$` opens and closes a formula.

It does not open before a space or before a digit, so "costs $5 and $10" is
text. The parser here and the one that renders the text share these rules.
"""

_OPTION_KEY = re.compile(
    r"^[ \t]*(?P<key>[A-Za-z_][\w-]*)[ \t]*:", re.MULTILINE
)
_BLANK_RUN = re.compile(r"[ \t]*\n(?:[ \t]*\n)+")
_LINK_TAIL = re.compile(r"\]\([^)]*\)")
_EMPHASIS = ("***", "___", "**", "__", "~~", "*", "_")
_FRONTMATTER_END = ("---", "...")
_TOKEN_NAMES = {
    "fence": "a code block",
    "code_block": "a code block",
    "html_block": "raw HTML",
    "hr": "a horizontal rule",
}


def _image_with_span(state: StateInline, silent: bool) -> bool:
    """Parse an image and record where it sat in the paragraph source.

    Args:
        state: The inline parser state.
        silent: True when the parser only checks that an image is there.

    Returns:
        True when an image was parsed.
    """
    start = state.pos
    if not image_rule(state, silent):
        return False
    if not silent:
        state.tokens[-1].meta["span"] = (start, state.pos)
    return True


def _build_parser() -> MarkdownIt:
    """Build the Markdown parser the deck format uses.

    Returns:
        A CommonMark parser with tables, the `figures` and `notes` containers,
        definition lists and dollar math enabled, and setext headings disabled.
    """
    md = MarkdownIt("commonmark")
    md.enable("table")
    md.disable("lheading")
    md.inline.ruler.at("image", _image_with_span)
    md.use(container_plugin, "figures")
    md.use(container_plugin, "notes")
    md.use(deflist_plugin)
    md.use(dollarmath_plugin, **MATH_RULES)
    return md


_PARSER = _build_parser()  # building one costs more than parsing a small deck


@dataclass(frozen=True, slots=True)
class TextSource:
    """Where one piece of slide text was written in the deck file.

    Attributes:
        text: The text as the slide holds it.
        lines: The first line and the line after the last, counted from 0
            over the whole file.
        column: The index of the cell in its row, for a table cell only.
    """

    text: str
    lines: tuple[int, int]
    column: int | None = None


@dataclass(slots=True)
class _Draft:
    """What the Markdown body of one slide holds.

    The options have not been applied yet.
    """

    title: str | None = None
    sentences: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    math: list[str] = field(default_factory=list)
    embeds: list[Embed] = field(default_factory=list)
    table: Table | None = None
    html: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: dict[str, TextSource] = field(default_factory=dict)


def split_frontmatter(
    text: str, *, source: Path | str
) -> tuple[dict[str, Any], str]:
    """Split the deck frontmatter from the slides.

    Args:
        text: The whole Markdown file.
        source: The file the text came from, used in the error messages.

    Returns:
        The frontmatter mapping, empty when the file has none, and the rest of
        the file, with its line endings normalised.

    Raises:
        DeckError: If the frontmatter block is never closed, holds unreadable
            YAML, or does not hold a mapping. A first line of `---` always opens
            frontmatter, so a file that starts with a slide separator gets this
            error, not a silent skip.
    """
    body = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = body.split("\n")
    if lines[0].strip() != "---":
        return {}, body
    hint = (
        'If that first "---" is meant as a slide separator, delete it; '
        "otherwise write the settings as key: value lines."
    )
    for number, line in enumerate(lines[1:], start=1):
        if line.strip() in _FRONTMATTER_END:
            block = "\n".join(lines[1:number])
            data = parse_yaml(block, origin=source)
            rest = "\n".join(lines[number + 1 :])
            if isinstance(data, Mapping):
                return dict(data), rest
            if data is None and not block.strip():
                return {}, rest
            raise DeckError(
                f'The file opens with "---", which starts frontmatter, but the '
                f'block up to the next "---" '
                f"does not hold deck settings. {hint}",
                source=source,
            )
    raise DeckError(
        f"The file opens with a frontmatter block that is never closed; add a "
        f"line holding --- after the deck settings. {hint}",
        source=source,
    )


def parse_markdown(
    text: str, *, source: Path | str, defaults: Mapping[str, Any] | None = None
) -> Deck:
    """Parse a Markdown deck file into a `mkdeck.model.Deck`.

    The deck takes its settings from the frontmatter, laid over `defaults`. A
    deck that sets no `title` opens with no generated title slide, and takes the
    first `#` heading of the deck, else `DEFAULT_TITLE`, as the title of the
    page.

    Args:
        text: The whole Markdown file.
        source: The path of the file, used in the error messages. It is never
            read.
        defaults: Deck settings the frontmatter overrides, as `mkdeck.config`
            reads them from a `deck.yml`.

    Returns:
        The parsed deck, already validated.

    Raises:
        DeckError: If the file, or one of its slides, breaks a rule of the
            format.
    """
    frontmatter, body = split_frontmatter(text, source=source)
    settings = merge_settings(
        defaults or {}, normalize_settings(frontmatter, origin=source)
    )
    fields: dict[str, Any] = {"title": DEFAULT_TITLE, **settings}
    if "title" not in settings:
        fields["title_slide"] = (
            # a deck that names no title has nothing to put on an opening slide
            False
        )
    deck = Deck(**fields)
    deck.slides.extend(slide for slide, _ in _read_slides(body, source=source))
    if (
        "title" not in settings
    ):  # the browser tab still wants a name: the first heading of the deck
        deck.title = next(
            (slide.title for slide in deck.slides if slide.title), DEFAULT_TITLE
        )
    validate_deck(deck, source=source)
    return deck


def locate_text(
    text: str, *, source: Path | str
) -> list[dict[str, TextSource]]:
    """Find where each piece of editable slide text sits in a deck file.

    A piece is keyed the way the renderer marks it: `title`, `sentence:N`,
    `bullet:N`, and `cell:R:C` with `R` = -1 for the header row. Text with no
    single place of its own is left out: a title or bullets set in the
    options comment, a sentence that shares its paragraph with a figure, a
    bullet of more than one paragraph, and a definition-list bullet.

    Args:
        text: The whole Markdown file.
        source: The path of the file, used in the error messages.

    Returns:
        One mapping per slide of the parsed deck, in order.

    Raises:
        DeckError: If the file does not parse as a deck.
    """
    _, body = split_frontmatter(text, source=source)
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    offset = normalized.count("\n") - body.count("\n")
    return [
        {
            key: replace(
                found, lines=(found.lines[0] + offset, found.lines[1] + offset)
            )
            for key, found in draft.sources.items()
        }
        for _, draft in _read_slides(body, source=source)
    ]


def _read_slides(
    body: str, *, source: Path | str
) -> Iterator[tuple[Slide, _Draft]]:
    """Parse the slides of a deck body, skipping the empty pieces.

    Args:
        body: The deck file without its frontmatter.
        source: The path of the deck file, used in the error messages.

    Yields:
        Each slide, with the draft its body was read into.
    """
    index = 0
    for tokens in _split_slides(_PARSER.parse(body)):
        parsed = _parse_slide(tokens, index=index, source=source)
        if parsed is not None:
            index += 1
            yield parsed


def _split_slides(tokens: list[Token]) -> list[list[Token]]:
    """Cut the token stream of a deck file at every top-level line of dashes.

    Args:
        tokens: The block tokens of the deck file, frontmatter removed.

    Returns:
        The tokens of each slide, in order. A run of dashes nested in a list, a
        quote or a container is not a separator.
    """
    slides: list[list[Token]] = [[]]
    for token in tokens:
        if (
            token.type == "hr"
            and token.level == 0
            and token.markup.startswith("-")
        ):
            slides.append([])
        else:
            slides[-1].append(token)
    return slides


def _parse_slide(
    tokens: list[Token], *, index: int, source: Path | str
) -> tuple[Slide, _Draft] | None:
    """Parse the tokens between two slide separators into a slide.

    Args:
        tokens: The block tokens of the slide.
        index: The zero-based position the slide will take, used to name it.
        source: The path of the deck file, used in the error messages.

    Returns:
        The slide and the draft its body was read into, or `None` when the
        piece holds nothing at all.

    Raises:
        DeckError: If the slide breaks a rule of the format.
    """
    options, tokens = _take_options(tokens, index=index, source=source)
    fail = partial(
        DeckError,
        slide=slide_name(Slide(id=_option_id(options)), index),
        source=source,
    )
    draft = _Draft()
    _consume(tokens, draft, fail=fail)
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
    if not options and slide == Slide():
        return None
    _apply_options(slide, options, fail=fail)
    if slide.layout == "auto" and slide.title and _is_bare_title(slide):
        slide.layout = "title"
    return slide, draft


def _option_id(options: Mapping[str, Any]) -> str | None:
    """Read the id out of the slide options, for naming the slide in an error.

    Args:
        options: The options mapping, which has not been validated yet.

    Returns:
        The id as text, or `None` when the slide has none.
    """
    raw = options.get("id")
    return None if raw is None else str(raw)


def _starts_notes(comment: str) -> bool:
    """Say whether an HTML comment is speaker notes: its first text is `notes:`.

    Args:
        comment: The text between `<!--` and `-->`.

    Returns:
        True when the comment opens with `notes:`, in any case.
    """
    return comment.lstrip().lower().startswith("notes:")


def _looks_like_options(comment: str) -> bool:
    """Say whether an HTML comment is meant as slide options.

    Args:
        comment: The text between `<!--` and `-->`.

    Returns:
        True when a `key:` line names an option, or nearly does. A comment that
        starts with `notes:` is speaker notes, never options.
    """
    if _starts_notes(comment):
        return False
    known = (*SLIDE_OPTION_KEYS, *BODY_ONLY_KEYS)
    keys = (
        found.group("key").lower() for found in _OPTION_KEY.finditer(comment)
    )
    return any(
        key in known or difflib.get_close_matches(key, known, n=1, cutoff=0.75)
        for key in keys
    )


def _take_options(
    tokens: list[Token], *, index: int, source: Path | str
) -> tuple[dict[str, Any], list[Token]]:
    """Split the options comment off the front of a slide.

    Only a comment that reads as options is taken; any other comment is left for
    the body, where it stays invisible.

    Args:
        tokens: The block tokens of the slide.
        index: The zero-based position of the slide, used to name it.
        source: The path of the deck file, used in the error messages.

    Returns:
        The options mapping, empty when the slide has none, and the rest of the
        tokens.

    Raises:
        DeckError: If the comment reads as options but is not a YAML mapping.
    """
    if not tokens or tokens[0].type != "html_block":
        return {}, tokens
    raw = tokens[0].content.strip()
    if not (
        raw.startswith("<!--")
        and raw.endswith("-->")
        and _looks_like_options(raw[4:-3])
    ):
        return {}, tokens
    fail = partial(DeckError, slide=slide_name(Slide(), index), source=source)
    try:
        data = parse_yaml(raw[4:-3], origin=source)
    except DeckError as error:
        raise fail(
            f"The options comment is not valid. {error.message}"
        ) from error
    if not isinstance(data, Mapping):
        raise fail("The options comment has to be a list of key: value lines.")
    return dict(data), tokens[1:]


def _apply_options(
    slide: Slide,
    options: Mapping[str, Any],
    *,
    fail: Callable[[str], DeckError],
) -> None:
    """Put the options of a slide onto the slide, in place.

    Args:
        slide: The slide built from the Markdown body.
        options: The mapping from the options comment.
        fail: Builds the `DeckError` to raise from a message.

    Raises:
        DeckError: If an option is unknown, has the wrong shape, or repeats
            something the Markdown body already said.
    """
    for key, raw in options.items():
        name = str(key)
        if name in BODY_ONLY_KEYS:
            raise fail(
                f'This slide sets "{name}" in its options, but embeds, tables '
                f"and raw HTML are written in the "
                "Markdown body; move it there."
            )
        if name not in SLIDE_OPTION_KEYS:
            raise fail(
                f'This slide has the unknown option "{name}". '
                f"{suggest(name, SLIDE_OPTION_KEYS, noun='options')}"
            )
        if raw is None:
            continue
        value = _option_value(name, raw, fail=fail)
        current = getattr(slide, name)
        if _is_set(name, current) and current != value:
            raise fail(
                f'This slide sets "{name}" in its options and in its Markdown '
                f"body; keep one of the two."
            )
        setattr(slide, name, value)


def _option_value(
    name: str, raw: Any, *, fail: Callable[[str], DeckError]
) -> Any:
    """Coerce one option value to the type its field holds.

    Args:
        name: The option key.
        raw: The value the author wrote.
        fail: Builds the `DeckError` to raise from a message.

    Returns:
        The coerced value.

    Raises:
        DeckError: If the value has the wrong shape, or names a layout that does
            not exist.
    """
    if name in {"bullets", "math", "classes"}:
        return coerce_text_list(raw, key=name, fail=fail)
    value = coerce_text(raw, key=name, fail=fail)
    if name == "layout" and value not in LAYOUTS:
        raise fail(
            f'This slide has the unknown layout "{value}". '
            f"{suggest(value, LAYOUTS, noun='layouts')}"
        )
    return value


def _is_set(name: str, value: Any) -> bool:
    """Say whether a slide field already holds something.

    The Markdown body is what put it there.

    Args:
        name: The field name.
        value: The value the field holds.

    Returns:
        `True` when the field is not at its default.
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
        `True` when the heading is the only content, which makes it a title
        slide.
    """
    return not (
        slide.sentence
        or slide.bullets
        or slide.math
        or slide.embeds
        or slide.table
        or slide.html
    )


def _consume(
    tokens: list[Token], draft: _Draft, *, fail: Callable[[str], DeckError]
) -> None:
    """Walk a run of block tokens and pour them into a draft slide.

    Args:
        tokens: The tokens of the slide body, or of one container inside it.
        draft: The draft to fill.
        fail: Builds the `DeckError` to raise from a message.

    Raises:
        DeckError: If the body holds a second heading or table, or a construct
            with no home in the slide model.
    """
    index = 0
    while index < len(tokens):
        token = tokens[index]
        kind = token.type
        if kind == "heading_open":
            end = _close(tokens, index)
            if draft.title is not None:
                raise fail(
                    "This slide holds two headings, but a slide takes one; "
                    "move the second onto a new slide."
                )
            draft.title = _inline_text(tokens[index + 1 : end])
            draft.sources["title"] = TextSource(draft.title, _lines(token))
            index = end + 1
        elif kind == "paragraph_open":
            end = _close(tokens, index)
            _consume_paragraph(tokens[index : end + 1], draft)
            index = end + 1
        elif kind in {"bullet_list_open", "ordered_list_open"}:
            end = _close(tokens, index)
            _list_items(tokens[index + 1 : end], draft, fail=fail)
            index = end + 1
        elif kind == "dl_open":
            end = _close(tokens, index)
            draft.bullets.extend(
                _definition_items(tokens[index + 1 : end], fail=fail)
            )
            index = end + 1
        elif kind in {"math_block", "math_block_label"}:
            draft.math.append(token.content.strip())
            index += 1
        elif kind == "table_open":
            end = _close(tokens, index)
            if draft.table is not None:
                raise fail(
                    "This slide holds two tables, but a slide takes one; move "
                    "the second onto a new slide."
                )
            draft.table = _parse_table(tokens[index : end + 1], draft)
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
            draft.notes.append(
                _inline_text(tokens[index + 1 : end], join="\n\n")
            )
            index = end + 1
        elif kind == "hr":
            index += 1
        else:
            raise fail(
                f"This slide holds {_describe_token(kind)}, which has no place "
                f"on a slide; "
                "write it as bullets, a table, or raw HTML."
            )


def _close(tokens: list[Token], start: int) -> int:
    """Find the token that closes the one at `start`.

    Args:
        tokens: The run of tokens.
        start: The index of an opening token.

    Returns:
        The index of the matching closing token.
    """
    depth = 0
    for index in range(start, len(tokens)):
        depth += tokens[index].nesting
        if depth == 0:
            return index
    raise AssertionError(
        "markdown-it left a block token open"
    )  # its own parser balances every pair


def _lines(token: Token) -> tuple[int, int]:
    """Read the lines a block token covers.

    Args:
        token: An opening block token.

    Returns:
        The first line and the line after the last, counted from 0.
    """
    assert token.map is not None  # markdown-it maps every opening block token
    return token.map[0], token.map[1]


def _inline_text(tokens: list[Token], *, join: str = " ") -> str:
    """Collect the source text of every inline token in a run.

    Args:
        tokens: The run of tokens.
        join: What to put between the pieces.

    Returns:
        The joined text, as it was written in the Markdown.
    """
    pieces = [
        token.content.strip() for token in tokens if token.type == "inline"
    ]
    return join.join(piece for piece in pieces if piece)


def _consume_paragraph(tokens: list[Token], draft: _Draft) -> None:
    """Turn one paragraph into embeds, a sentence, or both.

    A paragraph of images is a row of figures. The Markdown around an image
    stays a sentence, exactly as it was written, so that inline formatting and
    `$...$` math reach the renderer untouched.

    Args:
        tokens: The tokens from `paragraph_open` to `paragraph_close`.
        draft: The draft to fill.
    """
    inline = next((token for token in tokens if token.type == "inline"), None)
    if inline is None:
        return
    images = [child for child in inline.children or [] if child.type == "image"]
    for image in images:
        embed = Embed(
            src=str(image.attrGet("src") or ""),
            label=image.content.strip() or None,
        )
        embed.kind = resolve_embed_kind(embed)
        draft.embeds.append(embed)
    text = inline.content
    for image in reversed(images):
        text = _cut_image(text, *image.meta["span"])
    text = _BLANK_RUN.sub("\n", text).strip()
    if text:
        if not images:  # an edit there would have to keep the figure
            key = f"sentence:{len(draft.sentences)}"
            draft.sources[key] = TextSource(text, _lines(tokens[0]))
        draft.sentences.append(text)


def _cut_image(text: str, start: int, end: int) -> str:
    """Cut an image out of its paragraph.

    Also drop the link or emphasis that held nothing else.

    `[![Run](a.png)](https://example.org)` and `*![Run](a.png)*` are still a
    figure, and what wrapped the image must not be left behind as an empty link
    or a stray `**`.

    Args:
        text: The source of the paragraph.
        start: Where the image begins in it.
        end: Where the image ends.

    Returns:
        The text without the image and its now empty wrappers.
    """
    before, after = text[:start], text[end:]
    while True:
        link = _LINK_TAIL.match(after)
        if link and before.endswith("["):
            before, after = before[:-1], after[link.end() :]
            continue
        mark = next(
            (
                mark
                for mark in _EMPHASIS
                if before.endswith(mark) and after.startswith(mark)
            ),
            None,
        )
        if mark is None:
            return before + after
        before, after = before[: -len(mark)], after[len(mark) :]


def _item_text(tokens: list[Token], *, fail: Callable[[str], DeckError]) -> str:
    """Read the text of one list item or definition.

    Args:
        tokens: The tokens between the item's open and close.
        fail: Builds the `DeckError` to raise from a message.

    Returns:
        The Markdown text of the item, its paragraphs joined by a space.

    Raises:
        DeckError: If the item holds anything but paragraphs of text, such as a
            nested list.
    """
    pieces: list[str] = []
    for token in tokens:
        if token.type == "inline":
            pieces.append(token.content.strip())
        elif token.type in {"bullet_list_open", "ordered_list_open"}:
            raise fail(
                "This slide holds a nested list, but a slide takes one flat "
                "list of bullets; "
                "flatten it, or write the sub-points in the text of the bullet."
            )
        elif token.type not in {"paragraph_open", "paragraph_close"}:
            raise fail(
                f"This slide holds {_describe_token(token.type)} inside a "
                f"bullet, but a bullet holds only text; "
                "move it out of the list, or write it as raw HTML."
            )
    return " ".join(piece for piece in pieces if piece)


def _list_items(
    tokens: list[Token], draft: _Draft, *, fail: Callable[[str], DeckError]
) -> None:
    """Read the items of a list into the bullets of a draft.

    Args:
        tokens: The tokens between the list open and close.
        draft: The draft to fill.
        fail: Builds the `DeckError` to raise from a message.
    """
    index = 0
    while index < len(tokens):
        if tokens[index].type == "list_item_open":
            end = _close(tokens, index)
            item = tokens[index + 1 : end]
            if text := _item_text(item, fail=fail):
                paragraphs = [t for t in item if t.type == "paragraph_open"]
                if len(paragraphs) == 1:
                    key = f"bullet:{len(draft.bullets)}"
                    draft.sources[key] = TextSource(text, _lines(paragraphs[0]))
                draft.bullets.append(text)
            index = end + 1
        else:
            index += 1


def _definition_items(
    tokens: list[Token], *, fail: Callable[[str], DeckError]
) -> list[str]:
    """Read a definition list as bullets of the form `term: definition`.

    Args:
        tokens: The tokens between `dl_open` and `dl_close`.
        fail: Builds the `DeckError` to raise from a message.

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
            text = _item_text(tokens[index + 1 : end], fail=fail)
            if kind == "dt_open":
                term = text
            elif text:
                items.append(f"{term}: {text}" if term else text)
            index = end + 1
        else:
            index += 1
    return items


def _parse_table(tokens: list[Token], draft: _Draft) -> Table:
    """Read a GFM table.

    Args:
        tokens: The tokens from `table_open` to `table_close`.
        draft: The draft whose sources record where each cell sits.

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
            cells = columns if section == "thead_open" else row
            if cells is None:
                continue
            key = f"cell:{len(rows) if cells is row else -1}:{len(cells)}"
            draft.sources[key] = TextSource(
                text, _lines(token), column=len(cells)
            )
            cells.append(text)
    return Table(columns=columns, rows=rows)


def _code_html(token: Token) -> str:
    """Turn a code block into the raw HTML a slide carries.

    A `mermaid` fence becomes a `<deck-mermaid>` element, which the front-end
    renders on the slides that hold one. Every other fence becomes a code block.

    Args:
        token: The `fence` or `code_block` token.

    Returns:
        The HTML for the block, with the code escaped and its indentation kept.
    """
    info = token.info.strip().split()[0].lower() if token.info.strip() else ""
    code = html_escape(token.content.rstrip("\n"), quote=False)
    if info == "mermaid":
        return f"<deck-mermaid>{code}</deck-mermaid>"
    language = f' class="language-{html_escape(info)}"' if info else ""
    return f"<pre><code{language}>{code}</code></pre>"


def _consume_html(token: Token, draft: _Draft) -> None:
    """Take a raw HTML block, or the speaker notes hidden in a comment.

    A comment that is not a `notes:` comment is dropped, as in any Markdown
    renderer.

    Args:
        token: The `html_block` token.
        draft: The draft to fill.
    """
    raw = token.content.strip()
    if raw.startswith("<!--") and raw.endswith("-->"):
        inner = raw[4:-3].strip()
        if _starts_notes(inner) and (note := inner[len("notes:") :].strip()):
            draft.notes.append(note)
        return
    if raw:
        draft.html.append(raw)


def _describe_token(kind: str) -> str:
    """Name a block token for an error message.

    Args:
        kind: The token type, such as `blockquote_open`.

    Returns:
        A phrase such as `a blockquote`.
    """
    if kind in _TOKEN_NAMES:
        return _TOKEN_NAMES[kind]
    name = kind.removesuffix("_open").replace("_", " ")
    article = "an" if name[:1] in {"a", "e", "i", "o", "u"} else "a"
    return f"{article} {name}"
