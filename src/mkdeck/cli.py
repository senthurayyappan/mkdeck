"""Command-line interface for mkdeck."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date as date_type
from pathlib import Path
from typing import Annotated

import typer

from mkdeck.build import build_source
from mkdeck.check import check_deck
from mkdeck.errors import DeckError
from mkdeck.export import export_deck
from mkdeck.rollout import convert_brax_html
from mkdeck.server import serve_source

app = typer.Typer(no_args_is_help=True)

DECK_TEMPLATE = """---
title: {title}
date: {date}
---

# {title}

---

Say the one thing this slide is for, in a single sentence.

- a supporting point
- another one, kept short

---
<!--
id: numbers
-->

Numbers such as 134 N s and 0.65 m are highlighted where they stand alone.

| Run | Cap | Crossings |
| --- | --- | --- |
| baseline | 18 N m | 2 |
| tuned | 22 N m | 5 |

---
<!--
id: figures
-->

Drop an HTML page or an image in assets/ and reference it to get a figure.

<!-- notes: two embeds sit side by side; one fills the slide. -->
"""

CONFIG_TEMPLATE = """# Configuration for this deck. The Markdown frontmatter wins over these keys.
theme: minimal

# Units a highlighted number may carry. Longest spelling first.
# units:
#   - N m
#   - mm
#   - s
"""


@contextmanager
def _reporting() -> Iterator[None]:
    """Turn a :class:`~mkdeck.errors.DeckError` into a clean message.

    Yields:
        Nothing; the body runs inside the handler.

    Raises:
        Exit: With status 1 when the body raises a deck error.
    """
    try:
        yield
    except DeckError as exc:
        typer.secho(f"mkdeck: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from None


def _parse_size(text: str) -> tuple[int, int]:
    """Parse a ``WIDTHxHEIGHT`` viewport option.

    Args:
        text: The option value, such as ``1920x1080``.

    Returns:
        The width and height in pixels.

    Raises:
        DeckError: If the value is not two positive integers joined by ``x``.
    """
    parts = text.lower().split("x")
    if len(parts) != 2:
        raise DeckError(f"--size {text!r} is not a viewport; write it as WIDTHxHEIGHT, for example 1920x1080.")
    try:
        width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise DeckError(f"--size {text!r} is not a viewport; write it as WIDTHxHEIGHT, for example 1920x1080.") from exc
    if width <= 0 or height <= 0:
        raise DeckError(f"--size {text!r} needs a positive width and height.")
    return width, height


@app.callback()
def main() -> None:
    """Build, serve and check minimal HTML slide decks."""


@app.command()
def new(
    name: Annotated[Path, typer.Argument(help="Folder to create the deck in.")],
) -> None:
    """Scaffold a deck folder with deck.md, deck.yml and assets/."""
    with _reporting():
        folder = Path(name)
        if folder.exists() and any(folder.iterdir()):
            raise DeckError(f"{folder} already exists and is not empty.")
        (folder / "assets").mkdir(parents=True, exist_ok=True)
        (folder / "assets" / ".gitkeep").touch()
        title = folder.resolve().name.replace("-", " ").replace("_", " ").strip().title() or "Slide Deck"
        deck = folder / "deck.md"
        deck.write_text(
            DECK_TEMPLATE.format(title=title, date=date_type.today().isoformat()),
            encoding="utf-8",
        )
        (folder / "deck.yml").write_text(CONFIG_TEMPLATE, encoding="utf-8")
        typer.echo(f"Created {deck}")
        typer.echo(f"Serve it with: mkdeck serve {folder}")


@app.command()
def serve(
    path: Annotated[Path, typer.Argument(help="A .md file, or a folder holding deck.md.")],
    port: Annotated[int, typer.Option("--port", help="Port to listen on.")] = 5020,
    host: Annotated[str, typer.Option("--host", help="Interface to bind.")] = "127.0.0.1",
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open the deck in a browser.")] = False,
    no_reload: Annotated[bool, typer.Option("--no-reload", help="Do not watch the source for changes.")] = False,
) -> None:
    """Serve the deck and rebuild it whenever its source changes."""
    with _reporting():
        serve_source(path, host=host, port=port, open_browser=open_browser, reload=not no_reload)


@app.command()
def build(
    path: Annotated[Path, typer.Argument(help="A .md file, or a folder holding deck.md.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Folder to write the deck into.")] = Path("site"),
    single_file: Annotated[
        bool, typer.Option("--single-file", help="Inline the CSS and JS so the deck opens from file://.")
    ] = False,
) -> None:
    """Write the deck to an output folder."""
    with _reporting():
        index = build_source(path, out, single_file=single_file)
        typer.echo(f"Wrote {index}")


@app.command()
def check(
    path: Annotated[Path, typer.Argument(help="A .md file, a folder holding deck.md, or a built .html.")],
    size: Annotated[str, typer.Option("--size", help="Viewport, as WIDTHxHEIGHT.")] = "1920x1080",
    out: Annotated[Path, typer.Option("--out", help="Folder for the report and screenshots.")] = Path("report"),
    shots: Annotated[bool, typer.Option("--shots/--no-shots", help="Write one PNG per slide.")] = True,
) -> None:
    """Open every slide in headless Chromium and report what overflows."""
    with _reporting():
        check_deck(path, out=out, size=_parse_size(size), shots=shots)


@app.command()
def export(
    path: Annotated[Path, typer.Argument(help="A .md file, a folder holding deck.md, or a built .html.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="PDF to write.")] = Path("deck.pdf"),
    size: Annotated[str, typer.Option("--size", help="Page size, as WIDTHxHEIGHT.")] = "1920x1080",
) -> None:
    """Print the deck to a PDF, one page per slide."""
    with _reporting():
        export_deck(path, out, size=_parse_size(size))


@app.command()
def rollout(
    pages: Annotated[list[Path], typer.Argument(help="Brax playback pages to convert.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Folder to write the rollouts into.")] = Path("assets"),
) -> None:
    """Convert Brax playback pages into rollouts that play offline.

    Each page keeps only its own poses; the meshes go into one shared file per
    model, so a deck that shows a robot on thirty slides carries it once.
    """
    with _reporting():
        before = 0
        after = 0
        for page in pages:
            converted = convert_brax_html(page, out)
            before += page.stat().st_size
            after += converted.rollout.stat().st_size
            if not converted.shared:
                after += converted.meshes.stat().st_size
            shared = "shared meshes" if converted.shared else f"new meshes {converted.meshes.name}"
            typer.echo(f"{page.name} -> {converted.rollout.name} ({shared})")
        if pages:
            typer.echo(f"{before / 1_000_000:.1f} MB of pages became {after / 1_000_000:.1f} MB of rollouts.")
