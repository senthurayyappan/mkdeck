# Slide basics

Split a Markdown file into slides with `---`, and give each slide one idea.

```markdown
The Go2 finishes standing on the 0.60 m crate.

---

The Barkour model stops against the near face.
```

The file above holds two slides, because the `---` line ends the first slide and starts the second.

## Separate slides

A separator is a line of three or more dashes, alone on its line. It cuts the slide wherever it sits, even right under a paragraph.

However, mkdeck ignores a separator inside a fenced code block, an HTML comment, a `$$` block, or a `:::` block. In those blocks, a line of dashes belongs to the block.

## Say one thing per slide

Write the message as one sentence, and then add one kind of supporting content, such as a figure or a table. A slide with one message reads better than a slide with three.

## Name a slide with an id

Give a slide an id so that you can find it again. mkdeck names a slide by its id in error messages and in `check` reports, so every id must be unique. You set the id in the [slide options](slide-options.md).

## Start the file with a slide

A `---` on the first line always opens the frontmatter, which is the block of [deck settings](deck-settings.md). To start with a slide and no settings, leave out that first `---`, or write an empty frontmatter block before the slide:

```markdown
---
---

The first slide.
```

## Limits

!!! warning
    A file that opens with `---` and never closes the block is an error, and mkdeck does not skip it.

    Setext headings do not work. A line of `===` under a text line does not make a heading, and a line of `---` under a text line starts a new slide. Write headings with `#`.

Next: [Text and bullets](text.md).
