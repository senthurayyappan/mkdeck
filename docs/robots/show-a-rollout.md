# Show a rollout

Play a robot run inside a slide, next to the sentence that explains it.

To show a rollout, link the `.rollout` file like any other figure. Keep the file under `assets/`:

```markdown
Stage 0 reaches the crate.

![stage 0, 0.50 m](assets/stage0.rollout)
```

The link text becomes the caption. Because the link ends in `.rollout`, mkdeck adds the viewer to the deck. A deck with no rollout carries neither the viewer nor three.js.

## How a rollout plays

A rollout plays when its slide arrives, and the camera follows the robot, so a run that travels stays in frame. Hover over the rollout to see the play button, the scrub bar, and the time.

## Keep the meshes file beside the rollout

A `.rollout` file names its shared `.meshes` file, and the viewer reads that file from the same folder. So keep both files together. A folder build copies the `.meshes` file for you when the `.rollout` file sits in the deck folder.

## Play a whole bundle

A `.rbundle` file plays without conversion, because it holds the meshes and the poses in one file. It can be plain or gzip-compressed, and you link it like a rollout:

```markdown
![stage 0](assets/stage0.rbundle)
```

## Set the camera

To pick a camera or to stop the autoplay, write the element yourself. See [Viewer options](viewer-options.md).

## Limits

!!! note
    A rollout that fails to load shows an error on its slide. `mkdeck check` reports it as `ROLLOUT-ERROR`.

Next: [Viewer options](viewer-options.md).
