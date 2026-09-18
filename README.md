# mkdeck

[![CI](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-MkDocs-blue)](docs/index.md)
[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)](.python-version)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Minimal HTML slide decks from Markdown or Python, served like mkdocs.

Write your slides in a Markdown file, run one command, and the deck opens in
your browser. Save the file and the page reloads. reveal.js, KaTeX and the
fonts all travel inside the package, so there is no Node toolchain to set up
and nothing to fetch from a CDN while you present.

```bash
uv add mkdeck
uv run mkdeck new talk     # writes deck.md, deck.yml and assets/
uv run mkdeck serve talk   # http://127.0.0.1:5020
```

## What a slide looks like

Slides are separated by `---`. Say one thing per slide, then show the evidence:

```markdown
---
<!--
id: departure
-->

Five of five seeds cross the wall at 22 N m.

![Run 3](assets/run3.html)
```

Point a slide at an HTML file and mkdeck frames it. That is how a Brax viewer,
a Plotly chart or any other interactive page ends up running inside a slide,
next to the sentence that explains it. Point it at a PNG or a GIF instead and
you get a picture. Numbers such as `22 N m` come out in a darker ink, because
that is what people look for first.

Math is KaTeX, rendered when the deck is built. Diagrams are Mermaid. Tables
are ordinary Markdown pipes.

## Or build it from Python

Handy when the slides report numbers you already compute, since nobody has to
retype a value that changed:

```python
from mkdeck import Deck, Embed, Slide

deck = Deck(title="Vault runs", date="2026-09-18")
for run in runs:
    deck.slides.append(
        Slide(
            sentence=f"{run.crossings} of 5 seeds cross at {run.cap} N m.",
            embeds=[Embed(f"assets/{run.name}.html", label=run.label)],
        )
    )
deck.build("site/")
```

Markdown and Python produce the same slide objects and render through the same
code, so the two ways of writing a deck stay in step.

## Commands

| Command | What it does |
| --- | --- |
| `mkdeck new FOLDER` | Start a deck |
| `mkdeck serve PATH` | Serve it, and reload when you save |
| `mkdeck build PATH` | Write it to a folder, or to one HTML file |
| `mkdeck check PATH` | Tell you which slides overflow the screen |
| `mkdeck export PATH` | Print it to a PDF |

## Documentation

The [docs](docs/index.md) cover the Markdown format, the Python API, and how
to bring your own colours, fonts and components to a deck. Run `make docs` to
read them in a browser.

## Contributing

Bug reports and pull requests are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the local checks and the release flow.
