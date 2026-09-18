# mkdeck

Minimal HTML slide decks from Markdown or Python, served like mkdocs.

A deck is one Markdown file, one small config file, and a folder of figures.
mkdeck turns them into a single HTML page and serves it on a local port.

## What you get

- **Python only.** mkdeck carries reveal.js, KaTeX and the Roboto font inside
  the wheel. You do not install Node, and a built deck needs no network.
- **Live figures.** Point a slide at an HTML page to embed it. A Brax viewer, a
  Plotly chart or a WebGL scene runs inside the slide.
- **One deck, two ways to write it.** Author in Markdown, or build the slides
  from Python when the deck reports measured results. Both paths use the same
  slide model, so they cannot drift apart.
- **Math and diagrams.** KaTeX renders `$...$` and `$$...$$`. A `mermaid` code
  fence becomes a diagram.
- **One visual language.** White page, one grey sentence, dark numbers. You
  change the colours with CSS variables, and you add components with custom
  elements.

## Start here

| Page | Content |
| --- | --- |
| [Getting started](getting-started.md) | Install mkdeck and serve your first deck |
| [Writing slides](writing-slides.md) | The Markdown format and the deck settings |
| [Building from Python](python-api.md) | Generate a deck from your own data |
| [Extending a deck](extending.md) | Add your colours, fonts and components |
| [API reference](api.md) | Every public class and function |
