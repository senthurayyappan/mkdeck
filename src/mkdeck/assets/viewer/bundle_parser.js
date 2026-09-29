// Dependency-free .rbundle parser, taken from the rollout gallery this viewer was forked from
// (see scripts/VENDOR_VIEWER.md in the mkdeck repository).
// Imported by rollout_viewer.js as "rollout-bundle". NO `three` import.
//
// .rbundle wire format (authoritative twin of mkdeck/rollout.py, which writes the
// same header over a tail split into a shared mesh file and one file per run):
//   [4B "RBDL"][8B LE u64 headerLen][headerLen B UTF-8 JSON][binary tail]
// Tail starts 8-byte aligned; every buffer is 4-byte-element f32/u32; off=byte offset
// from tail start, count=element count.
//
// A gzip tail (header.compression === "gzip") is inflated before it gets here, by
// mkdeck-rollout.js with the browser's own DecompressionStream, which drops the
// header key once it has. Only the body poses are read; a gallery bundle's force
// and prediction buffers are left in the tail unread.

const MAGIC = 0x4c444252; // "RBDL" little-endian (bytes R=0x52,B=0x42,D=0x44,L=0x4c -> LE u32 0x4c444252)

export function parseBundle(buf) {
  const dv = new DataView(buf);
  if (dv.getUint32(0, true) !== MAGIC) throw new Error("not an .rbundle (bad magic)");
  const headerLen = Number(dv.getBigUint64(4, true));
  const headerBytes = new Uint8Array(buf, 12, headerLen);
  const header = JSON.parse(new TextDecoder().decode(headerBytes));
  if (header.compression === "gzip") throw new Error("the .rbundle tail is gzip'd and has to be inflated first");
  const tailStart = 12 + headerLen;

  function f32(spec) {
    return { data: new Float32Array(buf, tailStart + spec.off, spec.count), shape: spec.shape };
  }
  const buffers = {};
  for (const key of ["body_pos", "body_quat"]) {
    if (header.buffers[key]) buffers[key] = f32(header.buffers[key]);
  }
  const geoms = header.geoms.map(function (g) {
    const out = Object.assign({}, g);
    if (g.mesh) {
      out.verts = new Float32Array(buf, tailStart + g.mesh.verts_off, g.mesh.verts_count);
      out.faces = new Uint32Array(buf, tailStart + g.mesh.faces_off, g.mesh.faces_count);
    }
    return out;
  });
  return { meta: header.meta, geoms: geoms, buffers: buffers };
}
