# Slide options

Set an id, a layout, and more with an HTML comment at the top of a slide.

```markdown
<!--
id: departure
layout: statement
classes: [dense]
-->

Five of five seeds cross the wall at 22 N m.
```

This is the first slide of a file. On a later slide, the comment follows the `---` separator. The options comment is the first comment of the slide, and it holds `key: value` lines in YAML.

## When mkdeck reads a comment as options

mkdeck reads the first comment of a slide as options when one of its `key:` lines names an option. It also does so when a line nearly matches an option, such as `layot:` for `layout:`, so that a typo produces an error.

Any other comment is a plain comment. It stays invisible and mkdeck never checks it, so `<!-- TODO: fix this -->` is safe.

A comment that reads as options must be valid YAML and hold only the options below. Otherwise, mkdeck stops with an error that names the slide.

## The options

| Option | What it does | Default |
| --- | --- | --- |
| `id` | Gives the slide a stable name, which mkdeck writes to `data-id` | none |
| `layout` | Sets the layout: `auto`, `title`, `statement`, `figures`, or `table` | `auto` |
| `title` | Sets the heading, which a title slide draws | none |
| `sentence` | Sets the message, if you prefer to write it here | none |
| `bullets` | Sets the bullets, as a list of strings | none |
| `math` | Sets the display formulas, as a list | none |
| `notes` | Sets the speaker notes | none |
| `date` | Sets the date on a title slide, and restamps every later slide | none |
| `classes` | Adds CSS classes to the slide | none |

The `dense` class uses tighter sizes. mkdeck adds it to a crowded slide, meaning one with bullets, a heading, or two formulas. It never removes a `dense` that you set.

## Set each field once

Write each field in one place. If you set a field in the options and in the body, the two values must match, or mkdeck reports an error.

Write figures, tables, and raw HTML in the body, because the options `embeds`, `table`, and `html` are errors.

## Combine notes and options

A comment that starts with `notes:` is always speaker notes, so it cannot hold other options. To set `notes` next to other options, list it last and quote the text if YAML needs it:

```markdown
<!--
id: departure
notes: "Say this out loud: the cap matters."
-->
```

## Limits

!!! warning
    An unknown option, an unknown layout, or a repeated `id` is an error. See [What a slide cannot hold](limits.md).

Next: [Deck settings](deck-settings.md).
