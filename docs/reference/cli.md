# CLI: new, serve, build

Look up every option of the commands that create, preview, and build a deck.

Run `mkdeck --help` for the command list, or `mkdeck COMMAND --help` for one command. The commands `rollout`, `check`, and `export` are on the page [CLI: rollout, check, export](cli-tools.md).

## mkdeck

| Option | What it does |
| --- | --- |
| `--version` | Prints the version and exits |
| `--install-completion` | Installs shell completion for your shell |
| `--show-completion` | Prints the completion script, so you can copy it |
| `--help` | Prints the help and exits |

## Exit status

Every command exits with status 0 on success. When a deck or a file causes an error, the command prints `mkdeck: MESSAGE` to the error stream and exits with status 1.

## mkdeck new

Creates a deck folder with `deck.md`, `deck.yml`, and `assets/`. See [Your first deck](../start/first-deck.md).

```bash
mkdeck new NAME
```

| Argument | What it does |
| --- | --- |
| `NAME` | Sets the folder to create. It must not exist, or it must be empty |

## mkdeck serve

Serves a deck and rebuilds it when its source changes. See [Serve a deck](../share/serve.md).

```bash
mkdeck serve PATH [OPTIONS]
```

| Option | What it does | Default |
| --- | --- | --- |
| `PATH` | Sets the deck: a `.md` file, or a folder that holds `deck.md` | required |
| `--port` | Sets the port, from 0 to 65535. Port 0 picks a free port | `5020` |
| `--host` | Sets the interface to bind | `127.0.0.1` |
| `--open`, `--no-open` | Opens the deck in a browser | `--no-open` |
| `--reload`, `--no-reload` | Watches the source and rebuilds when it changes | `--reload` |

## mkdeck build

Writes a deck to a folder, or to one HTML file. See [Build a folder](../share/build.md) and [Build one file](../share/single-file.md).

```bash
mkdeck build PATH [OPTIONS]
```

| Option | What it does | Default |
| --- | --- | --- |
| `PATH` | Sets the deck: a `.md` file, or a folder that holds `deck.md` | required |
| `--out`, `-o` | Sets the folder to write. With `--single-file`, a path that ends in `.html` is the file itself | `site` |
| `--single-file` | Inlines the CSS and JS, so the deck opens from `file://` | off |

Next: [CLI: rollout, check, export](cli-tools.md).
