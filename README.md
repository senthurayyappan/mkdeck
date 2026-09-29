![mkdeck: Markdown in, slide deck out](https://raw.githubusercontent.com/senthurayyappan/mkdeck/main/docs/images/banner.jpg)

[![CI](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/senthurayyappan/mkdeck/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-MkDocs-blue)](https://senthurayyappan.com/mkdeck/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://github.com/senthurayyappan/mkdeck/blob/main/pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/senthurayyappan/mkdeck/blob/main/LICENSE)

mkdeck turns Markdown or Python into HTML slide decks. Each deck uses reveal.js, draws math with KaTeX, and plays Brax robot runs offline.

## Install

Try mkdeck once, with nothing installed:

```bash
uvx mkdeck new talk
uvx mkdeck serve talk
```

Install the command to use it every day. mkdeck needs Python 3.11 or newer:

```bash
uv tool install mkdeck    # or: pip install mkdeck
```

## Quickstart

```bash
mkdeck new talk                                   # create talk/deck.md, talk/deck.yml, talk/assets/
mkdeck serve talk --open                          # preview the deck, and reload when you save
mkdeck build talk --out site                      # write a folder that you can publish
mkdeck build talk --single-file --out talk.html   # write one HTML file
mkdeck export talk --out talk.pdf                 # print a PDF (needs the check extra)
```

## Example

A slide is a block of Markdown, and a `---` line starts the next slide. This deck has two slides:

```markdown
---
title: Vault runs
---

Five of five seeds cross the wall at 22 N m.

![Run 3](assets/run3.html)

---

The torque cap decides the outcome.

| Cap | Crossings |
| --- | --- |
| 18 N m | 2 |
| 22 N m | 5 |
```

mkdeck adds a title slide, frames the HTML page as a figure, and marks each number in a darker ink.

## What you can do

- [Write slides in Markdown](https://senthurayyappan.com/mkdeck/write/slide-basics/) with layouts, bullets, tables, and speaker notes.
- [Show live figures](https://senthurayyappan.com/mkdeck/write/figures/), such as a Plotly chart or any HTML page.
- [Convert Brax pages](https://senthurayyappan.com/mkdeck/robots/convert/) into rollouts that play offline.
- Draw [math](https://senthurayyappan.com/mkdeck/write/math/) with KaTeX and [diagrams](https://senthurayyappan.com/mkdeck/write/diagrams/) with Mermaid. Diagrams load Mermaid from a CDN.
- [Build a folder or one file](https://senthurayyappan.com/mkdeck/share/build/), then [check every slide](https://senthurayyappan.com/mkdeck/share/check/) and [export a PDF](https://senthurayyappan.com/mkdeck/share/export/). Both commands need the `check` extra.
- [Generate a deck from Python](https://senthurayyappan.com/mkdeck/python/build-a-deck/) when your slides report computed numbers.
- [Restyle a deck](https://senthurayyappan.com/mkdeck/extend/css/) with CSS variables, and add your own components.

Read the full [documentation](https://senthurayyappan.com/mkdeck/), or look up a command in the [CLI reference](https://senthurayyappan.com/mkdeck/reference/cli/).

## Contribute and license

Bug reports and pull requests are welcome, so read [CONTRIBUTING.md](https://github.com/senthurayyappan/mkdeck/blob/main/CONTRIBUTING.md) first.

mkdeck is MIT licensed. The package also carries reveal.js, KaTeX, three.js, and the KaTeX and Roboto fonts under their own licenses. See [THIRD_PARTY_NOTICES.md](https://github.com/senthurayyappan/mkdeck/blob/main/THIRD_PARTY_NOTICES.md).
