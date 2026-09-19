// Camera presets for the rollout viewer, vendored from the artifacts server's
// app_utils.js (see VENDOR.md). Kept function-for-function so a deck frames a
// run exactly the way the gallery does.
//
// The camera is orthographic: `scale` is the world height the viewport spans,
// so the same scale reads the same across runs whose robots start in different
// places. `off` is a direction from the target, not a position.

const DEFAULT_CAMERA = Object.freeze({
  view: "iso",
  target: Object.freeze([0, 0, 0.6]),
  off: Object.freeze([1, 1, 0.8]),
  up: Object.freeze([0, 0, 1]),
  scale: 3,
});

function finiteVector(value, fallback) {
  return Array.isArray(value) && value.length === 3 && value.every(Number.isFinite)
    ? value.slice()
    : fallback.slice();
}

export function normalizeCamera(value) {
  const source = value && typeof value === "object" ? value : {};
  const views = new Set(["iso", "side", "front", "top", "custom"]);
  const off = finiteVector(source.off, DEFAULT_CAMERA.off);
  const hasOffset = Math.hypot(off[0], off[1], off[2]) > 1e-6;
  return {
    view: views.has(source.view) ? source.view : DEFAULT_CAMERA.view,
    target: finiteVector(source.target, DEFAULT_CAMERA.target),
    off: hasOffset ? off : DEFAULT_CAMERA.off.slice(),
    up: finiteVector(source.up, DEFAULT_CAMERA.up),
    scale: Number.isFinite(source.scale) && source.scale >= 0.5 && source.scale <= 12
      ? source.scale
      : DEFAULT_CAMERA.scale,
  };
}

export function cameraPreset(name, scale = DEFAULT_CAMERA.scale) {
  const offsets = {
    iso: [1, 1, 0.8],
    side: [0, 1, 0],
    front: [1, 0, 0],
    top: [0, 0, 1],
  };
  const view = Object.hasOwn(offsets, name) ? name : DEFAULT_CAMERA.view;
  return normalizeCamera({
    view,
    target: DEFAULT_CAMERA.target,
    off: offsets[view],
    up: view === "top" ? [0, 1, 0] : DEFAULT_CAMERA.up,
    scale,
  });
}

export function orthographicFrustum(scale, aspect) {
  const halfHeight = (Number.isFinite(scale) && scale > 0 ? scale : DEFAULT_CAMERA.scale) / 2;
  const widthRatio = Number.isFinite(aspect) && aspect > 0 ? aspect : 1;
  return {
    left: -halfHeight * widthRatio,
    right: halfHeight * widthRatio,
    top: halfHeight,
    bottom: -halfHeight,
  };
}

export { DEFAULT_CAMERA };
