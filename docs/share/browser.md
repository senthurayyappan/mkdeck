# Install the browser tools

Install Playwright and Chromium so that you can run `mkdeck check` and `mkdeck export`.

Both commands drive headless Chromium through Playwright, and mkdeck does not install them by default. So you add the `check` extra and download Chromium yourself. The extra has that name because `mkdeck check` was the first command to need it, and `mkdeck export` uses the same install.

## Choose your install

In a project, add the extra to a dependency group. Then download the browser:

```bash
uv add --group slides "mkdeck[check]"
uv run playwright install chromium
```

With pip, install the extra, then download the browser:

```bash
pip install "mkdeck[check]"
python -m playwright install chromium
```

If you installed the command with `uv tool install mkdeck`, install it again with the extra:

```bash
uv tool install "mkdeck[check]"
uvx playwright install chromium
```

To try the commands once without installing, run `uvx --from "mkdeck[check]" mkdeck check talk`.

## Fix a Chromium start failure

Chromium fails to start when the machine lacks system libraries, such as NSS or ALSA. On Debian or Ubuntu, run `playwright install-deps chromium`. Alternatively, point `LD_LIBRARY_PATH` at a folder that holds the libraries. Playwright inherits your environment.

## Limits

!!! warning
    Run `check` and `export` only on decks that you trust. Raw HTML in a slide runs in the browser that these commands start. The commands stop the page from reading a local file outside the deck folder. However, the page can still reach the network.

Next: [Check your slides](check.md).
