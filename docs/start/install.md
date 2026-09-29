# Install mkdeck

Install mkdeck with `uv` or `pip`, or run it once with `uvx`. mkdeck needs Python 3.11 or newer.

## Try it once

First, run mkdeck through `uvx`, which installs nothing on your machine:

```bash
uvx mkdeck new talk
uvx mkdeck serve talk
```

## Install the command

Next, install the command if you plan to use mkdeck often:

```bash
uv tool install mkdeck    # or: pip install mkdeck
```

## Add mkdeck to a project

Instead, add mkdeck as a dependency when your project has a `pyproject.toml`:

```bash
uv add mkdeck
```

If the deck is not part of your program, keep mkdeck out of your runtime dependencies:

```bash
uv add --group slides mkdeck
```

## Run the commands

The docs write `mkdeck ...` for every command. If you did not install the command, put `uvx` or `uv run` in front of it.

## Add the browser tools

Two commands need more than mkdeck itself. `mkdeck check` and `mkdeck export` need Playwright and Chromium, which you install separately. Follow [Install the browser tools](../share/browser.md) when you need them.

## Limits

!!! note
    `uv add` edits a `pyproject.toml`, so it fails in a folder that has none. Create one first, or use `uv tool install` instead.

Next: [Your first deck](first-deck.md).
