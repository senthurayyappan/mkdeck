// Dependency-free .rbundle parser, vendored from the artifacts server (see VENDOR.md).
// Imported by rollout_viewer.js as "rollout-bundle". NO `three` import.
//
// .rbundle wire format (authoritative twin of mkdeck/rollout.py, which writes the
// same header over a tail split into a shared mesh file and one file per run):
//   [4B "RBDL"][8B LE u64 headerLen][headerLen B UTF-8 JSON][binary tail]
// Tail starts 8-byte aligned; every buffer is 4-byte-element f32/u32; off=byte offset
// from tail start, count=element count.
//
// v2 (header.compression === "gzip") gzip's the tail; v1 has a raw tail. Pass an
// inflate(Uint8Array)->Uint8Array to read v2 (browser: pako.inflate; node: zlib gunzip).
// off/count index the UNCOMPRESSED tail, so we inflate first, then view from its start.

const MAGIC = 0x4c444252; // "RBDL" little-endian (bytes R=0x52,B=0x42,D=0x44,L=0x4c -> LE u32 0x4c444252)

export function parseBundle(buf, inflate) {
  const dv = new DataView(buf);
  if (dv.getUint32(0, true) !== MAGIC) throw new Error("not an .rbundle (bad magic)");
  const headerLen = Number(dv.getBigUint64(4, true));
  const headerBytes = new Uint8Array(buf, 12, headerLen);
  const header = JSON.parse(new TextDecoder().decode(headerBytes));
  const tailStart = 12 + headerLen;

  // v1: view the tail in place. v2: inflate into a fresh buffer and index from its start.
  let tailBuf = buf;
  let tailBase = tailStart;
  if (header.compression === "gzip") {
    if (typeof inflate !== "function")
      throw new Error(".rbundle tail is gzip'd but no inflate() was provided");
    let u8 = inflate(new Uint8Array(buf, tailStart));
    if (u8.byteOffset % 4 !== 0) u8 = new Uint8Array(u8); // realign for typed-array views (rare)
    tailBuf = u8.buffer;
    tailBase = u8.byteOffset;
  }

  function f32(spec) {
    return { data: new Float32Array(tailBuf, tailBase + spec.off, spec.count), shape: spec.shape };
  }
  const buffers = {};
  for (const key of ["body_pos", "body_quat", "forces", "predictions"]) {
    if (header.buffers[key]) buffers[key] = f32(header.buffers[key]);
  }
  const geoms = header.geoms.map(function (g) {
    const out = Object.assign({}, g);
    if (g.mesh) {
      out.verts = new Float32Array(tailBuf, tailBase + g.mesh.verts_off, g.mesh.verts_count);
      out.faces = new Uint32Array(tailBuf, tailBase + g.mesh.faces_off, g.mesh.faces_count);
    }
    return out;
  });
  return { meta: header.meta, forceLabels: header.force_labels || [], geoms: geoms, buffers: buffers };
}
