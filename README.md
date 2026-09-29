# mkdeck

[![CI](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-MkDocs-blue)](https://senthurayyappan.github.io/mkdeck/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://github.com/senthurayyappan/mkdeck/blob/main/pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/senthurayyappan/mkdeck/blob/main/LICENSE)

Minimal HTML slide decks from Markdown or Python, served like mkdocs.

Write your slides in a Markdown file and run one command. mkdeck serves the
deck on a local port, and the page reloads when you save the file. reveal.js,
KaTeX and the fonts all travel inside the package, so there is no Node
toolchain to set up. Mermaid is the one exception: a slide that holds a diagram
loads a pinned release of it from a CDN, so that slide needs a network
connection (or a local copy of Mermaid that you point the diagram at).

## Install

To try it once, with nothing installed:

```bash
uvx mkdeck new talk
uvx mkdeck serve talk
```

To use it regularly, install the command:

```bash
uv tool install mkdeck    # or: pip install mkdeck
```

Inside a project that has a `pyproject.toml`, add it as a dependency with
`uv add mkdeck` (`uv add --group slides mkdeck` keeps it out of your runtime
dependencies).

## Quickstart

```bash
mkdeck new talk     # writes talk/deck.md, talk/deck.yml and talk/assets/
mkdeck serve talk   # serves http://127.0.0.1:5020 and reloads when you save
```

Add `--open` to `mkdeck serve` to open the deck in your browser, and `--port`
to pick another port. Without a global install, put `uvx mkdeck` or
`uv run mkdeck` in front of the same commands.

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

Math is KaTeX. mkdeck leaves a placeholder for each formula, and the KaTeX that
ships in the package draws it in the browser, so math works offline. Diagrams
are Mermaid fences, and they load Mermaid from a CDN (see above). Tables are
ordinary Markdown pipes.

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

An embed such as `assets/run3.html` is resolved relative to the deck's
`source` folder, which is the current directory unless you pass `source=`. Run
the script from the folder that holds `assets/`, or pass
`deck.build("site/", source="slides/")`. mkdeck copies the files into `site/`.

Markdown and Python produce the same slide objects and render through the same
code, so the two ways of writing a deck stay in step. `load_source` reads a
Markdown deck into an object with the same two methods, `build` and `serve`:

```python
from mkdeck import load_source

load_source("talk").build("site/")
```

`mkdeck`, `mkdeck.errors` and `mkdeck.rollout` are the public API; every other
module is an implementation detail.

## Commands

| Command | What it does |
| --- | --- |
| `mkdeck new FOLDER` | Start a deck |
| `mkdeck serve PATH` | Serve it, and reload when you save |
| `mkdeck build PATH` | Write it to a folder, or to one HTML file |
| `mkdeck rollout PAGES` | Turn Brax playback pages into rollouts that play offline |
| `mkdeck check PATH` | Tell you which slides overflow the screen |
| `mkdeck export PATH` | Print it to a PDF (rollouts print as a still frame) |

`check` and `export` drive headless Chromium through Playwright. Install the
`check` extra (`pip install "mkdeck[check]"`) and run `python -m playwright
install chromium` first. The extra has that name because `mkdeck check` was the
first command to need it; `mkdeck export` uses it too.

## Documentation

The [docs](https://senthurayyappan.github.io/mkdeck/) cover the Markdown format,
the Python API, and how to bring your own colours, fonts and components to a
deck. To read them from a checkout, run `make docs`.

## Contributing

Bug reports and pull requests are welcome. See
[CONTRIBUTING.md](https://github.com/senthurayyappan/mkdeck/blob/main/CONTRIBUTING.md)
for the local checks and the release flow.

## License

mkdeck is MIT licensed. The package also carries reveal.js, KaTeX, three.js and
the KaTeX and Roboto fonts under their own licenses; see
[THIRD_PARTY_NOTICES.md](https://github.com/senthurayyappan/mkdeck/blob/main/THIRD_PARTY_NOTICES.md).
