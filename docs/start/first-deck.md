# Your first deck

Create, serve, edit, and build a deck in a few commands.

## Create the deck

First, run `mkdeck new` with the name of a new folder:

```bash
mkdeck new talk
```

The command writes a deck folder with three items, but it stops with an error if the folder already holds files.

```
talk/deck.md      the slides
talk/deck.yml     the deck settings
talk/assets/      figures, HTML pages, and images
```

## Serve the deck

Next, run `mkdeck serve` to see the deck in a browser:

```bash
mkdeck serve talk
```

The command prints `Slide deck: http://127.0.0.1:5020/`, so open that address in a browser. From now on, mkdeck rebuilds the deck and reloads the page each time you save a file in the folder.

Add `--open` to open the browser for you, or add `--port` to pick another port. Press Ctrl-C to stop the server.

## Edit a slide

Then edit the deck. Save any HTML page as `talk/assets/run3.html`, and replace the text of `talk/deck.md` with this deck:

```markdown
---
title: "Vault runs"
date: "2026-09-18"
---

<!--
id: departure
-->

Five of five seeds cross the wall at 22 N m.

![Run 3](assets/run3.html)
```

The block between the first two `---` lines is the frontmatter, which holds deck settings. Because the deck sets a title, mkdeck adds an opening title slide. The comment gives the next slide an id, and the paragraph is the sentence, which is the message of the slide. The last line is a figure, which is an image, an HTML page, or a robot run on a slide. Here mkdeck frames your HTML page.

mkdeck also marks the number `22 N m` in a darker ink, because readers look for numbers first.

## Build the deck

Finally, run `mkdeck build` to write the deck to files:

```bash
mkdeck build talk --out site
```

`site/index.html` holds the deck, and you can publish the whole `site/` folder as it is. See [Build a folder](../share/build.md) for more.

Next: [The deck folder](deck-folder.md).
