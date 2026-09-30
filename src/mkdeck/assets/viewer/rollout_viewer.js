// Rollout viewer: draws an .rbundle with vendored three.js r150.
//
// Forked from the viewer of a rollout gallery (its origin is written down in
// scripts/VENDOR_VIEWER.md of the mkdeck source repository). That one is one viewer per sandboxed iframe, sized to the
// window and driven by the dashboard's clock over postMessage. A deck cannot use iframes: an ES module
// will not load from a file:// URL, which is how a shipped deck is opened, so
// the viewer runs in the slide itself. Hence the shape change — a factory
// bound to a mount element, sized to that element, with its own clock — while
// the scene building and the geometry table are ported constant-for-constant.
// What a deck never shows -- the force arrows, the prediction lines, the collision
// geoms and the setters that switched them -- was left behind in the fork.

import { parseBundle } from "rollout-bundle";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { cameraPreset, normalizeCamera, orthographicFrustum } from "mkdeck-camera";

const DEFAULT_BACKGROUND = 0xf4f1ea;

function quat(wxyz, i) {  // wxyz array slice -> THREE.Quaternion (xyzw)
  return new THREE.Quaternion(wxyz[i + 1], wxyz[i + 2], wxyz[i + 3], wxyz[i + 0]);
}

function clearGroup(grp) {
  while (grp.children.length) {
    const c = grp.children.pop();
    c.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    });
  }
}

// ---- scene build (ports the server viewer's _geom_mesh + _build) ----
function makeGeometry(g) {
  const s = g.size;
  if (g.type === "mesh") {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(g.verts, 3));
    geo.setIndex(new THREE.BufferAttribute(g.faces, 1));
    geo.computeVertexNormals();
    return geo;
  }
  if (g.type === "box") return new THREE.BoxGeometry(2 * s[0], 2 * s[1], 2 * s[2]);
  if (g.type === "sphere") return new THREE.SphereGeometry(s[0], 24, 16);
  if (g.type === "ellipsoid") { const geo = new THREE.SphereGeometry(1, 24, 16); geo.scale(s[0], s[1], s[2]); return geo; }
  if (g.type === "capsule") { const geo = new THREE.CapsuleGeometry(s[0], 2 * s[1], 8, 16); geo.rotateX(Math.PI / 2); return geo; }
  if (g.type === "cylinder") { const geo = new THREE.CylinderGeometry(s[0], s[0], 2 * s[1], 24); geo.rotateX(Math.PI / 2); return geo; }
  return null;  // plane handled separately
}

/**
 * Mount a viewer in an element and return the handle a slide drives it with.
 *
 * @param {HTMLElement} mount   element the canvas fills; it must be positioned.
 * @param {object} options      background (css color or number), scale, loop, follow, onFrame.
 */
