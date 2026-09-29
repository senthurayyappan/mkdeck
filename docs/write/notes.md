# Speaker notes

Add notes that only you see while you present.

```markdown
Five of five seeds cross the wall.

<!-- notes: say that the cap changes how the robot crosses the wall -->
```

An HTML comment that starts with `notes:` holds speaker notes, and it works anywhere on the slide.

## What counts as the notes

Everything after `notes:` is the text of the notes, exactly as you wrote it. So a colon, a `#`, or a word such as `yes` is only text.

## Write longer notes

For notes with several paragraphs, use a `notes` block:

```markdown
::: notes
Start with the cap.

Then show the crossing rate.
:::
```

A `---` line inside a `notes` block does not start a new slide.

## Open the presenter view

Press `S` during the talk, and reveal.js opens the presenter view with your notes.

## Write notes in Python

Set the `notes` field of a `Slide`. See [The slide model](../python/slide-model.md).

## Limits

!!! note
    A `notes:` comment cannot hold other slide options. To set notes next to other options, follow the rule in [Slide options](slide-options.md#combine-notes-and-options).

Next: [Slide options](slide-options.md).
