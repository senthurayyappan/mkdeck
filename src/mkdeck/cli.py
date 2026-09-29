"""Command-line interface for mkdeck."""

import json
import string
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date as date_type
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from mkdeck._messages import install_warning_formatter
from mkdeck.check import check_deck, report_text
from mkdeck.errors import DeckError
from mkdeck.export import export_deck
from mkdeck.rollout import ROLLOUT_SUFFIX, NotBraxPage, convert_brax_html
from mkdeck.source import load_source

__all__ = ["app"]

app = typer.Typer(no_args_is_help=True)

DECK_TEMPLATE = """---
title: {title_yaml}
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

# Units a highlighted number may carry, in any order. Setting this replaces the defaults.
# units:
#   - N m
#   - mm
#   - s
"""


@contextmanager
def _reporting() -> Iterator[None]:
    """Turn a deck error, or a file that cannot be read or written, into a clean message.

    Yields:
        Nothing; the body runs inside the handler.

    Raises:
        Exit: With status 1 when the body raises a deck error, an
            :class:`OSError` or a :class:`UnicodeDecodeError`.
    """
    try:
        yield
    except DeckError as exc:
        _fail(str(exc))
    except OSError as exc:
        _fail(f"{exc.strerror}: {exc.filename}" if exc.strerror and exc.filename else str(exc))
    except UnicodeDecodeError as exc:
        _fail(f"{exc}; a deck and its config are UTF-8 text.")


def _fail(message: str) -> NoReturn:
    """Print an error the way every command does, and exit.

    Args:
        message: What went wrong.

    Raises:
        Exit: Always, with status 1.
    """
    typer.secho(f"mkdeck: {message}", err=True, fg=typer.colors.RED)
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


def _installed_version() -> str:
    """Name the installed release, or ``unknown`` when mkdeck runs from a bare source tree."""
    try:
        return version("mkdeck")
    except PackageNotFoundError:
        return "unknown"


def _show_version(show: bool) -> None:
    """Print the version and exit, for ``--version``."""
    if show:
        typer.echo(f"mkdeck {_installed_version()}")
        raise typer.Exit()


@app.callback()
def main(
    show_version: Annotated[
        bool,
        typer.Option("--version", callback=_show_version, is_eager=True, help="Show the version and exit."),
    ] = False,
) -> None:
    """Build, serve and check minimal HTML slide decks."""
    install_warning_formatter()


@app.command()
def new(
    name: Annotated[Path, typer.Argument(help="Folder to create the deck in.")],
) -> None:
    """Scaffold a deck folder with deck.md, deck.yml and assets/."""
    with _reporting():
        folder = Path(name)
        if folder.exists() and not folder.is_dir():
            raise DeckError(f"{folder} already exists and is not a folder.")
        if folder.exists() and any(folder.iterdir()):
            raise DeckError(f"{folder} already exists and is not empty.")
        (folder / "assets").mkdir(parents=True, exist_ok=True)
        (folder / "assets" / ".gitkeep").touch()
        title = string.capwords(folder.resolve().name.replace("-", " ").replace("_", " ")) or "Slide Deck"
        deck = folder / "deck.md"
        # A JSON string is a YAML string, so a title such as "a: b" or "yes" survives the frontmatter.
        deck.write_text(
            DECK_TEMPLATE.format(
                title=title, title_yaml=json.dumps(title, ensure_ascii=False), date=date_type.today().isoformat()
            ),
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
    reload: Annotated[
        bool, typer.Option("--reload/--no-reload", help="Watch the source and rebuild when it changes.")
    ] = True,
) -> None:
    """Serve the deck and rebuild it whenever its source changes."""
    with _reporting():
        load_source(path).serve(host=host, port=port, open_browser=open_browser, reload=reload)


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
        index = load_source(path).build(out, single_file=single_file)
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
        viewport = _parse_size(size)
        records = check_deck(path, out=out, size=viewport, shots=shots)
        typer.echo(report_text(records, size=viewport, path=path), nl=False)


@app.command()
def export(
    path: Annotated[Path, typer.Argument(help="A .md file, a folder holding deck.md, or a built .html.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="PDF to write.")] = Path("deck.pdf"),
    size: Annotated[str, typer.Option("--size", help="Page size, as WIDTHxHEIGHT.")] = "1920x1080",
) -> None:
    """Print the deck to a PDF, one page per slide.

    The PDF is still: an embedded page prints as it looks once loaded, a rollout
    prints as its first frame, and a Mermaid diagram needs a network to draw.
    """
    with _reporting():
        typer.echo(f"Wrote {export_deck(path, out, size=_parse_size(size))}")


@app.command()
def rollout(
    pages: Annotated[list[Path], typer.Argument(help="Brax playback pages to convert.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Folder to write the rollouts into.")] = Path("assets"),
) -> None:
    """Convert Brax playback pages into rollouts that play offline.

    Each page keeps only its own poses; the meshes go into one shared file per
    model, so a deck that shows a robot on thirty slides carries it once.

    A page that holds no Brax scene is skipped rather than fatal, because an
    assets folder normally mixes playback pages with plots. A page that holds a
    scene that cannot be converted is reported and the rest are still
    converted, but the command then exits with an error.
    """
    with _reporting():
        pages = list(dict.fromkeys(pages))
        by_stem: dict[str, list[Path]] = {}
        for page in pages:
            by_stem.setdefault(page.stem, []).append(page)
        clashes = [
            f"{' and '.join(str(page) for page in group)} would both become {stem}{ROLLOUT_SUFFIX}"
            for stem, group in by_stem.items()
            if len(group) > 1
        ]
        if clashes:
            raise DeckError("; ".join(clashes) + ". Rename one of each pair.")
        before = after = skipped = failed = 0
        for page in pages:
            try:
                converted = convert_brax_html(page, out)
            except NotBraxPage:
                skipped += 1
                typer.secho(f"{page.name} skipped; it is not a Brax playback page.", err=True, fg=typer.colors.YELLOW)
                continue
            except DeckError as exc:
                failed += 1
                typer.secho(f"mkdeck: {exc}", err=True, fg=typer.colors.RED)
                continue
            before += page.stat().st_size
            after += converted.rollout.stat().st_size
            if not converted.shared:
                after += converted.meshes.stat().st_size
            shared = "shared meshes" if converted.shared else f"new meshes {converted.meshes.name}"
            typer.echo(f"{page.name} -> {converted.rollout.name} ({shared})")
        if skipped == len(pages):
            raise DeckError("none of those pages hold a Brax scene, so there was nothing to convert.")
        if before:
            typer.echo(f"{before / 1_000_000:.1f} MB of pages became {after / 1_000_000:.1f} MB of rollouts.")
        if failed:
            raise DeckError(f"{failed} of {len(pages)} pages could not be converted.")
