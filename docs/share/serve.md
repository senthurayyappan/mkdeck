# Serve a deck

Preview your deck in a browser while you write it.

```bash
mkdeck serve talk
```

The command prints `Slide deck: http://127.0.0.1:5020/` and `Press Ctrl-C to stop.` Open the address in a browser.

## Live reload

mkdeck watches the deck folder. When you save a file, it rebuilds the deck, prints `mkdeck: rebuilt`, and then reloads the page.

Sometimes a rebuild fails. In that case, mkdeck keeps the last good deck and prints the error in the terminal. The page also shows a banner at the bottom with the same message. Fix the file and save again.

## Options

Add `--open` to open a browser tab for you, `--port` to pick another port, or `--no-reload` to serve one fixed build. See [CLI: new, serve, build](../reference/cli.md#mkdeck-serve) for every option.

## Who can reach the server

The server hands out the whole built deck, including a copy of your `assets/` folder. By default it listens on `127.0.0.1`, so only your own machine can reach it.

It also answers only requests that name `localhost` or a loopback address. So a web page from another site cannot read your deck through your browser.

## Limits

!!! warning
    `--host 0.0.0.0` makes the server reachable from the network. Anyone on that network can then read everything in the build. mkdeck prints a warning, and the server then answers to any name.

Next: [Install the browser tools](browser.md).
