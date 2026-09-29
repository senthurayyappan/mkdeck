# CLI: rollout, check, export

Look up every option of the commands that convert, check, and print a deck.

`check` and `export` need the [browser tools](../share/browser.md).

## mkdeck rollout

Converts Brax playback pages into rollouts that play offline. See [Convert Brax pages](../robots/convert.md).

```bash
mkdeck rollout PAGES... [OPTIONS]
```

| Option | What it does | Default |
| --- | --- | --- |
| `PAGES` | Sets the Brax pages to convert | required |
| `--out`, `-o` | Sets the folder for the rollouts | `assets` |

## mkdeck check

Opens every slide in headless Chromium and reports what overflows. See [Check your slides](../share/check.md).

```bash
mkdeck check PATH [OPTIONS]
```

| Option | What it does | Default |
| --- | --- | --- |
| `PATH` | Sets the deck: a `.md` file, a folder that holds `deck.md`, or a built `.html` file | required |
| `--size` | Sets the viewport, as `WIDTHxHEIGHT` | `1920x1080` |
| `--out` | Sets the folder for the report and the screenshots | `report` |
| `--shots`, `--no-shots` | Writes one PNG per slide | `--shots` |
| `--strict` | Exits with status 1 when it flags any slide | off |

Without `--strict`, `check` exits with status 0 once it writes the report, whatever it finds.

## mkdeck export

Prints a deck to a PDF with one page per slide. See [Export to PDF](../share/export.md).

```bash
mkdeck export PATH [OPTIONS]
```

| Option | What it does | Default |
| --- | --- | --- |
| `PATH` | Sets the deck: a `.md` file, a folder that holds `deck.md`, or a built `.html` file | required |
| `--out`, `-o` | Sets the PDF to write | `deck.pdf` |
| `--size` | Sets the page size, as `WIDTHxHEIGHT` | `1920x1080` |

## Limits

!!! note
    The PDF is still. An HTML page prints as it looks once it has loaded. A rollout prints as its first frame. A diagram needs a network to draw.

Next: [Troubleshooting](troubleshooting.md).
