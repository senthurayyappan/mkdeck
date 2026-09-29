# Check your slides

Find the slides that overflow the screen before you present.

```bash
mkdeck check talk --size 1920x1080
```

The command opens every slide in headless Chromium, measures it, and prints one line per slide. Before you run it, install the [browser tools](browser.md).

## What check reports

The report flags these problems:

| Flag | Meaning |
| --- | --- |
| `OVERFLOW` | The content runs off the top or bottom of the screen |
| `INTO-CHROME` | The content reaches the bottom strip that shows the date and the slide number |
| `SCROLLBAR` | An element would show a scrollbar |
| `OVERLAP` | Two blocks of the slide cover each other |
| `KATEX-ERROR`, `MATH-UNRENDERED` | A formula did not draw |
| `MERMAID-ERROR` | A diagram did not draw |
| `ROLLOUT-ERROR` | A rollout did not load |

A clean slide shows `ok`.

## Read the report files

The command writes three kinds of file into `report/`:

- `report.txt` holds the lines that the command prints.
- `report.json` holds the same findings for a program to read.
- `slide_01.png`, `slide_02.png`, and so on hold one screenshot per slide.

A new run replaces the screenshots of the run before it.

## Use check in CI

`check` exits with status 0 once it writes the report, even when it flags a slide. To fail a CI job, add `--strict`. Then the command exits with status 1 when it flags any slide:

```bash
mkdeck check talk --strict
```

## Options

Use `--size` to check at another screen size, `--out` to choose the report folder, or `--no-shots` to skip the screenshots. See [CLI: rollout, check, export](../reference/cli-tools.md#mkdeck-check) for every option.

## Limits

!!! warning
    Run `check` only on decks that you trust. See [Install the browser tools](browser.md#limits).

    To keep the check fast, mkdeck replaces an HTML page larger than 2 MB with a stub.

Next: [Export to PDF](export.md).
