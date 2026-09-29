# Numbers and units

Make readers see the numbers first. mkdeck marks each number in a darker ink.

```markdown
Departure speed reaches 2.10 m/s at 22 N m.
```

mkdeck marks `2.10 m/s` and `22 N m` as two values, because a number keeps its unit. However, a number inside a word stays gray, so the `2` in `Go2` is not marked.

## Where marking applies

mkdeck marks numbers in the text of a slide, which means a sentence, a bullet, or a table cell. A figure label, a heading, and a table header keep one weight.

## Default units

Unless you set your own list, mkdeck recognizes these units:

`N m s/rad`, `kg m^2`, `rad/s`, `body weights`, `N m`, `mm`, `ms`, `Hz`, `kg`, `m`, `s`, `m/s`, `%`, `percent`, `degrees`

Each spelling is one unit. For example, `N m s/rad` is a single unit.

## Set your own units

Set `units` in `deck.yml`, in the frontmatter, or on a `Deck` in Python. Your list replaces the defaults:

```yaml
units:
  - N m
  - mm
  - s
```

The order of the list does not matter, because mkdeck tries the longest spelling first. As a result, `N m` matches before `m`.

## Limits

!!! note
    An empty list marks the number and no unit. Then `22 N m` marks only `22`.

Next: [Math](math.md).
