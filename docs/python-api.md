# Building from Python

Build the slides in Python when the deck reports numbers you already compute.
The deck then follows the data, and nobody retypes a value into Markdown.

```python
from mkdeck import Deck, Embed, Slide

deck = Deck(title="Vault runs", date="2026-09-18")

for run in runs:
    deck.slides.append(
        Slide(
            id=run.name,
            sentence=f"{run.crossings} of 5 seeds cross at {run.cap} N m.",
            embeds=[Embed(f"assets/{run.name}.html", label=run.label)],
        )
    )

deck.build("site/")
```

Use `deck.serve(port=5020)` while you work on the deck, and `deck.build()` when
you publish it. Both take a `source` argument, which names the folder that holds
your figures.

## The slide model

Markdown and Python meet here. The parser produces these classes, and the
renderer reads them. There is one code path, so the two ways of writing a deck
cannot drift apart.

| Class | Holds |
| --- | --- |
| `Deck` | The title, the date, the theme and the slides |
| `Slide` | One slide: a sentence, bullets, math, figures, a table or raw HTML |
| `Embed` | One figure: a source, a caption and a kind |
| `Table` | The columns and the rows of a table |

`Slide` carries the same fields as the options comment in Markdown, plus
`embeds`, `table` and `html`. See [Writing slides](writing-slides.md) for what
each field means, and the [API reference](api.md) for the signatures.

```python
from mkdeck import Slide, Table

Slide(
    id="torque-cap",
    sentence="The higher cap raises the crossing rate.",
    table=Table(columns=["Cap", "Crossings"], rows=[["18 N m", "2"], ["22 N m", "5"]]),
    notes="The 18 N m runs stall against the wall.",
)
```

## Read a deck that is already written

Load a Markdown deck, change it, then build it:

```python
from mkdeck import load_source

loaded = load_source("slides/deck.md")
loaded.deck.slides.append(Slide(sentence="One more result arrived."))
loaded.deck.build("site/", config=loaded.config, source=loaded.directory)
```

`load_source` accepts a Markdown file, or a folder that holds `deck.md`. It
returns the deck, the merged settings, the folder that holds the figures, and
the Markdown file itself.

## Errors

mkdeck raises `DeckError` for a deck that breaks a rule, such as three figures
on one slide or two slides with the same `id`. The message names the slide and
says how to fix it. The CLI prints the message and exits with status 1.

```python
from mkdeck import DeckError

try:
    deck.build("site/")
except DeckError as error:
    print(error)
```
