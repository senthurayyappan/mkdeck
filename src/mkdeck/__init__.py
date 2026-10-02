"""Minimal HTML slide decks from Markdown or from Python.

The public API is the slide model and the two ways to get a deck: build one in
Python, or load one from a Markdown file. Either way, `build` writes it and
`serve` shows it::

    from mkdeck import Deck, Slide, Embed, load_source

    deck = Deck(title="Quadruped Vault Runs", date="2026-09-18")
    deck.slides.append(
        Slide(
            sentence="Five seeds cross the wall.",
            embeds=[
                Embed("assets/g1.html", label="18 N m"),
                Embed("assets/g2.html", label="22 N m"),
            ],
        )
    )
    deck.build("site/")  # or deck.serve(port=5020)

    load_source("talk").build("site/")  # a deck.md and its assets/ folder

The public modules are `mkdeck`, `mkdeck.errors` and `mkdeck.rollout`. Every
other module is an implementation detail and can change between releases.
"""

from importlib.metadata import PackageNotFoundError, version

from mkdeck.errors import DeckError, DeckWarning
from mkdeck.model import DEFAULT_UNITS, Deck, Embed, Slide, Table
from mkdeck.source import DeckSource, load_source

try:
    __version__ = version("mkdeck")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = [
    "DEFAULT_UNITS",
    "Deck",
    "DeckError",
    "DeckSource",
    "DeckWarning",
    "Embed",
    "Slide",
    "Table",
    "__version__",
    "load_source",
]
