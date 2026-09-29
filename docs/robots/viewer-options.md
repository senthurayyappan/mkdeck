# Viewer options

Choose the camera, the autoplay, and the background of a rollout.

A figure written as `![](...)` has no place for options. So write the `<deck-rollout>` element yourself, as raw HTML, and keep the file under `assets/`:

```markdown
Stage 1 goes over the crate.

<deck-rollout src="assets/stage1.rollout" data-view="side" data-autoplay="false"></deck-rollout>
```

mkdeck sees the element and adds the viewer to the deck, as it does for a figure.

## The options

You set each option as a `data-` attribute:

| Attribute | What it does | Default |
| --- | --- | --- |
| `data-autoplay="false"` | Waits for you to press play | plays at once |
| `data-loop="false"` | Stops at the end | starts over |
| `data-follow="false"` | Holds the camera still | follows the robot |
| `data-view="side"` | Sets the camera: `iso`, `side`, `front`, or `top` | `iso` |
| `data-scale="2.4"` | Sets the world height that the viewport spans, in meters | `3` |
| `data-background="#fff"` | Sets the background, as a CSS color | `#f4f1ea` |

## Limits

!!! note
    `data-scale` takes a value from 0.5 to 12. Any other value falls back to `3`.

Next: [Share and export rollouts](share-rollouts.md).
