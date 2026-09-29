# Convert Brax pages

Turn Brax playback pages into small rollout files that play offline.

A rollout is a recorded robot run that a slide plays in 3D. A Brax playback page carries its whole world inline: every mesh, plus six libraries that it fetches from a CDN when the page opens. As a result, thirty slides with one robot mean thirty copies of that robot, and the deck fails without a network.

## Run the converter

`mkdeck rollout` splits each page in two. First, the meshes of one model go into a shared file. Then each run keeps only its poses:

```bash
mkdeck rollout runs/*.html -o slides/assets
```

The command prints one line for each page and then a size summary. The hash in the first line depends on your model:

```text
stage0.html -> stage0.rollout (new meshes cf0f4e5579ed5ecd.meshes)
stage1.html -> stage1.rollout (shared meshes)
X MB of pages became Y MB of rollouts.
```

The last line shows the size of the pages that mkdeck read and the size of the rollouts that it wrote. It tells you what sharing the meshes saves on your own pages.

## What the command writes

| File | What it holds |
| --- | --- |
| `NAME.rollout` | The poses of one run |
| `HASH.meshes` | The meshes of one model. Runs of the same model share it |

The converter keeps every triangle, and the poses are the ones that Brax recorded, so the conversion loses nothing.

## Options

Use `--out` to choose the folder for the rollouts. It defaults to `assets`. See [CLI: rollout, check, export](../reference/cli-tools.md#mkdeck-rollout) for every option.

## Limits

!!! note
    The command skips a page with no Brax scene and says so, but it exits with an error if it skips every page.

    If mkdeck cannot convert one scene, the command reports it and converts the rest, and then it exits with an error.

    Two pages with the same file name stem, such as `a/run.html` and `b/run.html`, would write the same rollout. The command then refuses and asks you to rename one.

Next: [Show a rollout](show-a-rollout.md).
