# The deck folder

Learn which files mkdeck reads, which files it copies into a build, and which files it writes.

```
talk/
  deck.md          the slides
  deck.yml         the deck settings
  assets/          figures, HTML pages, images, fonts
  theme/mine.css   your own stylesheet (optional)
  theme/marks.js   your own script (optional)
```

## Files mkdeck reads

mkdeck reads two files from the deck folder:

| File | What it holds |
| --- | --- |
| `deck.md` or `slides.md` | The slides. mkdeck looks for `deck.md` first |
| `deck.yml` or `deck.yaml` | The deck settings. The frontmatter of `deck.md` wins |

You can pass either a folder or a `.md` file to a command. With a file, the deck folder is the folder that holds it.

## Files mkdeck copies

A folder build copies four kinds of file into the output folder:

1. The whole `assets/` folder, except hidden files and hidden folders.
2. Each file that a figure names, wherever it sits under the deck folder.
3. Each file that `extra_css` or `extra_js` names.
4. The front-end files, such as reveal.js, KaTeX, and the theme. They go into `mkdeck-assets/`.

mkdeck copies nothing else. For example, a `data.js` beside `figs/g.html` stays behind, because only that page refers to it. The same holds for a file that raw HTML names. To copy such a file, put it under `assets/`. An `http` or `https` URL needs no copy.

## Files mkdeck writes

Each command writes to a default place:

| Command | Default output |
| --- | --- |
| `mkdeck build` | `site/` |
| `mkdeck check` | `report/` |
| `mkdeck export` | `deck.pdf` |

`mkdeck serve` ignores changes to these three names inside the deck folder, so a build or a check does not trigger a reload.

## Limits

!!! warning
    mkdeck refuses a figure path that leaves the deck folder, whether through `..` or through a link, and it refuses an absolute path. Inside `assets/`, it skips a link that points outside the folder and prints a warning.

Next: [Slide basics](../write/slide-basics.md).
