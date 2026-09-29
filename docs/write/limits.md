# What a slide cannot hold

Know which content stops a build, so that you can fix a slide fast.

mkdeck stops with an error, and names the slide, when a slide holds content that it cannot draw. It never drops content silently.

## Errors

These cases are errors:

- Figures and a table on the same slide.
- More than two figures.
- Two tables, or two headings.
- A nested list.
- Anything but text inside a bullet, such as a code block or raw HTML.
- A block with no place on a slide, such as a quote.
- An option that sets a field to a different value than the body does.
- An option that names body content: `embeds`, `table`, or `html`.
- An unknown option, an unknown layout, or two slides with the same `id`.

In every case, move the extra content onto a new slide.

## Read an error message

An error names the deck file and the slide. For example:

```text
deck.md: slide 2 "a": This slide repeats the id of slide 1; give every slide its own id, or drop one of the two.
```

On the command line, mkdeck prints the message and exits with status 1. In Python, mkdeck raises a `DeckError`. See [Errors and warnings](../python/messages.md).

## What is not an error

A heading is not an error. When a slide holds a heading and a body, mkdeck draws the heading above the body:

```markdown
# Results

Five of five seeds cross the wall.
```

A problem that leaves the deck usable is only a warning. Two examples are an embed that is not on disk and a local image outside `assets/`.

## Limits

!!! note
    The rules about figures, tables, and ids apply to decks that you build in Python too.

Next: [Convert Brax pages](../robots/convert.md).
