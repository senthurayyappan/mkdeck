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

`Deck.build` and `Deck.serve` are the two ways to use a deck. Use
`deck.serve(port=5020)` while you work on it, and `deck.build("site/")` when you
publish it. Both take a `source` argument, which names the folder that holds
your figures. It defaults to the current directory and takes a string or a
`Path`. `build` also takes `single_file=True`, which writes one HTML document
that opens from a `file://` URL.

**Embeds and assets are resolved relative to `source`.** In the example above,
`Embed("assets/run3.html")` points at `./assets/run3.html`, so run the script
from the folder that holds `assets/`, or pass `source="slides/"` to name
another folder. mkdeck copies the `assets/` tree and every embed the slides
name into the build, and it refuses a path that leaves `source`.

Building again into the same folder brings it up to date: every file is copied
afresh, and a file the previous build wrote that this one no longer needs is
removed (mkdeck keeps a `.mkdeck-build.json` list in the folder for this).

`deck.serve()` rebuilds the deck when a file under `source` changes, and the
browser reloads. `source` is the current directory when you leave it out, so
`deck.serve()` watches the folder you run it from. It builds the `Deck` in hand
again, unchanged, and it does not run the Python code that generates the
slides. Edit the script and restart it to see the change; the live reload covers
your figures and stylesheets, not the loop that builds the slides.

## The slide model

Markdown and Python meet here. The Markdown loader produces these classes, and
the renderer reads them. There is one code path, so the two ways of writing a
deck cannot drift apart.

| Class | Holds |
| --- | --- |
| `Deck` | The title, the date, the theme, the units and the slides |
| `Slide` | One slide: a sentence, bullets, math, figures, a table or raw HTML |
| `Embed` | One figure: a source, a caption and a kind |
| `Table` | The columns and the rows of a table |

`Deck` carries every setting of `deck.yml` and of the frontmatter as a field:
`title`, `date`, `theme`, `units`, `extra_css`, `extra_js`, `reveal` and
`title_slide`. See [Writing slides](writing-slides.md#deck-settings) for what
each one means. `units` is the list of units the number marking recognises,
in any order, and it replaces `DEFAULT_UNITS`, which you can extend:

```python
from mkdeck import DEFAULT_UNITS, Deck

deck = Deck(title="Vault runs", units=[*DEFAULT_UNITS, "GPa"])
```

`Slide` carries the same fields as the options comment in Markdown, plus
`embeds`, `table` and `html`. See [Writing slides](writing-slides.md) for what
each field means, and the [API reference](api.md) for the signatures.

Text in a slide takes inline Markdown (`**bold**`, `*italic*`, `` `code` ``,
links) and passes raw HTML through unescaped. When the text comes from data you
do not control, such as a run name or a log line, escape it with `html.escape`
before you put it in the slide.

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

`load_source` reads a Markdown deck and its `deck.yml` into a `DeckSource`. It
builds and serves the same way a `Deck` does, and it knows where the deck's
figures are:

```python
from mkdeck import load_source

load_source("talk").build("site/")
```

`load_source` accepts a Markdown file, or a folder that holds `deck.md` (or
`slides.md`). The `deck.yml` beside the file and the frontmatter are read once
into the fields of the deck, the frontmatter winning key by key.

The `DeckSource` has three attributes: `deck`, the `Deck` it read; `directory`,
the folder that holds the Markdown and its figures; and `markdown`, the file
itself. Change the deck before you build it:

```python
from mkdeck import Slide, load_source

loaded = load_source("slides/deck.md")
loaded.deck.slides.append(Slide(sentence="One more result arrived."))
loaded.build("site/")
```

`DeckSource.serve()` reads the Markdown again on every change under the
folder, so an edit to `deck.md` or `deck.yml` reloads the page. That has a
consequence for the pattern above: the first build of a served `DeckSource` uses
`loaded.deck` as you changed it, but every rebuild reads the files from disk
again, so the first edit to the Markdown drops your changes. To serve a deck
you change in Python, serve the `Deck` itself, and watch the deck's folder:

```python
loaded = load_source("slides/deck.md")
loaded.deck.slides.append(Slide(sentence="One more result arrived."))
loaded.deck.serve(source=loaded.directory)  # figures reload; the Markdown is not read again
```

## Errors and warnings

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

A problem that leaves the deck usable, such as an embed that is not on disk,
is a `DeckWarning`. It goes through Python's `warnings` module, so you decide
what happens to it. The command line shows each one as `mkdeck: warning: ...`.

```python
import warnings

from mkdeck import DeckWarning

warnings.filterwarnings("ignore", category=DeckWarning)  # say nothing
warnings.filterwarnings("error", category=DeckWarning)  # or make a warning a failure

with warnings.catch_warnings(record=True) as caught:  # or collect them
    warnings.simplefilter("always", DeckWarning)
    deck.build("site/")
print([str(warning.message) for warning in caught])
```

## What is public

`mkdeck` exports `Deck`, `Slide`, `Embed`, `Table`, `DEFAULT_UNITS`,
`load_source`, `DeckSource`, `DeckError` and `DeckWarning`. `mkdeck.errors`
holds the two exception classes, and `mkdeck.rollout` holds the Brax
converter. Every other module is an implementation detail that can change
between releases.
