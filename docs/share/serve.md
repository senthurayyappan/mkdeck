# Serve a deck

Preview your deck in a browser while you write it.

```bash
mkdeck serve talk
```

The command prints `Slide deck: http://127.0.0.1:5020/` and `Press Ctrl-C to stop.` Open the address in a browser.

## Live reload

mkdeck watches the deck folder. When you save a file, it rebuilds the deck, prints `mkdeck: rebuilt`, and then reloads the page.

Sometimes a rebuild fails. In that case, mkdeck keeps the last good deck and prints the error in the terminal. The page also shows a banner at the bottom with the same message. Fix the file and save again.

## Edit text on the page

You can fix a word, a title, or a table cell on the page itself, without going back to your editor. Double-click the text. A box opens with the Markdown of that text. Change it, and press Enter. mkdeck writes the change into `deck.md`, rebuilds the deck, and reloads the page on the same slide.

| Key | What it does |
| --- | --- |
| Enter | Save the change. A click elsewhere on the page also saves. |
| Shift+Enter | In a sentence, start a new paragraph. In a bullet, start a new bullet. |
| Esc | Close the box and keep the old text. |

You can edit these parts of a slide:

- The `#` heading. It stays on one line.
- A sentence. A blank line splits it into two paragraphs, so each one starts on a new line.
- A bullet. Each line becomes its own bullet. Delete all the text to delete the bullet.
- A table cell, in the header or the body. mkdeck escapes a `|` that you type.

Text that has no single place in the file cannot be edited on the page. That includes a title or bullets set in the slide options, a sentence in the same paragraph as a figure, and a bullet with two paragraphs. Edit those in `deck.md`.

mkdeck saves a change only if `deck.md` still holds the text that the page shows. If you changed that text in your editor in the meantime, the box shows an error, and nothing is overwritten. Most editors reload the file after a change on the page. If the file has unsaved changes in your editor, save or discard them before you edit on the page.

Only a deck made from Markdown can be edited this way. A deck that you serve from Python, a deck served with `--no-reload`, and a deck served to the network with `--host` cannot be edited.

## Options

Add `--open` to open a browser tab for you, `--port` to pick another port, or `--no-reload` to serve one fixed build. See [CLI: new, serve, build](../reference/cli.md#mkdeck-serve) for every option.

## Who can reach the server

The server hands out the whole built deck, including a copy of your `assets/` folder. By default it listens on `127.0.0.1`, so only your own machine can reach it.

It also answers only requests that name `localhost` or a loopback address. So a web page from another site cannot read your deck through your browser.

An edit made on the page must come from a page of this server and carry a key that the server makes each time it starts. So a web page from another site cannot write to your deck.

## Limits

!!! warning
    `--host 0.0.0.0` makes the server reachable from the network. Anyone on that network can then read everything in the build. mkdeck prints a warning, and the server then answers to any name.

Next: [Install the browser tools](browser.md).
