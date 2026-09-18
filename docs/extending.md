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
`!important`. The full list of variables sits at the top of
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

A `--single-file` build folds the stylesheet into the document. A relative
`url()` then resolves against the document instead. Keep the font stylesheet
out of `extra_css` if you build single-file decks, and load the font from the
network instead.

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

### Example: hand-drawn marks

This component circles a number on the slide. It uses
[rough-notation](https://roughnotation.com/), a 10 KB library that draws
sketched marks over any element.

```js
// theme/marks.js
import { annotate } from "https://esm.sh/rough-notation@0.5.1";

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
```

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
