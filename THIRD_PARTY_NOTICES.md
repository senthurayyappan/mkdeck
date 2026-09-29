# Third-party notices

mkdeck's own code is released under the MIT License (see `LICENSE`). The wheel
and the source distribution also carry the front-end libraries and fonts below,
unmodified apart from the trimming described in each row, so that a built deck
opens with no network. Each one keeps its own license, and the license text
sits beside the files in `src/mkdeck/assets/<folder>/`.

A folder build (`mkdeck build`) copies these folders, license files included,
next to `index.html`. A `--single-file` build inlines the code and leaves the
license files behind, so keep them with the deck if you redistribute it.

| Library | Version | License | Folder | Upstream |
| --- | --- | --- | --- | --- |
| reveal.js | 6.0.2 | MIT | `assets/reveal.js/` | <https://github.com/hakimel/reveal.js> |
| KaTeX (code) | 0.18.7 | MIT | `assets/katex/` | <https://github.com/KaTeX/KaTeX> |
| KaTeX fonts | 0.18.7 | OFL-1.1 | `assets/katex/dist/fonts/` | <https://github.com/KaTeX/KaTeX> |
| Roboto, from `@fontsource/roboto` | 5.3.0 | OFL-1.1 | `assets/roboto/` | <https://github.com/fontsource/fontsource>, <https://github.com/googlefonts/roboto-classic> |
| three.js (with `OrbitControls`) | 0.150.1 (r150) | MIT | `assets/three/` | <https://github.com/mrdoob/three.js> |
| marked, inlined in the reveal.js notes plugin | as bundled in reveal.js 6.0.2 | MIT | `assets/reveal.js/dist/plugin/notes.js` | <https://github.com/markedjs/marked> |

The versions come from the `package.json` files kept next to the vendored
code and from `scripts/vendor_assets.py`, which downloads each library from its
npm tarball. The SPDX expression of the package, `MIT AND OFL-1.1`, is the
union of the licenses in this table and mkdeck's own.

## What is vendored

- **reveal.js** — `dist/reveal.js`, `dist/reveal.css`, `dist/reset.css`, and the
  `notes` and `zoom` plugins. License: `assets/reveal.js/LICENSE`.
- **KaTeX** — `katex.min.js`, `katex.min.css` and the `.woff2` fonts only; the
  stylesheet is edited to drop the `.woff` and `.ttf` fallbacks that are not
  shipped. The code is MIT (`assets/katex/LICENSE`). The fonts are licensed
  under the SIL Open Font License 1.1, with the Reserved Font Names listed in
  `assets/katex/dist/fonts/OFL.txt`.
- **Roboto** — the latin subset at weights 300, 400 and 500, as `.woff2`.
  License: SIL Open Font License 1.1, in `assets/roboto/LICENSE`.
- **three.js** — `three.module.js` and `controls/OrbitControls.js`, used only by
  a deck that shows a robot rollout. License: `assets/three/LICENSE`.

## Not bundled

- **Mermaid** is not part of the package. A slide that holds a diagram loads it
  from a CDN when the deck is opened (see the docs), unless you supply your own
  copy.

## marked

The reveal.js notes plugin (`dist/plugin/notes.js`) has the `marked` Markdown
parser compiled into it. marked is distributed under the MIT License:

```text
Copyright (c) 2018+, MarkedJS (https://github.com/markedjs/)
Copyright (c) 2011-2018, Christopher Jeffrey (https://github.com/chjj/)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
