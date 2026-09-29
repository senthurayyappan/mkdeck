# Layouts

Let mkdeck pick the layout of each slide from its content, so that you rarely set a layout yourself.

## Layout follows content

First, you write the content. Then mkdeck chooses the layout that fits it:

| Layout | mkdeck picks it when |
| --- | --- |
| `title` | A heading is the only content |
| `figures` | The slide holds figures |
| `table` | The slide holds a table |
| `statement` | Anything else |

The default value is `auto`, which means "pick from the content". To force a layout, set `layout` in the [slide options](slide-options.md).

## Order on the slide

The order you write things in does not decide where they land. Instead, mkdeck draws every slide in one fixed order:

1. The heading.
2. The display formulas.
3. The sentences.
4. The bullets.
5. The figures or the table.
6. The code blocks, raw HTML, and diagrams.

For example, this slide draws the formula first and the two paragraphs after it:

```markdown
The loss is

$$L = x$$

which matters
```

To keep a formula inside a sentence, write it as inline math, such as `$L = x$`, or split the text across two slides.

## Title slides

A deck that sets a `title` opens with a generated title slide, which mkdeck draws from `title` and `date`.

Sometimes your first slide is already a title slide, either as a `#` heading alone or as a slide with `layout: title`. In that case, mkdeck uses your slide as the opening slide and generates none.

A deck with no `title` gets no generated slide, so its first slide is the first one you wrote. The browser tab then shows the first `#` heading, or "Slide Deck" when there is none. To drop the generated slide in any deck, set `title_slide: false`.

A title slide with its own `date` sets the date in the corner of every later slide.

## Limits

!!! note
    A deck with no slide and no title slide is an error.

    In Python, a slide that holds only a `title` is a statement slide, so set `layout="title"` to make a title slide.

Next: [Numbers and units](numbers.md).
