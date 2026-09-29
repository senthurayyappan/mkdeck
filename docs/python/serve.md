# Serve from Python

Preview a deck from a script, and choose what reloads.

```python
deck.serve(port=5020)
```

`Deck.serve` builds the deck, serves it, and blocks until you press Ctrl-C. It takes the arguments of `mkdeck serve`: `host`, `port`, `open_browser`, and `reload`. It also takes `source`.

## Watch your figures

`deck.serve()` watches the folder in `source`, which is the current directory when you leave `source` out. When a file in it changes, mkdeck builds the same `Deck` again and the browser reloads.

The live reload covers your figures and stylesheets. However, it does not run the Python code that generates the slides. So to see a change to the slides, edit the script and restart it.

## Serve a deck from Markdown

`DeckSource.serve()` reads the Markdown again on every change under the folder, so an edit to `deck.md` or `deck.yml` reloads the page.

## Serve a deck that you change in Python

The first build of a served `DeckSource` uses `loaded.deck` with your changes. However, every later rebuild reads the files from disk again. As a result, your first edit to the Markdown drops your changes.

To serve a deck that you change in Python, serve the `Deck` itself. Point `source` at the deck folder:

```python
from mkdeck import Slide, load_source

loaded = load_source("slides/deck.md")
loaded.deck.slides.append(Slide(sentence="One more result arrived."))
loaded.deck.serve(source=loaded.directory)
```

With this pattern, figures reload but the Markdown does not.

## Limits

!!! note
    `serve` raises `DeckError` when it cannot render the deck, when the folder does not exist, or when another program uses the port.

Next: [Errors and warnings](messages.md).
