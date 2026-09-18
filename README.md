# mkdeck

[![CI](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-MkDocs-blue)](docs/index.md)
[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)](.python-version)
[![uv](https://img.shields.io/badge/uv-managed-DE5FE9?logo=uv)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/badge/lint-Ruff-D7FF64?logo=ruff)](https://docs.astral.sh/ruff/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Minimal HTML slide decks from Markdown or Python, served like mkdocs.

Write the slides in Markdown. Serve them on a local port. Embed live web pages,
images, math and diagrams. You need Python only. mkdeck carries reveal.js,
KaTeX and Roboto inside the wheel, so there is no Node, no npm and no build step.

## Use it

```bash
uv add mkdeck
uv run mkdeck new talk     # write deck.md, deck.yml and assets/
uv run mkdeck serve talk   # open http://127.0.0.1:5020
```

| Command | Purpose |
| --- | --- |
| `mkdeck new FOLDER` | Create a deck folder |
| `mkdeck serve PATH` | Serve the deck and reload it when the source changes |
| `mkdeck build PATH` | Write the deck to a folder, or to one HTML file |
| `mkdeck check PATH` | Report the slides that overflow the screen |
| `mkdeck export PATH` | Print the deck to a PDF |

A slide is one block of Markdown between `---` separators:

```markdown
---
<!--
id: departure
-->

Five of five seeds cross the wall at 22 N m.

![Run 3](assets/run3.html)
```

You can also build the same deck from Python, which suits decks that report
measured results:

```python
from mkdeck import Deck, Slide, Embed

deck = Deck(title="Vault runs", date="2026-09-18")
deck.slides.append(Slide(sentence="Five seeds cross.", embeds=[Embed("assets/run3.html")]))
deck.build("site/")
```

## Learn more

Read the [documentation](docs/index.md). It covers the Markdown format, the
Python API, and how to add your own components to a deck.

## Develop mkdeck

| Command | Purpose |
| --- | --- |
| `make install` | Install the tools and the Git hooks |
| `make check` | Lint, format and type checks |
| `make test` | Run the tests with coverage |
| `make docs` | Serve this documentation |
| `make build` | Build a wheel and a source distribution |

See [CONTRIBUTING.md](CONTRIBUTING.md). Use [Conventional
Commits](https://www.conventionalcommits.org/), such as `feat: add export`.
Release Please reads them to prepare each release.