export function createViewer(mount, options = {}) {
  const background = options.background === undefined ? DEFAULT_BACKGROUND : options.background;

  let bundle = null;            // parsed bundle (null until load())
  let bodyGroups = [];          // THREE.Group per body
  let dt = 1 / 30, nFrames = 1;
  let cameraState = cameraPreset("iso", options.scale);
  let playing = false, clock = 0, last = 0;
  let follow = options.follow !== false, followBody = 1, followFrom = null;
  let frameHandle = 0, disposed = false;

  // preserveDrawingBuffer stays off, three.js's own default. Turning it on to
  // help screenshots does the opposite: a headless Chromium then captures the
  // canvas blank, while the frame it draws is correct either way.
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.domElement.className = "mkd-rollout-canvas";
  mount.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  if (background !== null) scene.background = new THREE.Color(background);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 0.5));
  const key = new THREE.DirectionalLight(0xffffff, 0.8);
  key.position.set(3, 3, 6);
  scene.add(key);

  const size = () => {
    const rect = mount.getBoundingClientRect();
    return { width: Math.max(rect.width, 1), height: Math.max(rect.height, 1) };
  };
  const first = size();
  const frustum = orthographicFrustum(cameraState.scale, first.width / first.height);
  const camera = new THREE.OrthographicCamera(frustum.left, frustum.right, frustum.top, frustum.bottom, 0.01, 1000);
  camera.up.set(cameraState.up[0], cameraState.up[1], cameraState.up[2]);

  // OrbitControls (r150) captures the orbit axis from `camera.up` once, in its
  // constructor, and never refreshes it -- so a controls instance built while
  // the camera was still the three.js default +Y keeps orbiting about world +Y
  // even after the camera is pointed z-up. Rebuilding the controls is the only
  // way to move the axis on this version.
  let controls = null;
  function makeControls() {
    const target = controls ? controls.target.clone() : null;
    if (controls) controls.dispose();
    controls = new OrbitControls(camera, renderer.domElement);
    if (target) controls.target.copy(target);
  }
  makeControls();

  function setCameraUp(up) {
    if (camera.up.x === up[0] && camera.up.y === up[1] && camera.up.z === up[2]) return;
    camera.up.set(up[0], up[1], up[2]);
    makeControls();  // the "top" preset is y-up; every other view is z-up
  }

  function buildScene() {
    bodyGroups.forEach((b) => { clearGroup(b); scene.remove(b); });
    bodyGroups = [];
    const nb = bundle.buffers.body_pos.shape[1];
    for (let b = 0; b < nb; b++) { const grp = new THREE.Group(); scene.add(grp); bodyGroups.push(grp); }
    // Body 0 is the world and never moves, so the first real body is what the
    // camera holds on to. body_names lets a bundle name a better one.
    followBody = Math.min(1, nb - 1);
    const names = bundle.meta.body_names || [];
    ["torso", "trunk", "base", "chassis", "pelvis"].some(function (alias) {
      const at = names.findIndex(function (name) { return String(name || "").toLowerCase() === alias; });
      if (at > 0) { followBody = at; return true; }
      return false;
    });
    followFrom = null;

    bundle.geoms.forEach(function (g) {
      const parent = bodyGroups[g.body] || scene;
      if (g.type === "plane") {
        const grid = new THREE.GridHelper(20, 40, 0x999999, 0xcccccc);
        grid.rotateX(Math.PI / 2);  // GridHelper is xz-plane; rotate into xy (z-up ground)
        grid.position.set(g.local_pos[0], g.local_pos[1], g.local_pos[2]);
        parent.add(grid); return;
      }
      if (g.is_collision) return;  // the collision shapes are never drawn
      const geo = makeGeometry(g);
      if (!geo) return;
      const rgb = new THREE.Color(g.rgba[0], g.rgba[1], g.rgba[2]);
      const opacity = Math.min(Math.max(g.rgba[3], 0.05), 1.0);
      const mat = new THREE.MeshStandardMaterial({
        color: rgb, opacity: opacity, transparent: opacity < 1.0, roughness: 0.7, metalness: 0.0,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(g.local_pos[0], g.local_pos[1], g.local_pos[2]);
      mesh.quaternion.copy(quat(g.local_quat, 0));
      parent.add(mesh);
    });
  }

  function seekFrame(t) {
    if (!bundle) return;
    const curFrame = Math.min(Math.max(Math.round(t / dt), 0), nFrames - 1);
    const bp = bundle.buffers.body_pos.data, bq = bundle.buffers.body_quat.data;
    const nb = bundle.buffers.body_pos.shape[1];
    for (let b = 0; b < nb; b++) {
      const pj = (curFrame * nb + b) * 3, qj = (curFrame * nb + b) * 4;
      bodyGroups[b].position.set(bp[pj], bp[pj + 1], bp[pj + 2]);
      bodyGroups[b].quaternion.set(bq[qj + 1], bq[qj + 2], bq[qj + 3], bq[qj + 0]);
    }
    if (follow) {
      // Move the target and the camera together, so the run stays centred
      // while an orbit the viewer dragged is kept.
      const here = bodyGroups[followBody].position;
      if (followFrom === null) followFrom = here.clone();
      const step = here.clone().sub(followFrom);
      controls.target.add(step);
      camera.position.add(step);
      followFrom.copy(here);
    }
    if (options.onFrame) options.onFrame(curFrame * dt, duration());
  }

  // ---- camera (orthographic world scale + fixed named views) ----
  function applyFrustum(scale) {
    cameraState.scale = scale;
    const box = size();
    const f = orthographicFrustum(scale, box.width / box.height);
    camera.left = f.left; camera.right = f.right; camera.top = f.top; camera.bottom = f.bottom;
    camera.updateProjectionMatrix();
  }

  function applyCam(c) {
    cameraState = normalizeCamera(c);
    const t = cameraState.target;
    const raw = new THREE.Vector3(cameraState.off[0], cameraState.off[1], cameraState.off[2]);
    if (cameraState.view !== "custom") raw.normalize().multiplyScalar(20);
    setCameraUp(cameraState.up);
    controls.target.set(t[0], t[1], t[2]);
    camera.position.set(t[0] + raw.x, t[1] + raw.y, t[2] + raw.z);
    camera.zoom = 1;
    applyFrustum(cameraState.scale);
    controls.update();
    followFrom = null;
  }
  applyCam(cameraState);

  function duration() { return (nFrames - 1) * dt; }

  function resize() {
    const box = size();
    applyFrustum(cameraState.scale);
    renderer.setSize(box.width, box.height, false);
  }
  resize();

  // A slide that is off screen has no layout, so its canvas would size to 1x1
  // and come back blank when the slide arrives. Watching the mount catches that
  // moment without the deck having to tell the viewer about it.
  const observer = typeof ResizeObserver === "function" ? new ResizeObserver(resize) : null;
  if (observer) observer.observe(mount);

  function tick(now) {
    if (disposed) return;
    frameHandle = requestAnimationFrame(tick);
    if (playing && bundle) {
      const elapsed = last ? (now - last) / 1000 : 0;
      clock += elapsed;
      const total = duration();
      if (total > 0 && clock > total) clock = options.loop === false ? total : clock - total;
      if (total > 0 && clock >= total && options.loop === false) playing = false;
      seekFrame(clock);
    }
    last = now;
    controls.update();
    renderer.render(scene, camera);
  }
  frameHandle = requestAnimationFrame(tick);

  return {
    /** Draw an .rbundle. Takes over from whatever was shown before. */
    load(buffer) {
      bundle = parseBundle(buffer);
      const bp = bundle.buffers.body_pos;
      if (!bp || !bp.shape || bp.shape.length < 2 || !bp.data) {
        bundle = null;
        throw new Error("the rollout holds no body positions");
      }
      dt = bundle.meta.dt || 1 / (bundle.meta.fps || 30);
      nFrames = bp.shape[0];
      buildScene();
      clock = 0;
      const at = Math.min(followBody, bp.shape[1] - 1) * 3;
      applyCam(Object.assign({}, cameraState, {
        target: [bp.data[at], bp.data[at + 1], bp.data[at + 2]],
      }));
      seekFrame(0);
      return { duration: duration(), frames: nFrames };
    },
    play() { playing = true; last = 0; },
    pause() { playing = false; },
    toggle() { playing = !playing; last = 0; return playing; },
    seek(t) { clock = Math.min(Math.max(t, 0), duration()); seekFrame(clock); },
    setView(name) { applyCam(cameraPreset(name, cameraState.scale)); },
    /** Draw one frame now. A PDF export cannot wait for the next animation
     *  frame, which a headless browser may throttle away entirely. */
    render() { controls.update(); renderer.render(scene, camera); },
    get playing() { return playing; },
    get duration() { return duration(); },
    /** Give the WebGL context back; a deck keeps only a few slides alive. */
    dispose() {
      disposed = true;
      cancelAnimationFrame(frameHandle);
      if (observer) observer.disconnect();
      controls.dispose();
      bodyGroups.forEach(clearGroup);
      renderer.dispose();
      // dispose() alone leaves the context alive until garbage collection, and a
      // browser that holds too many drops the oldest, which may be a live slide.
      renderer.forceContextLoss();
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
      bundle = null;
    },
  };
}
