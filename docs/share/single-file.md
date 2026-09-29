# Build one file

Hand someone a single HTML file that opens with a double click.

```bash
mkdeck build talk --single-file --out talk.html
```

The command inlines the stylesheets and the scripts into `talk.html`. When the deck has rollouts, it folds them in too. As a result, the file opens from a `file://` URL.

## Choose the output name

With `--single-file`, an `--out` path that ends in `.html` is the file itself. Any other name is a folder that holds `index.html`:

```bash
mkdeck build talk --single-file --out share
```

## Keep the assets beside the file

The command also writes your `assets/` folder next to the HTML file, so keep the two together when the slides show HTML pages or images. Fonts are the exception, because a font that your CSS loads with `url()` travels inside the file when the font sits in the deck folder.

## Build again

A build into a `.html` file keeps no `.mkdeck-build.json` list. Because the file may sit in a folder that mkdeck does not own, mkdeck removes nothing there.

## Limits

!!! note
    A single-file build leaves out the license files of the bundled libraries. Keep them with the deck if you redistribute it. See [THIRD_PARTY_NOTICES.md](https://github.com/senthurayyappan/mkdeck/blob/main/THIRD_PARTY_NOTICES.md).

Next: [Serve a deck](serve.md).
