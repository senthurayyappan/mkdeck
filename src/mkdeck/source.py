"""Load a deck from disk.

That is a Markdown file, its `deck.yml` and the folder of its assets.
"""

from dataclasses import dataclass
from pathlib import Path

from mkdeck.config import read_config_file
from mkdeck.errors import DeckError
from mkdeck.markdown import parse_markdown
from mkdeck.model import Deck
from mkdeck.paths import read_text

__all__ = ["DECK_FILENAMES", "DeckSource", "find_markdown", "load_source"]

DECK_FILENAMES: tuple[str, ...] = ("deck.md", "slides.md")
"""Markdown filenames looked for when the path given is a folder."""


@dataclass(frozen=True, slots=True)
class DeckSource:
    """A deck loaded from disk, ready to build or serve.

    Attributes:
        deck: The parsed deck. The frontmatter and `deck.yml` are already merged
            into its fields, so the deck alone carries the settings.
        directory: The folder holding the Markdown and its assets.
        markdown: The Markdown file the deck came from.
    """

    deck: Deck
    directory: Path
    markdown: Path

    def build(
        self, out: Path | str = "site", *, single_file: bool = False
    ) -> Path:
        """Write the deck to an output folder, with the assets it names.

        Args:
            out: The output folder, or the HTML file when `single_file` is set
                and the path ends in `.html`.
            single_file: True to inline every stylesheet and script.

        Returns:
            The path of the written HTML document.

        Raises:
            DeckError: If a slide breaks a rule of the model, the output folder
                is the deck folder, or a file the deck names is outside the deck
                folder.
        """
        return self.deck.build(
            out, source=self.directory, single_file=single_file
        )

    def serve(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 5020,
        open_browser: bool = False,
        reload: bool = True,
    ) -> None:
        """Serve the deck until interrupted.

        Read it again whenever its folder changes.

        The first build uses `deck` as it is, but every rebuild reads the
        Markdown and `deck.yml` from disk again, so a change made to `deck` in
        Python shows only until the first edit. To serve a deck that is changed
        in Python, serve that `Deck` with `Deck.serve` instead.

        The folder is watched apart from the ones `mkdeck build`, `check` and
        `export` write into by default (`site`, `report` and `deck.pdf`).

        Args:
            host: The interface to bind.
            port: The port to bind.
            open_browser: True to open the deck in a browser once it is up.
            reload: True to watch the folder and push reloads.

        Raises:
            DeckError: If the deck cannot be rendered or the port is taken.
        """
        from mkdeck.build import (
            build_deck,  # imported here, so that `import mkdeck` loads neither
        )
        from mkdeck.server import serve  # the renderer nor the file watcher

        pending: DeckSource | None = self

        def build(root: Path, live: bool) -> None:
            nonlocal pending
            current, pending = (
                pending or load_source(self.markdown),
                None,
            )  # the first build reuses the deck in hand
            build_deck(
                current.deck, root, source=current.directory, live_reload=live
            )

        serve(
            build,
            watch_paths=[self.directory],
            host=host,
            port=port,
            open_browser=open_browser,
            reload=reload,
        )


def find_markdown(path: Path | str) -> Path:
    """Resolve a path to the Markdown file holding the deck.

    Args:
        path: A Markdown file, or a folder holding `deck.md` or `slides.md`.

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
        raise DeckError(
            f"The folder holds no deck; put a {listed} in it, or point mkdeck "
            f"at the file itself.",
            source=path,
        )
    raise DeckError("The path does not exist.", source=path)


def load_source(path: Path | str) -> DeckSource:
    """Load a deck and its settings from disk.

    The `deck.yml` beside the Markdown and the frontmatter are read once and
    merged into the fields of the deck, the frontmatter winning.

    Args:
        path: A Markdown file, or a folder holding `deck.md` or `slides.md`.

    Returns:
        The loaded deck, with its source folder.

    Raises:
        DeckError: If the path holds no deck, the file is not readable UTF-8
            text, or the deck cannot be parsed.
    """
    markdown = find_markdown(path)
    deck = parse_markdown(
        read_text(markdown),
        source=markdown,
        defaults=read_config_file(markdown),
    )
    return DeckSource(deck=deck, directory=markdown.parent, markdown=markdown)
