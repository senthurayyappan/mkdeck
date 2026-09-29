# API reference

Look up every public class and function of mkdeck.

You import everything on this page from the top-level `mkdeck` package. The one exception is the rollout converter, which lives in `mkdeck.rollout`. The public modules are `mkdeck`, `mkdeck.errors`, and `mkdeck.rollout`. Every other module is an implementation detail, and it can change between releases.

`Deck.build` and `Deck.serve` write and show a deck that you build in Python. `load_source(...)` returns a `DeckSource` with the same two methods for a deck written in Markdown. These are the only entry points. See [Build a deck from Python](python/build-a-deck.md) for how they fit together.

## The slide model

Markdown produces these classes, and the renderer reads them. You can also build them yourself.

::: mkdeck.Deck

::: mkdeck.Slide

::: mkdeck.Embed

::: mkdeck.Table

::: mkdeck.DEFAULT_UNITS

## Load a deck from disk

::: mkdeck.load_source

::: mkdeck.DeckSource

## Errors and warnings

::: mkdeck.DeckError

::: mkdeck.DeckWarning

## Rollouts

`mkdeck rollout` calls `convert_brax_html`. It reads one Brax playback page. It writes a `.rollout` file and, for a model it has not seen, a shared `.meshes` file. A page with no Brax scene raises `NotBraxPage`, which is a `DeckError`. A caller that converts a folder of pages can catch it and skip the page.

::: mkdeck.rollout.convert_brax_html

::: mkdeck.rollout.Converted

::: mkdeck.rollout.NotBraxPage
