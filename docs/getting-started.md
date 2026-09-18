# Getting started

## Install

```bash
uv add mkdeck
```

Keep mkdeck out of your runtime dependencies if the deck is not part of your
program:

```bash
uv add --group slides mkdeck
```

## Create a deck

```bash
uv run mkdeck new talk
```

The command writes three things:

```
talk/deck.md      the slides
talk/deck.yml     the theme, the units and your own CSS or JS
talk/assets/      figures, HTML pages and images
```

## Serve it

```bash
uv run mkdeck serve talk
```

The deck opens on <http://127.0.0.1:5020>. mkdeck watches the folder and
reloads the page when you save a change. Use `--port` to pick another port, and
`--open` to open a browser.

## Write a slide

Each block between `---` separators is one slide. Write the message as one
sentence, then add a figure:

```markdown
---
<!--
id: departure
-->

Five of five seeds cross the wall at 22 N m.

![Run 3](assets/run3.html)
```

mkdeck marks the numbers `22 N m` and `3` in a darker ink, because a reader
looks for the numbers first. [Writing slides](writing-slides.md) describes the
full format.

## Build it

```bash
uv run mkdeck build talk --out site
```

`site/index.html` holds the deck. The folder also holds the front-end files and
a copy of your `assets/` folder, so you can publish the folder as it is.

To hand someone a single file, inline the stylesheets and the scripts:

```bash
uv run mkdeck build talk --single-file --out talk.html
```

The file opens from a `file://` URL. Keep it beside its `assets/` folder if the
slides embed pages or images.

## Check it before you present

```bash
uv add --group slides "mkdeck[check]"
uv run playwright install chromium
uv run mkdeck check talk --size 1920x1080
uv run mkdeck export talk --out talk.pdf
```

`check` opens every slide in headless Chromium. It reports the slides whose
content runs off the screen, and writes `report/report.json` and one screenshot
per slide. `export` prints the deck to a PDF, one page per slide.

Both commands need the `check` extra and the Chromium download. If Chromium
fails to start because the machine has no system NSS or ALSA libraries, set
`MKDECK_BROWSER_LIBS` to a folder that holds them. mkdeck prepends that folder
to `LD_LIBRARY_PATH` when it starts the browser.

## Next

- [Writing slides](writing-slides.md) for the Markdown format
- [Building from Python](python-api.md) to generate slides from your data
- [Extending a deck](extending.md) for your own colours and components
- [CONTRIBUTING.md](https://github.com/senthurayyappan/mkdeck/blob/main/CONTRIBUTING.md)
  to work on mkdeck itself
