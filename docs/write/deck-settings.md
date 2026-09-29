# Deck settings

Set the title, the theme, and more for the whole deck.

You write deck settings in the frontmatter of `deck.md`, in `deck.yml`, or in both:

```markdown
---
title: "Barkour vault: model mismatch and open problems"
date: "2026-09-16"
theme: dark
---
```

```yaml
# deck.yml
theme: minimal
units:
  - N m
  - mm
```

The frontmatter is the block between two `---` lines at the top of the file, and `deck.yml` sits beside the Markdown file.

## Combine the two files

The frontmatter wins over `deck.yml`, key by key, so you can keep shared settings in `deck.yml` and override them in one deck. For `reveal`, mkdeck merges the two maps, and the frontmatter wins for each option.

## The settings

| Key | What it does | Default |
| --- | --- | --- |
| `title` | Sets the deck title, the browser tab title, and the generated title slide | none |
| `date` | Sets the date on the title slide and in the corner of every slide | none |
| `theme` | Sets the look: `minimal` or `dark` | `minimal` |
| `units` | Sets the units that number marking recognizes. See [Numbers and units](numbers.md) | the default units |
| `extra_css` | Lists your stylesheets, linked after the theme | none |
| `extra_js` | Lists your scripts, loaded after `mkdeck.js` | none |
| `reveal` | Sets options that mkdeck merges into `Reveal.initialize` | none |
| `title_slide` | Set it to `false` to drop the generated title slide | `true` |

Without a `title`, mkdeck generates no title slide. See [Title slides](layouts.md#title-slides).

## Set the theme

A theme is a stylesheet. The `minimal` theme has a white page and dark text, and the `dark` theme has a dark page and light text.

Both themes keep the same boxes and sizes, so a slide that fits in one fits in the other. To change colors or fonts, see [Custom CSS](../extend/css.md).

## Limits

!!! warning
    An unknown key is an error that names the file and suggests the closest key. A theme name with no stylesheet is an error too, so mkdeck never builds an unstyled deck.

Next: [What a slide cannot hold](limits.md).
