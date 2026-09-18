# Extending a deck

mkdeck ships one visual language and no branding. Everything specific to you — your
colours, your typeface, your annotations — is added from your own deck folder, with no
build step and no Node.

There are three extension points, in increasing order of power: **theme tokens**, **extra
stylesheets**, and **custom elements**.

## Theme tokens

The built-in themes define their whole appearance as CSS custom properties. Redefining a
token in your own stylesheet changes every rule that uses it:

```css
/* theme/mine.css */
:root {
  --mkd-ink: #15130d;
  --mkd-surface: #f6f4ee;
  --mkd-grey: #6f6a5d;
  --mkd-line: #d9d4c7;
}
```

```yaml
# deck.yml
theme: minimal
extra_css: [theme/mine.css]
```

`extra_css` is linked after the theme, so your file wins without `!important`. The full
token list is in `mkdeck/assets/themes/minimal.css`, which is written to be read.

## Custom elements

A custom element is the way to add a component. It is a web standard, so it needs no
framework and no compiler — one `.js` file in your deck folder, named in `extra_js`:

```yaml
# deck.yml
extra_css: [theme/marks.css]
extra_js:  [theme/marks.js]
```

Elements you define are used directly in Markdown, because Markdown passes raw HTML
through:

```markdown
Departure speed reaches <deck-mark type="circle">2.10 m/s</deck-mark> at 22 N m.
```

### Worked example: hand-drawn annotations

This is the component most often wanted for a talk: circle or underline a number on the
slide, at the moment you say it out loud rather than when the slide appears. It is built on
[rough-notation](https://roughnotation.com/), a 10 KB library that draws sketched
annotations over any element.

```js
// theme/marks.js
import { annotate } from "https://esm.sh/rough-notation@0.5.1";

class DeckMark extends HTMLElement {
  connectedCallback() {
    if (this.annotation) { return; }           // reconnects when reveal moves the node
    this.annotation = annotate(this, {
      type: this.getAttribute("type") || "circle",   // circle, underline, box, highlight
      color: this.getAttribute("color") || "var(--mkd-accent)",
      strokeWidth: 2,
      padding: 6,
      animationDuration: 700,
      multiline: this.hasAttribute("multiline"),
    });
    // Draw when the slide arrives, and reset when it leaves, so a second visit replays it.
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
/* theme/marks.css — the element is inline, and must not disturb the line box. */
deck-mark { display: inline; position: relative; }
```

`window.mkdeck.onSlide(fn)` is the whole API you need: it calls `fn({index, total, slide,
date})` on every slide change, calls it immediately if the deck is already up, and returns a
function that unsubscribes.

### Drawing on your own cue, not on the slide change

To annotate while you are speaking rather than on arrival, drive it from a reveal fragment.
Anything with `class="fragment"` advances on the next keypress, and mkdeck leaves reveal's
fragment handling alone:

```markdown
Departure speed reaches
<deck-mark class="fragment" type="circle">2.10 m/s</deck-mark> at 22 N m.
```

```js
this.addEventListener("visible", () => this.annotation.show());
this.addEventListener("hidden", () => this.annotation.hide());
```

Reveal fires `visible` and `hidden` on the fragment element itself, so the number is on the
slide from the start and the circle appears when you press space.

## What mkdeck gives your component

`window.mkdeck` is the only global, and it is small on purpose:

| Member | Meaning |
| --- | --- |
| `onSlide(fn)` | Subscribe to slide changes; returns an unsubscribe function |
| `reloadEmbeds()` | Rebuild the current slide's iframes, the fix for a stalled viewer |
| `deck` | The `Reveal` instance, for anything mkdeck does not wrap |

Reveal's own API stays available through `mkdeck.deck`, so a component can use fragments,
`addKeyBinding`, the overview, or any event mkdeck does not surface.

## A note on fonts

Web fonts load asynchronously, and anything that measures text before the font arrives
will measure the wrong box. This is not hypothetical: it is why figure labels in a deck can
come out clipped. If your component measures or positions against text, wait first:

```js
await document.fonts.ready;
```

The same applies to any figure you generate with a plotting library that computes its own
label boxes.
