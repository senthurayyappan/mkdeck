# Getting started

## Install

To try mkdeck once, with nothing installed, run it through `uvx`:

```bash
uvx mkdeck new talk
uvx mkdeck serve talk
```

To use it regularly, install the command:

```bash
uv tool install mkdeck    # or: pip install mkdeck
```

Inside a project that has a `pyproject.toml`, add it as a dependency. This
fails in an empty folder, because `uv add` edits a `pyproject.toml` that has to
exist already:

```bash
uv add mkdeck
```

Keep mkdeck out of your runtime dependencies if the deck is not part of your
program:

```bash
uv add --group slides mkdeck
```

The examples below write `mkdeck ...`. If you did not install the command, put
`uvx` or `uv run` in front of it.

## Create a deck

```bash
mkdeck new talk
```

The command writes three things:

```
talk/deck.md      the slides
talk/deck.yml     the theme, the units and your own CSS or JS
talk/assets/      figures, HTML pages and images
```

## Serve it

```bash
mkdeck serve talk
```

The deck is served on <http://127.0.0.1:5020>; open that address in a browser.
mkdeck watches the folder and reloads the page when you save a change. Add
`--open` to open a browser tab for you, and `--port` to pick another port.

The server hands out the whole built deck, including a copy of your `assets/`
folder. It listens on `127.0.0.1`, so only your own machine can reach it.
`--host 0.0.0.0` makes it reachable from the network, and then anyone on that
network can read everything in the build.

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
mkdeck build talk --out site
```

`site/index.html` holds the deck. The folder also holds the front-end files and
a copy of your `assets/` folder, so you can publish the folder as it is.

Build again into the same folder and mkdeck brings it up to date. It copies
every file afresh and removes the files the previous build wrote that this one
no longer needs, which it knows from a `.mkdeck-build.json` file it keeps in the
folder. Files you put there yourself are never touched. A build into a single
HTML file (below) keeps no such list, because that file may sit in a folder
mkdeck does not own.

mkdeck reports a problem that leaves the deck usable, such as an embed that is
not on disk, as a warning on the command line. A rule the deck breaks is an
error, which stops the build with a message that names the slide.

To hand someone a single file, inline the stylesheets and the scripts:

```bash
mkdeck build talk --single-file --out talk.html
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

With pip, install `"mkdeck[check]"` and run `python -m playwright install
chromium` instead.

`check` opens every slide in headless Chromium. It reports the slides whose
content runs off the screen, a formula or a diagram that did not draw, and a
rollout that did not load, and writes `report/report.json` and one screenshot
per slide. `export` prints the deck to a PDF, one page per slide.

A PDF is a still picture of the deck. An embedded page prints as it looks once
it has loaded, without its interaction. A rollout prints as its first frame, a
picture of the robot at the start of the run. A diagram is drawn from the same
CDN as on screen, so `export` needs a network for it.

Both commands need the `check` extra and the Chromium download. The extra is
called `check` because that command asked for it first; `export` uses the same
Playwright install. If Chromium fails to start because the machine lacks system
libraries such as NSS or ALSA, install them (on Debian or Ubuntu,
`playwright install-deps chromium` does that), or point `LD_LIBRARY_PATH` at a
folder that holds them before you run the command. Playwright inherits your
environment.

## Next

- [Writing slides](writing-slides.md) for the Markdown format
- [Building from Python](python-api.md) to generate slides from your data
- [Extending a deck](extending.md) for your own colours and components
- [CONTRIBUTING.md](https://github.com/senthurayyappan/mkdeck/blob/main/CONTRIBUTING.md)
  to work on mkdeck itself
