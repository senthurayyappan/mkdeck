# Build a deck from Python

Generate slides from data that you already compute, so that nobody retypes a number.

```python
from mkdeck import Deck, Embed, Slide

runs = [
    ("run3", "Run 3", 5, 22),
    ("run4", "Run 4", 4, 20),
]  # name, label, crossings, cap

deck = Deck(title="Vault runs", date="2026-09-18")

for name, label, crossings, cap in runs:
    deck.slides.append(
        Slide(
            id=name,
            sentence=f"{crossings} of 5 seeds cross at {cap} N m.",
            embeds=[Embed(f"assets/{name}.html", label=label)],
        )
    )

deck.build("site/")
```

The loop adds one slide for each run, and then `deck.build("site/")` writes the deck to `site/`.

## Build the deck

`Deck.build` writes the deck to a folder and returns the path of the HTML file. It takes these arguments:

| Argument | What it does | Default |
| --- | --- | --- |
| `out` | Sets the output folder | `"site"` |
| `source` | Sets the folder that holds your figures. It takes a string or a `Path` | the current directory |
| `single_file` | Set it to `True` to write one HTML file that opens from `file://` | `False` |

## Find your figures

mkdeck resolves every embed relative to `source`, so `Embed("assets/run3.html")` points at `./assets/run3.html`. Run the script from the folder that holds `assets/`, or name another folder:

```python
deck.build("site/", source="slides/")
```

mkdeck copies the `assets/` tree into the build, together with every embed that the slides name.

## Build again

A second build into the same folder brings it up to date. First, mkdeck copies every file afresh. Then it removes each file that the previous build wrote and this build does not need. It finds those files in a `.mkdeck-build.json` list in the folder.

## Limits

!!! warning
    mkdeck refuses a path that leaves `source`. If you pass `source`, the output folder cannot be that folder or its `assets/` folder.

Next: [The slide model](slide-model.md).
