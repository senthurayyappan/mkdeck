# Custom JavaScript

Add your own script to a deck, and use the small `window.mkdeck` API.

List the script in `deck.yml`:

```yaml
extra_js: [theme/marks.js]
```

mkdeck loads each `extra_js` file after `mkdeck.js`.

## Write a classic script

mkdeck loads each file as a classic script, not as a module. A folder build links it with `<script src>`, and a `--single-file` build writes it inline into a `<script>`. So a top-level `import ... from "..."` is a syntax error.

Browsers refuse to load a module from a `file://` page, and a deck that someone opens with a double click uses `file://`. For that reason, mkdeck keeps to classic scripts.

## Load a module with a dynamic import

A classic script may call `import()`. The call works from a served deck and from a file if the browser can reach the module address. A full `https://` URL always works:

```js
import("https://esm.sh/rough-notation@0.5.1").then(({ annotate }) => {
  // use annotate here
});
```

A library that ships a plain script build defines a global and needs no `import`. List it in `extra_js` before your file.

## Use window.mkdeck

`window.mkdeck` is the only global that mkdeck adds:

| Member | What it does |
| --- | --- |
| `onSlide(fn)` | Calls `fn({index, total, slide, date})` on each slide change. It returns a function that unsubscribes |
| `reloadEmbeds()` | Rebuilds the iframes of the current slide. Use it when a viewer stalls |
| `deck` | The reveal.js instance |

`onSlide` also calls `fn` at once when the deck is already up. Reveal's own API stays available through `mkdeck.deck`, so your component can use fragments, key bindings, or the overview.

## Wait for fonts

A web font arrives after the page. As a result, code that measures text too early gets the wrong width, and a label comes out clipped. Wait for the fonts first:

```js
document.fonts.ready.then(() => {
  // measure text here
});
```

The same rule applies to a figure that a plotting library draws, because the library computes its own label boxes.

Next: [Custom elements](elements.md).
