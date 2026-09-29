# The rollout viewer

Where the code under `src/mkdeck/assets/viewer/` came from, and what was
changed on the way. This file is for people working on mkdeck; it is not
shipped in the wheel.

The viewer draws a `.rbundle`, the file format the maintainer's rollout
gallery (a separate web app for browsing robot runs, not distributed with
mkdeck) uses. Keeping the code recognisably the same is deliberate: a bundle
that plays in the gallery should play in a deck, and a fix made in one place
should be easy to carry to the other.

| file | origin in the gallery | state |
| --- | --- | --- |
| `bundle_parser.js` | `static/bundle_parser.js` | trimmed to the body poses and the geoms; see below |
| `camera.js` | `static/app_utils.js` | the three camera helpers, lifted unchanged |
| `rollout_viewer.js` | `static/viewer.js` | forked; see below |

three.js r150.1 and its `OrbitControls` sit under `assets/three/`, at the pin
the gallery uses. `scripts/vendor_assets.py` refreshes them. The pin matters:
`viewer.js` works around r150's `OrbitControls` reading `camera.up` once, in
its constructor, and never refreshing it, and that workaround (`setCameraUp`,
which rebuilds the controls) came across with the fork.

## What the fork changes, and why

The gallery runs one viewer per sandboxed iframe, sized to the window, its
clock driven by the dashboard over `postMessage`. A deck cannot do that. An ES
module will not load from a `file://` URL, which is how a shipped deck is
opened, so the viewer runs in the slide itself, booted from `blob:` URLs by
`assets/mkdeck-rollout.js`.

- **A factory, not a module of singletons.** `createViewer(mount)` returns a
  handle, so several rollouts can be alive at once.
- **Sized to its element**, watched with a `ResizeObserver`, rather than to
  `window.innerWidth`. A slide that is off screen has no layout, and the canvas
  would otherwise settle at 1×1 and come back blank.
- **Its own clock**, with `play`/`pause`/`seek`, in place of the `bv-*`
  protocol. A deck has no dashboard to own the time.
- **`dispose()`**, because a deck keeps only the current slide and its
  neighbours alive and has to give the WebGL context back.
- **The camera follows the robot**, which the gallery leaves to the person
  dragging it. A run that travels would otherwise leave the frame with nobody
  there to bring it back.
- **`render()`** draws one frame synchronously, for the PDF export, which turns
  each rollout into a picture and cannot wait for an animation frame.
- **`preserveDrawingBuffer` left off**, three.js's own default. Turning it on
  to help screenshots does the opposite: a headless Chromium then captures the
  canvas blank, measured, while the frame it draws is correct either way.
- **No `pako`.** The gallery inflates with it; here the browser's own
  `DecompressionStream` does the job, so nothing is vendored for it.

The scene building, the geometry table, the force arrows and the prediction
lines are ported constant-for-constant. Changing any of those numbers here
without changing them in the gallery means a run looks different in the two
places.

## The format

The gallery serves a whole `.rbundle`. A deck usually holds the same bundle cut
in two — a `.meshes` file shared by every run of one model, and a `.rollout`
per run — which `mkdeck-rollout.js` glues back together before the parser sees
it. `mkdeck/rollout.py` writes that split and documents the wire format. A
whole `.rbundle` plays too: an uncompressed one is handed to the parser as it
is, and a gzip one (header `compression: "gzip"`) is inflated by
`mkdeck-rollout.js` first, since the parser is given no inflate function.
