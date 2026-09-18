"""Minimal HTML slide decks from Markdown or from Python.

The public API is the slide model, the Markdown parser and the renderer::

    from mkdeck import Deck, Slide, Embed

    deck = Deck(title="Quadruped Vault Runs", date="2026-09-18")
    deck.slides.append(
        Slide(
            sentence="Five seeds cross the wall.",
            embeds=[Embed("assets/g1.html", label="18 N m"), Embed("assets/g2.html", label="22 N m")],
        )
    )
    deck.build("site/")  # or deck.serve(port=5020)
"""

from mkdeck.build import DeckSource, build_deck, build_source, load_source
from mkdeck.config import DeckConfig
from mkdeck.errors import DeckError
from mkdeck.markdown import parse_markdown
from mkdeck.model import Deck, Embed, Slide, Table
from mkdeck.render import DEFAULT_UNITS, render_deck, render_slide
from mkdeck.server import serve_deck, serve_source

__all__ = [
    "DEFAULT_UNITS",
    "Deck",
    "DeckConfig",
    "DeckError",
    "DeckSource",
    "Embed",
    "Slide",
    "Table",
    "build_deck",
    "build_source",
    "load_source",
    "parse_markdown",
    "render_deck",
    "render_slide",
    "serve_deck",
    "serve_source",
]
