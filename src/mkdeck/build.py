"""Load a deck from disk and write a self-contained site for it."""

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from mkdeck.config import CONFIG_FILENAMES, DeckConfig, apply_config, load_config
from mkdeck.errors import DeckError
from mkdeck.markdown import parse_markdown, split_frontmatter
from mkdeck.model import Deck
from mkdeck.render import ASSET_ROOT, DEFAULT_ASSET_BASE, REMOTE_PREFIXES, inline_assets, render_deck

DECK_FILENAMES: tuple[str, ...] = ("deck.md", "slides.md")
"""Markdown filenames looked for when the path given is a folder."""

EMBED_WARN_BYTES = 2_000_000
"""An embed larger than this is called out at build time."""

ASSETS_DIRNAME = "assets"
"""The deck's own asset folder, copied into the output as it stands."""


def _warn(message: str) -> None:
    """Print a non-fatal warning to standard error.

    Args:
        message: The text to show, without a trailing newline.
    """
    print(f"mkdeck: warning: {message}", file=sys.stderr)


@dataclass(slots=True)
class DeckSource:
    """A deck loaded from disk, with everything the renderer needs.

    Attributes:
        deck: The parsed deck, with the merged configuration already applied.
        config: The merged configuration, the frontmatter winning over ``deck.yml``.
        directory: The folder holding the Markdown and its assets.
        markdown: The Markdown file the deck came from.
        watched: The files the dev server watches for changes.
    """

    deck: Deck
    config: DeckConfig
    directory: Path
    markdown: Path
    watched: list[Path] = field(default_factory=list)


def find_markdown(path: Path | str) -> Path:
    """Resolve a path to the Markdown file holding the deck.

    Args:
        path: A Markdown file, or a folder holding ``deck.md`` or ``slides.md``.

    Returns:
        The Markdown file.

    Raises:
        DeckError: If the path does not exist or holds no deck.
    """
    path = Path(path)
    if path.is_file():
        return path
    if path.is_dir():
        for name in DECK_FILENAMES:
            candidate = path / name
            if candidate.is_file():
                return candidate
        listed = " or a ".join(DECK_FILENAMES)
        raise DeckError(f"holds no deck; put a {listed} in it, or point mkdeck at the file itself.", source=path)
    raise DeckError("does not exist.", source=path)


def load_source(path: Path | str) -> DeckSource:
    """Load a deck and its configuration from disk.

    The frontmatter and ``deck.yml`` are merged by
    :func:`mkdeck.config.load_config` and then copied onto the deck, so the deck
    alone carries the settings from there on.

    Args:
        path: A Markdown file, or a folder holding ``deck.md`` or ``slides.md``.

    Returns:
        The loaded deck, its configuration and its source folder.

    Raises:
        DeckError: If the path holds no deck, or the deck cannot be parsed.
    """
    markdown = find_markdown(path)
    directory = markdown.parent
    try:
        text = markdown.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeckError(f"could not be read: {exc.strerror}.", source=markdown) from exc
    frontmatter, _ = split_frontmatter(text, source=markdown)
    config = load_config(markdown, frontmatter=frontmatter)
    deck = parse_markdown(text, source=markdown)
    apply_config(deck, config)
    watched = [markdown, *(directory / name for name in CONFIG_FILENAMES if (directory / name).is_file())]
    return DeckSource(deck=deck, config=config, directory=directory, markdown=markdown, watched=watched)


def _copy_vendor_assets(out: Path, *, theme: str) -> None:
    """Copy the vendored front-end assets next to ``index.html``.

    Args:
        out: The output folder.
        theme: The theme name, checked so a typo is reported at build time.
    """
    if not ASSET_ROOT.is_dir():  # pragma: no cover - a broken installation
        _warn(f"the vendored assets are missing from this installation: {ASSET_ROOT}")
        return
    target = out / DEFAULT_ASSET_BASE
    for entry in sorted(ASSET_ROOT.iterdir()):
        if entry.name == "templates":
            continue
        destination = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, destination)
    if not (ASSET_ROOT / "themes" / f"{theme}.css").is_file():
        _warn(f"theme {theme!r} has no stylesheet in {ASSET_ROOT / 'themes'}; the deck will render unstyled.")


