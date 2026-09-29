# Vendored libraries

Know which libraries ship inside mkdeck, so you know what a deck fetches from the network.

mkdeck carries the libraries that a deck needs, so nothing loads when you present. Each one is a pinned release. The release comes from its npm package and sits in the repository.

| Library | Version | Used for |
| --- | --- | --- |
| reveal.js | 6.0.2 | The slides, with the notes and zoom plugins |
| KaTeX | 0.18.7 | Math, drawn in the browser, with its fonts |
| Roboto | 5.3.0 (`@fontsource/roboto`) | The default font, in three weights of the latin subset |
| three.js | r150 (0.150.1) | The rollout viewer, only in a deck that has a rollout |

## Mermaid is the exception

mkdeck does not bundle Mermaid. A slide with a diagram loads release 12.0.0 from a CDN, and mkdeck checks it against its SRI hash. Point the diagram's `data-src` at a local copy to work offline. See [Diagrams](../write/diagrams.md).

## Why three.js stays on r150

The rollout viewer works around how r150's `OrbitControls` reads the camera's `up` vector once, when the controls start. Before you move to a newer three.js, re-read that workaround.

## Licenses

Each library keeps its own license, and a folder build copies the license files next to the code. See [THIRD_PARTY_NOTICES.md](https://github.com/senthurayyappan/mkdeck/blob/main/THIRD_PARTY_NOTICES.md).

To update a library, follow [Vendor a library](https://github.com/senthurayyappan/mkdeck/blob/main/CONTRIBUTING.md#vendor-a-library) in CONTRIBUTING.md.

Next: [CLI: new, serve, build](../reference/cli.md).
