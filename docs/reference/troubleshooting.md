# Troubleshooting

Find the cause of a common problem, and fix it.

Every row names a symptom, its cause, and the fix.

## Slide problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| "frontmatter block that is never closed" | The first line of `deck.md` is `---`, so mkdeck expects settings | Delete that line, or close the block with a second `---` |
| A slide splits in the wrong place | A line of dashes cuts the slide, even under a paragraph | Move or remove the line. Write headings with `#` |
| A number is not marked | Its unit is not in the `units` list | Add the unit. See [Numbers and units](../write/numbers.md) |
| A script fails with "Cannot use import statement" | `extra_js` runs as a classic script | Use a dynamic `import()`. See [Custom JavaScript](../extend/js.md) |

## Build problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| Warning: "was not found in the deck folder" | A figure path does not match a file | Fix the path. It is relative to the deck folder |
| Warning: "not copied into the build" | A local image sits outside `assets/` | Move the image under `assets/` |
| "The output folder is the deck source folder" | `--out` points at the deck folder | Choose another folder with `--out` |

## Viewing problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| A diagram is blank | The browser cannot reach the CDN | Connect to a network, or save Mermaid under `assets/`. See [Diagrams](../write/diagrams.md) |
| A rollout is blank when you open a folder build from `file://` | A browser does not read a neighboring file from a `file://` page | Serve the folder, or build one file. See [Share and export rollouts](../robots/share-rollouts.md) |
| The page does not reload after you edit a Python script | The server does not run your script again | Restart the script. See [Serve from Python](../python/serve.md) |
| The server answers 403 | The address in the browser is not `localhost` or a loopback address | Open `http://127.0.0.1:5020/` or `http://localhost:5020/` |
| "could not listen on" | Another program uses the port | Choose another port with `--port` |

## Install problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| `uv add mkdeck` fails | The folder has no `pyproject.toml` | Create one, or use `uv tool install mkdeck` |
| `check` or `export` asks for Playwright | The `check` extra is not installed | See [Install the browser tools](../share/browser.md) |
| Chromium does not start on Linux | System libraries are missing | Run `playwright install-deps chromium` |

Next: [API reference](../api.md).