def _copy_file(rel: str, out: Path, *, source: Path, what: str) -> None:
    """Copy one file the document names, keeping its path relative to the deck.

    Args:
        rel: The path the document holds, relative to the deck source folder.
        out: The output folder.
        source: The deck source folder.
        what: What the file is, used in the warning when it is missing.
    """
    if rel.startswith(REMOTE_PREFIXES):
        return
    origin = source / rel
    if not origin.is_file():
        _warn(f"{what} not found, so it was not copied: {rel}")
        return
    destination = out / rel
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origin, destination)


def _copy_deck_assets(deck: Deck, out: Path, *, source: Path) -> None:
    """Copy the deck's own assets into the output folder.

    The whole ``assets/`` tree is copied when there is one. Every embed and
    every stylesheet or script the deck adds is copied on its own, keeping its
    path relative to the deck, because the document refers to it that way.

    Args:
        deck: The deck being built.
        out: The output folder.
        source: The deck source folder.
    """
    tree = source / ASSETS_DIRNAME
    if tree.is_dir() and tree.resolve() != (out / ASSETS_DIRNAME).resolve():
        shutil.copytree(tree, out / ASSETS_DIRNAME, dirs_exist_ok=True)
    for rel in (*deck.extra_css, *deck.extra_js):
        _copy_file(rel, out, source=source, what="stylesheet or script")
    # A deck normally shows the same embed on several slides, so each one is
    # handled once: the file is copied once and its warning is said once.
    seen: set[str] = set()
    for slide in deck.slides:
        for embed in slide.embeds:
            if embed.src.startswith(REMOTE_PREFIXES) or embed.src in seen:
                continue
            seen.add(embed.src)
            origin = source / embed.src
            if not origin.is_file():
                _warn(f"embed not found, so it was not copied: {embed.src}")
                continue
            size = origin.stat().st_size
            if size > EMBED_WARN_BYTES:
                _warn(f"embed {embed.src} is {size / 1_000_000:.1f} MB; a deck full of these is slow to open.")
            destination = out / embed.src
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, destination)


def build_deck(
    deck: Deck,
    out: Path | str = "site",
    *,
    config: DeckConfig | None = None,
    source: Path | None = None,
    single_file: bool = False,
) -> Path:
    """Write a deck to an output folder.

    Args:
        deck: The deck to build.
        out: The output folder, or the HTML file itself when ``single_file`` is
            set and the path ends in ``.html``.
        config: The merged deck configuration.
        source: The deck source folder, used to copy the deck's own assets.
        single_file: True to fold the stylesheets and scripts into the document,
            so the result opens from a ``file://`` URL.

    Returns:
        The path of the written HTML document.

    Raises:
        DeckError: If a slide breaks a rule of the model, or the output folder
            is the source folder.
    """
    out = Path(out)
    if single_file and out.suffix.lower() in {".html", ".htm"}:
        directory, index = out.parent or Path(), out
    else:
        directory, index = out, out / "index.html"
    if source is not None and directory.resolve() == Path(source).resolve():
        raise DeckError("The output folder is the deck source folder; write the build somewhere else with -o.")

    html = render_deck(deck, config=config)
    if single_file:
        html = inline_assets(html, source=source)
    directory.mkdir(parents=True, exist_ok=True)
    index.write_text(html, encoding="utf-8")
    if not single_file:
        _copy_vendor_assets(directory, theme=deck.theme or "minimal")
    if source is not None:
        _copy_deck_assets(deck, directory, source=Path(source))
    return index


def build_source(path: Path | str, out: Path | str = "site", *, single_file: bool = False) -> Path:
    """Load a deck from disk and build it.

    Args:
        path: A Markdown file, or a folder holding ``deck.md`` or ``slides.md``.
        out: The output folder, or the HTML file when ``single_file`` is set.
        single_file: True to fold the stylesheets and scripts into the document.

    Returns:
        The path of the written HTML document.

    Raises:
        DeckError: If the deck cannot be loaded or rendered.
    """
    loaded = load_source(path)
    return build_deck(
        loaded.deck,
        out,
        config=loaded.config,
        source=loaded.directory,
        single_file=single_file,
    )
