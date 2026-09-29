# HTML pages in slides

Run a Plotly chart, a Brax viewer, or any HTML page inside a slide, and keep the deck fast.

```markdown
Departure speed peaks at 22 N m.

![Plot, seed 2](assets/plot.html?seed=2)
```

mkdeck keeps the query, `?seed=2`, in the page address, but it leaves the query off the file name. So it copies the file `assets/plot.html`.

## How pages load

mkdeck limits how many pages run at once by applying three rules:

1. The current slide loads its page at once.
2. The two neighboring slides load their pages lazily, which means the browser decides when.
3. mkdeck removes the iframes of every other slide.

Removing an iframe frees its WebGL context. As a result, a deck with dozens of slides and many megabytes of WebGL pages still answers a key press at once.

## Reload a stalled page

Press `R` during a talk to reload the figures on the current slide, for example when a viewer stalls. Your own script can call `window.mkdeck.reloadEmbeds()` to do the same. See [Custom JavaScript](../extend/js.md).

## Keep pages small

mkdeck warns you at build time when a page is larger than 2 MB, and it gives the warning once for each file. A deck full of large pages opens slowly.

## Limits

!!! note
    A folder build copies the pages that you name. However, it copies a file that a page loads only if that file sits under `assets/`. See [The deck folder](../start/deck-folder.md).

Next: [Tables](tables.md).
