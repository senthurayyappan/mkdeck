# Tables

Show a comparison with a Markdown table.

```markdown
The higher cap raises the crossing rate.

| Cap | Crossings |
| --- | --- |
| 18 N m | 2 |
| 22 N m | 5 |
```

mkdeck gives a slide with a table the `table` layout, and the sentence appears above the table.

## Format cells

A cell takes inline Markdown, such as bold text, code, and links, and math works in every cell.

mkdeck marks numbers in the body cells but not in the header cells, so a column named `18 N m` keeps the header weight. See [Numbers and units](numbers.md).

## Check the width

A wide table can run off the slide. To find out, run `mkdeck check`, which lists the rows, the columns, and the width in pixels of each table. See [Check your slides](../share/check.md).

## Limits

!!! warning
    A slide holds one table, and it holds a table or figures, not both. Move the extra content onto a new slide.

Next: [Speaker notes](notes.md).
