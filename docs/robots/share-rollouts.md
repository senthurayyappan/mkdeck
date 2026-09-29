# Share and export rollouts

Send a deck of rollouts to another person, or print it to a PDF.

## Serve the folder, or build one file

A browser does not read a neighboring file from a `file://` page. So a folder build with rollouts works only from a server. To share the deck as a file, build a single file instead:

```bash
mkdeck build slides -o out/deck.html --single-file
```

The single file carries the rollouts and the viewer inside the document. As a result, it opens from a USB stick or an email attachment with nothing to fetch.

## Expect a larger file

A single file is larger than the folder build, because the binary files travel as text and grow by about a third.

## Export a PDF

`mkdeck export` prints a rollout as its first frame, which shows the robot at the start of the run. Therefore the PDF holds no motion.

```bash
mkdeck export slides -o slides.pdf
```

See [Export to PDF](../share/export.md) for the other figure types.

## Limits

!!! note
    A single-file build folds rollouts into the document, but it still needs `assets/` beside it for HTML pages and images.

Next: [Build a folder](../share/build.md).
