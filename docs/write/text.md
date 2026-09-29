# Text and bullets

Write the sentence, the bullets, and the formatting of a slide.

```markdown
Five of five seeds cross the wall.

- Run 3 starts at **0.50 m**
- Run 4 starts at *0.60 m*
```

The first paragraph is the sentence, and the list below it holds two bullets.

## Write the sentence

A paragraph is the sentence of the slide, which is its one-line message. If you write two paragraphs, the slide gets two sentences.

## Add bullets

A `-` list makes bullets. A numbered list also makes bullets, but mkdeck drops the numbers. A definition list makes bullets in the form `term: definition`:

```markdown
Cap
: The torque limit in N m
```

Each bullet holds text only, so a nested list is an error.

## Format text

A sentence, a bullet, a figure label, and a table cell take inline Markdown, so you can write bold text, italic text, `code`, and links. Math and number marking work in the same places.

## Add a heading

A `#` heading appears above the rest of the slide, and a heading alone makes a [title slide](layouts.md#title-slides). A slide holds one heading.

## Add raw HTML

Raw HTML in text passes through as you wrote it. mkdeck copies an element with its closing tag, and the text inside it, without change:

```markdown
Run 3 <b>stalls</b> at the wall.
```

A block of raw HTML on its own line appears after the other content of the slide. Use it for a layout that the slide model does not cover.

## Add a code block

A fenced code block appears as code after the other content of the slide. mkdeck does not add color to the code.

## Limits

!!! warning
    Raw HTML runs in the browser. If you build a deck from data in Python, escape any text that you did not write. Use `html.escape` before you put the text in a slide.

Next: [Layouts](layouts.md).
