# API reference

Everything on this page is importable from the top-level `mkdeck` package,
apart from the rollout converter, which lives in `mkdeck.rollout`. The public
modules are `mkdeck`, `mkdeck.errors` and `mkdeck.rollout`. Every other module
is an implementation detail and can change between releases.

`Deck.build` and `Deck.serve` write and show a deck built in Python.
`load_source(...)` returns a `DeckSource` with the same two methods for a deck
written in Markdown. Those are the only entry points; see
[Building from Python](python-api.md) for how they fit together.

## The slide model

The classes the Markdown loader produces and the renderer reads. You can also
build them yourself.

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

`mkdeck rollout` calls this function. It reads one Brax playback page and
writes a `.rollout` file and, for a model it has not seen, its shared
`.meshes` file. A page that holds no Brax scene raises `NotBraxPage`, a
`DeckError` that a caller converting a folder of pages can catch and skip.

::: mkdeck.rollout.convert_brax_html

::: mkdeck.rollout.Converted

::: mkdeck.rollout.NotBraxPage
