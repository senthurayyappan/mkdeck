# Custom elements

Add a component to your slides with a custom element.

A custom element is a web standard, so it needs no framework and no compiler. You write one `.js` file and one small stylesheet, and then you list them in `deck.yml`:

```yaml
extra_css: [theme/marks.css]
extra_js:  [theme/marks.js]
```

Markdown passes HTML through, so you use the element in the text of a slide:

```markdown
Departure speed reaches <deck-mark type="circle">2.10 m/s</deck-mark> at 22 N m.
```

## Example: hand-drawn marks

This component circles a number on the slide. It uses [rough-notation](https://roughnotation.com/), a 10 KB library that draws sketched marks over any element. The script imports it from a CDN, so the slide needs a network connection.

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

The script defines the element once the import arrives. A `<deck-mark>` already on the page upgrades at that moment, so the order does not matter.

The element is inline, so it must not move the line. Add this rule to `theme/marks.css`:

```css
deck-mark { display: inline; position: relative; }
```

## Draw on your own cue

To draw the mark while you speak, use a reveal.js fragment. A fragment advances on the next key press:

```markdown
Departure speed reaches
<deck-mark class="fragment" type="circle">2.10 m/s</deck-mark> at 22 N m.
```

Then replace the `onSlide` call in `connectedCallback` with these lines. They listen for the two events that reveal.js fires on the fragment:

```js
this.addEventListener("visible", () => this.annotation.show());
this.addEventListener("hidden", () => this.annotation.hide());
```

The number stays on the slide. The circle appears when you press space.

Next: [Vendored libraries](libraries.md).
