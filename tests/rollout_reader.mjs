// Reads a .rollout or .rbundle the way a deck does, and prints what came out as JSON.
//
//   node rollout_reader.mjs <assets folder> <file>
//
// It runs the real mkdeck-rollout.js (bundleFrom, in a stubbed page) to build the
// bundle the viewer reads, then the real bundle_parser.js on that. A rollout's shared
// meshes are looked up beside the file, as a single-file deck carries them inline.
import { readdirSync, readFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import vm from "node:vm";

const [assets, file] = process.argv.slice(2);
const folder = dirname(file);

// Every file beside the rollout stands in for a payload the single-file deck carries inline.
const inline = () =>
  readdirSync(folder).map((name) => ({
    getAttribute: () => name,
    get textContent() {
      return readFileSync(join(folder, name)).toString("base64");
    },
  }));
const sandbox = {
  window: { location: { protocol: "http:" }, customElements: { get: () => true, define() {} }, console },
  document: { querySelectorAll: inline },
  atob, Blob, Response, DecompressionStream, TextDecoder, TextEncoder,
};
const script = readFileSync(join(assets, "mkdeck-rollout.js"), "utf8");
// bundleFrom is a function declaration inside the script's own scope; hand it out.
vm.runInNewContext(script.replace('"use strict";', '"use strict"; window.reader = { bundleFrom };'), sandbox);

const parser = readFileSync(join(assets, "viewer", "bundle_parser.js"), "utf8");
const { parseBundle } = await import(`data:text/javascript;base64,${Buffer.from(parser).toString("base64")}`);

const bytes = new Uint8Array(readFileSync(file));
const bundle = parseBundle(await sandbox.window.reader.bundleFrom(bytes, ""));
const pos = bundle.buffers.body_pos;
const quat = bundle.buffers.body_quat;
console.log(JSON.stringify({
  name: basename(file),
  meta: bundle.meta,
  geoms: bundle.geoms.map((g) => ({
    type: g.type,
    body: g.body,
    verts: g.verts ? Array.from(g.verts) : null,
    faces: g.faces ? Array.from(g.faces) : null,
  })),
  posShape: pos.shape,
  pos: Array.from(pos.data),
  quatShape: quat.shape,
  quat: Array.from(quat.data),
}));
