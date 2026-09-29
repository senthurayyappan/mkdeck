# Load a deck

Read a Markdown deck into Python, change it, and build it.

```python
from mkdeck import load_source

load_source("talk").build("site/")
```

`load_source` reads a Markdown deck and its `deck.yml`. It returns a `DeckSource`, which has the same `build` and `serve` methods as a `Deck`.

## Point at a deck

`load_source` accepts a Markdown file, or a folder that holds `deck.md` or `slides.md`. It reads `deck.yml` and the frontmatter once, and the frontmatter wins key by key.

## Change a deck before you build

A `DeckSource` has three attributes:

| Attribute | What it holds |
| --- | --- |
| `deck` | The `Deck` that mkdeck read |
| `directory` | The folder with the Markdown and its figures |
| `markdown` | The Markdown file |

To change the deck, edit `deck` and then build:

```python
from mkdeck import Slide, load_source

loaded = load_source("slides/deck.md")
loaded.deck.slides.append(Slide(sentence="One more result arrived."))
loaded.build("site/")
```

## Limits

!!! note
    `load_source` raises `DeckError` when the path holds no deck, when the file is not UTF-8 text, or when the deck breaks a rule.

Next: [Serve from Python](serve.md).
