# The slide model

Learn the four classes that describe a deck, so that you can build any slide in Python.

Markdown and Python meet in these classes: the Markdown loader produces them, and the renderer reads them. Because there is one code path, the two ways to write a deck cannot drift apart.

| Class | What it holds |
| --- | --- |
| `Deck` | The title, the date, the theme, the units, and the slides |
| `Slide` | One slide: a sentence, bullets, math, figures, a table, or raw HTML |
| `Embed` | One figure: a source, a caption, and a kind |
| `Table` | The columns and the rows of a table |

The [API reference](../api.md) lists every field and signature.

## Build a slide with a table

This slide holds a sentence, a table, and speaker notes:

```python
from mkdeck import Slide, Table

Slide(
    id="torque-cap",
    sentence="The higher cap raises the crossing rate.",
    table=Table(
        columns=["Cap", "Crossings"], rows=[["18 N m", "2"], ["22 N m", "5"]]
    ),
    notes="The 18 N m runs stall against the wall.",
)
```

`Slide` has the same fields as the [slide options](../write/slide-options.md), plus `embeds`, `table`, and `html`.

## Set the deck settings

`Deck` carries every setting of `deck.yml` and the frontmatter as a field. The fields are `title`, `date`, `theme`, `units`, `extra_css`, `extra_js`, `reveal`, and `title_slide`. See [Deck settings](../write/deck-settings.md).

`units` replaces `DEFAULT_UNITS`. To add a unit, extend the default list:

```python
from mkdeck import DEFAULT_UNITS, Deck

deck = Deck(title="Vault runs", units=[*DEFAULT_UNITS, "GPa"])
```

## Format text

Text in a slide takes inline Markdown and passes raw HTML through unchanged. So when the text comes from data that you do not control, such as a run name or a log line, escape it first:

```python
from html import escape

from mkdeck import Slide

Slide(sentence=escape(log_line))
```

## Limits

!!! note
    A `Slide` with only a `title` is a statement slide. Set `layout="title"` to make a title slide.

Next: [Load a deck](load-a-deck.md).
