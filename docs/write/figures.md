# Figures

Show an image, an HTML page, or a robot run on a slide with an image link.

A figure can be an image, an HTML page, or a rollout, which is a recorded robot run. The code calls a figure an embed, so you also meet that word in Python and in warnings.

```markdown
![Run 3, 22 N m](assets/run3.html)
```

The link text becomes the caption above the frame, and the file suffix decides how mkdeck draws the figure:

| Suffix | mkdeck draws |
| --- | --- |
| `.html`, `.htm` | An iframe. Use it for a Plotly chart or any interactive page |
| `.rollout`, `.rbundle` | A robot run in the rollout viewer. See [Show a rollout](../robots/show-a-rollout.md) |
| Any other suffix | An image, such as a PNG, an SVG, or a GIF |

The source can also be an `http` or `https` URL.

## Show two figures

To put two figures side by side, place them inside a `figures` block:

```markdown
::: figures
![Unitree Go2](assets/a1_go2_crate.html)
![Barkour CAD](assets/a1_cad_crate.html)
:::
```

Two image lines in a row also make two figures, so the block is optional.

## Wrap a figure in a link

An image alone in a paragraph is a figure, and so is an image that only a link or emphasis wraps. The next line makes a figure and drops the link:

```markdown
[![Run 3](assets/run3.png)](https://example.org)
```

## Put an image inside text

An image inside a bullet or a table cell appears where you wrote it. mkdeck copies everything under `assets/`, so an image there works. However, mkdeck copies no local image from any other place, so it warns you and the image breaks. To fix this, move the file under `assets/`, or write the image on a line of its own.

## Limits

!!! warning
    A slide holds at most two figures, and it holds figures or a table, not both. Move the extra content onto a new slide.

Next: [HTML pages in slides](embeds.md).
