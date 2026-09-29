# Build a folder

Write your deck to a folder that you can publish as it is.

```bash
mkdeck build talk --out site
```

The command prints `Wrote site/index.html`. Without `--out`, mkdeck writes to `site/`.

## What the folder holds

The `site/` folder holds `index.html`, the front-end files in `mkdeck-assets/`, and a copy of your `assets/` folder. It also holds the files that your figures and your `extra_css` and `extra_js` settings name. See [The deck folder](../start/deck-folder.md).

Because every path in the page is relative, you can publish the folder on any static host, or in any subfolder of one.

## Build again

To bring the folder up to date, build again into the same folder. First, mkdeck copies every file afresh. Then it removes each file that the previous build wrote and this build does not need. It knows those files from a `.mkdeck-build.json` list that it keeps in the folder.

mkdeck never touches files that you put in the folder yourself.

## Warnings and errors

mkdeck reports a problem that leaves the deck usable as a warning, such as an embed that is not on disk, and the build continues. However, a rule that the deck breaks is an error, which stops the build with a message that names the slide.

## Options

Use `--out` to choose the folder, or `--single-file` to write one HTML file, as [Build one file](single-file.md) shows. See [CLI: new, serve, build](../reference/cli.md#mkdeck-build) for every option.

## Limits

!!! warning
    The output folder cannot be the deck folder or its `assets/` folder. mkdeck stops with an error and asks you to write the build somewhere else.

Next: [Build one file](single-file.md).
