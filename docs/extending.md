# Extending a deck

mkdeck ships one visual language and no branding. You add your own colours,
fonts and components from your deck folder. There is no build step and no Node.

There are three ways to do it: theme tokens, extra stylesheets, and custom
elements.

## Theme tokens

Each theme states its whole appearance as CSS variables. Redefine a variable,
and every rule that uses it changes:

```css
/* theme/mine.css */
:root {
  --mkd-ink: #15130d;      /* headings and numbers */
  --mkd-surface: #f6f4ee;  /* the page */
  --mkd-grey: #6f6a5d;     /* the sentence */
  --mkd-line: #d9d4c7;     /* figure borders and table rules */
  --mkd-accent: #b4532a;   /* links, and your own marks */
}
```

```yaml
# deck.yml
theme: minimal
extra_css: [theme/mine.css]
```

mkdeck links `extra_css` after the theme, so your file wins without
`!important`. The path stays inside the deck folder. An `http` or `https` URL
is left as a link. The full list of variables sits at the top of
`mkdeck/assets/themes/minimal.css`.

## Fonts

Add a font the same way. Save the file under `assets/`, then declare it:

```css
/* theme/mine.css */
@font-face {
  font-family: "My Hand";
  src: url("../assets/fonts/myhand.woff2") format("woff2");
  font-display: swap;
}

.mkd-title {
  font-family: "My Hand", var(--mkd-font);
}
```

The path is relative to the stylesheet, not to the deck. mkdeck copies the
whole `assets/` tree and each file you name in `extra_css` or `extra_js`, so
the deck stays offline.

A `--single-file` build folds the stylesheet into the document and inlines a
`url()` that stays inside the deck folder, so the font comes along. A path
that leaves the folder is left out.

## Custom elements

A custom element is how you add a component. It is a web standard, so it needs
no framework and no compiler. Write one `.js` file and name it in `deck.yml`:

```yaml
extra_css: [theme/marks.css]
extra_js:  [theme/marks.js]
```

Markdown passes HTML through, so you use the element in the slide text:

```markdown
Departure speed reaches <deck-mark type="circle">2.10 m/s</deck-mark> at 22 N m.
```

### Scripts run as classic scripts

mkdeck loads each `extra_js` file as a classic script, not as a module. A folder
build links it with `<script src>`, and a `--single-file` build writes it inline
into a `<script>`. A top-level `import ... from "..."` is then a syntax error
("Cannot use import statement outside a module"). Browsers refuse to load a
module from a `file://` page, which is how a deck that someone double-clicks
opens, so mkdeck keeps to classic scripts.

To use an ES module, load it with a dynamic `import()`, which a classic script
may call. It works from a served deck and from a file, as long as the module's
address can be reached: a full `https://` URL always can. A library that
ships a plain script build, one that defines a global, needs no `import` at all:
list it in `extra_js` before your file.

### Example: hand-drawn marks

This component circles a number on the slide. It uses
[rough-notation](https://roughnotation.com/), a 10 KB library that draws
sketched marks over any element. The example imports it from a CDN with a
dynamic `import()`, so the slide needs a network connection.

```js
// theme/marks.js
(async () => {
  const { annotate } = await import("https://esm.sh/rough-notation@0.5.1");

  class DeckMark extends HTMLElement {
    connectedCallback() {
      if (this.annotation) { return; }           // reveal moves the node, so guard it
      this.annotation = annotate(this, {
        type: this.getAttribute("type") || "circle",   // circle, underline, box, highlight
        color: this.getAttribute("color") || "var(--mkd-accent)",
        strokeWidth: 2,
        padding: 6,
        animationDuration: 700,
        multiline: this.hasAttribute("multiline"),
      });
      // Draw the mark when the slide arrives. Reset it when the slide leaves,
      // so a second visit draws it again.
      this.unsubscribe = window.mkdeck.onSlide(({ slide }) => {
        if (slide && slide.contains(this)) { this.annotation.show(); }
        else { this.annotation.hide(); }
      });
    }

    disconnectedCallback() {
      if (this.unsubscribe) { this.unsubscribe(); }
    }
  }

  customElements.define("deck-mark", DeckMark);
})();
```

The element is defined once the import has arrived. A `<deck-mark>` already on
the page is upgraded at that moment, so the order does not matter.

```css
/* theme/marks.css — the element is inline, and must not move the line. */
deck-mark { display: inline; position: relative; }
```

### Draw on your own cue

To draw the mark while you speak, use a reveal fragment. A fragment advances on
the next keypress:

```markdown
Departure speed reaches
<deck-mark class="fragment" type="circle">2.10 m/s</deck-mark> at 22 N m.
```

```js
this.addEventListener("visible", () => this.annotation.show());
this.addEventListener("hidden", () => this.annotation.hide());
```

Reveal fires `visible` and `hidden` on the fragment itself. The number stays on
the slide, and the circle appears when you press space.

## What mkdeck gives your component

`window.mkdeck` is the only global, and it is small:

| Member | Meaning |
| --- | --- |
| `onSlide(fn)` | Call `fn({index, total, slide, date})` on each slide change. Returns an unsubscribe function |
| `reloadEmbeds()` | Rebuild the iframes of the current slide. Use it when a viewer stalls |
| `deck` | The reveal.js instance |

`onSlide` also calls `fn` at once if the deck is already up. Reveal's own API
stays available through `mkdeck.deck`, so your component can use fragments, key
bindings or the overview.

## Fonts load late

A web font arrives after the page. Code that measures text before the font
arrives measures the wrong width, and a label comes out clipped. Wait for the
fonts first:

```js
await document.fonts.ready;
```

The same rule applies to a figure you generate with a plotting library, because
the library computes its own label boxes.

## Vendored libraries

mkdeck carries the libraries a deck needs, so nothing is fetched when you
present. Each one is a pinned release, downloaded from its npm package and
committed to the repository:

| Library | Version | Used for |
| --- | --- | --- |
| reveal.js | 6.0.2 | The slides, with the notes and zoom plugins |
| KaTeX | 0.18.7 | Math, drawn in the browser, with its fonts |
| Roboto | 5.3.0 (`@fontsource/roboto`) | The default font, three weights of the latin subset |
| three.js | r150 (0.150.1) | The rollout viewer, and only in a deck that has a rollout |

[Mermaid](writing-slides.md#math-and-diagrams) is the exception: a pinned
release (12.0.0, checked against its SRI hash) is loaded from a CDN when a slide
holds a diagram, unless the diagram's `data-src` names a local copy.

three.js stays on r150 on purpose. The rollout viewer works around the way
r150's `OrbitControls` reads the camera's `up` vector once, when the controls
are created, and moving to a newer three.js means re-reading that workaround
first. The licenses of everything above are in
[THIRD_PARTY_NOTICES.md](https://github.com/senthurayyappan/mkdeck/blob/main/THIRD_PARTY_NOTICES.md).
