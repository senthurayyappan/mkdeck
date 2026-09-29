# Custom CSS

Change the colors and fonts of a deck from your own stylesheet.

mkdeck ships one visual style and no branding. You add your own from the deck folder, so there is no build step and no Node.

## Redefine the theme tokens

Each theme states its whole look as CSS variables, so when you redefine a variable, every rule that uses it changes:

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

Then list the stylesheet in `deck.yml`:

```yaml
# deck.yml
theme: minimal
extra_css: [theme/mine.css]
```

mkdeck links `extra_css` after the theme, so your file wins without `!important`. The full list of variables sits at the top of `mkdeck-assets/themes/minimal.css` in any build folder.

## Add a font

First, save the font file under `assets/`. Then declare it in your stylesheet:

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

The `url()` path is relative to the stylesheet, not to the deck. mkdeck copies the whole `assets/` tree and each file that `extra_css` or `extra_js` names. So the deck stays offline.

## Limits

!!! note
    An `extra_css` path stays inside the deck folder. An `http` or `https` URL stays a link.

    A `--single-file` build folds the stylesheet into the document. It inlines each `url()` that stays inside the deck folder, so the font comes along. It leaves out a path that leaves the folder.

Next: [Custom JavaScript](js.md).
