# Export to PDF

Print your deck to a PDF with one page per slide.

```bash
mkdeck export talk --out talk.pdf
```

The command builds the deck, opens it in headless Chromium, and prints it, and then it reports `Wrote talk.pdf`. Before you run it, install the [browser tools](browser.md).

## What the PDF holds

A PDF is a still picture of the deck, so each kind of figure prints in its own way:

| Figure | How it prints |
| --- | --- |
| An HTML page | As it looks once it has loaded, without its interaction |
| A rollout | As its first frame, which shows the robot at the start of the run |
| A diagram | Drawn from the same CDN as on screen |

## Options

Use `--out` to name the PDF and `--size` to set the page size. See [CLI: rollout, check, export](../reference/cli-tools.md#mkdeck-export) for every option.

## Limits

!!! warning
    A diagram needs a network connection when you export.

    Run `export` only on decks that you trust. See [Install the browser tools](browser.md#limits).

Next: [Build a deck from Python](../python/build-a-deck.md).
