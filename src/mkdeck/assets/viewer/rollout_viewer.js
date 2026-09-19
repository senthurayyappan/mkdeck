// Rollout viewer: draws an .rbundle with vendored three.js r150.
//
// Forked from the artifacts server's static/viewer.js (see VENDOR.md). That one
// is one viewer per sandboxed iframe, sized to the window and driven by the
// dashboard's clock over postMessage. A deck cannot use iframes: an ES module
// will not load from a file:// URL, which is how a shipped deck is opened, so
// the viewer runs in the slide itself. Hence the shape change — a factory
// bound to a mount element, sized to that element, with its own clock — while
// the scene building, the force arrows and the prediction lines are ported
// constant-for-constant.

import { parseBundle } from "rollout-bundle";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { cameraPreset, normalizeCamera, orthographicFrustum } from "mkdeck-camera";

// ---- constants, ported verbatim from the artifacts server's viewer ----
const GRAVITY = 9.81;
const ARROW_MAX_WEIGHTS = 3; // clamp arrow at 3 robot-heights (= 3x body-weight) so impact spikes don't shoot off
const ARROW_SHAFT_R = 0.013, ARROW_HEAD_R = 0.034, ARROW_HEAD_L = 0.07;
const FORCE_COLOR = 0xff3c3c;
const PRED_TORSO_COLOR = [60, 220, 255], PRED_FOOT_COLOR = [255, 170, 60], PRED_ALL_COLOR = [150, 150, 165];
const PRED_FADE = 0.7, PRED_TORSO_LINK = 0, PRED_FOOT_LINKS = [3, 6, 9, 12];

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
 * @param {object} options      background (css color or number), speed, loop.
 */
export function createViewer(mount, options = {}) {
  const background = options.background === undefined ? DEFAULT_BACKGROUND : options.background;

  let bundle = null;            // parsed bundle (null until load())
  let bodyGroups = [];          // THREE.Group per body
  let visualHandles = [], collisionHandles = [];
  let dt = 1 / 30, nFrames = 1, weight = GRAVITY, robotHeight = 0.3;
  let curFrame = 0, showForces = true, showCollision = false, showPred = true, predMode = "torso+feet";
  let cameraState = cameraPreset("iso", options.scale);
  let applyingCamera = false;
  let playing = false, clock = 0, last = 0, speed = options.speed || 1;
  let follow = options.follow !== false, followBody = 1, followFrom = null;
  let frameHandle = 0, disposed = false;

  // preserveDrawingBuffer stays off, three.js's own default. Turning it on to
  // help screenshots does the opposite: a headless Chromium then captures the
  // canvas blank, while the frame it draws is correct either way.
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: options.preserveDrawingBuffer === true,
  });
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
    controls.enablePan = options.pan !== false;
    if (target) controls.target.copy(target);
  }
  makeControls();

  function setCameraUp(up) {
    if (camera.up.x === up[0] && camera.up.y === up[1] && camera.up.z === up[2]) return;
    camera.up.set(up[0], up[1], up[2]);
    makeControls();  // the "top" preset is y-up; every other view is z-up
  }

  const forcesGroup = new THREE.Group(); scene.add(forcesGroup);
  const predGroup = new THREE.Group(); scene.add(predGroup);

  function buildScene() {
    bodyGroups.forEach((b) => { clearGroup(b); scene.remove(b); });
    bodyGroups = []; visualHandles = []; collisionHandles = [];
    const nb = bundle.buffers.body_pos.shape[1];
    for (let b = 0; b < nb; b++) { const grp = new THREE.Group(); scene.add(grp); bodyGroups.push(grp); }
    const mass = bundle.meta.robot_mass_kg || bundle.meta.total_mass_kg || 1.0;
    weight = Math.max(mass, 1e-3) * GRAVITY;
    // Robot height = vertical span of the bodies at frame 0. Force arrows scale to it (1 body-weight
    // of force -> 1 robot-height of arrow), so they read the same across designs of different heights.
    const bp0 = bundle.buffers.body_pos.data;
    let zmin = Infinity, zmax = -Infinity;
    for (let b = 0; b < nb; b++) { const z = bp0[b * 3 + 2]; if (z < zmin) zmin = z; if (z > zmax) zmax = z; }
    robotHeight = Math.max(zmax - zmin, 0.05);
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
        parent.add(grid); visualHandles.push(grid); return;
      }
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
      mesh.visible = !g.is_collision;
      parent.add(mesh);
      (g.is_collision ? collisionHandles : visualHandles).push(mesh);
    });
  }

  function seekFrame(t) {
    if (!bundle) return;
    curFrame = Math.min(Math.max(Math.round(t / dt), 0), nFrames - 1);
    const bp = bundle.buffers.body_pos.data, bq = bundle.buffers.body_quat.data;
    const nb = bundle.buffers.body_pos.shape[1];
    for (let b = 0; b < nb; b++) {
      const pj = (curFrame * nb + b) * 3, qj = (curFrame * nb + b) * 4;
      bodyGroups[b].position.set(bp[pj], bp[pj + 1], bp[pj + 2]);
      bodyGroups[b].quaternion.set(bq[qj + 1], bq[qj + 2], bq[qj + 3], bq[qj + 0]);
    }
    drawForces(curFrame);
    drawPredictions(curFrame);
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

  function addArrow(anchor, dir, length) {
    const shaftLen = Math.max(length - ARROW_HEAD_L, 1e-3);
    const shaft = new THREE.Mesh(
      new THREE.CylinderGeometry(ARROW_SHAFT_R, ARROW_SHAFT_R, shaftLen, 12),
      new THREE.MeshStandardMaterial({ color: FORCE_COLOR }));
    const head = new THREE.Mesh(
      new THREE.ConeGeometry(ARROW_HEAD_R, ARROW_HEAD_L, 16),
      new THREE.MeshStandardMaterial({ color: FORCE_COLOR }));
    shaft.position.y = shaftLen / 2; head.position.y = shaftLen + ARROW_HEAD_L / 2;
    const arrow = new THREE.Group(); arrow.add(shaft); arrow.add(head);
    arrow.position.set(anchor[0], anchor[1], anchor[2]);
    arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3(dir[0], dir[1], dir[2]));
    forcesGroup.add(arrow);
  }

  function drawForces(frame) {
    clearGroup(forcesGroup);
    if (!showForces || !bundle.buffers.forces) return;
    const f = bundle.buffers.forces, nf = f.shape[1], base = frame * nf * 2 * 3;
    for (let k = 0; k < nf; k++) {
      const a = base + k * 2 * 3;
      const anchor = [f.data[a], f.data[a + 1], f.data[a + 2]];
      const vec = [f.data[a + 3], f.data[a + 4], f.data[a + 5]];
      if (!anchor.every(Number.isFinite) || !vec.every(Number.isFinite)) continue;
      const mag = Math.hypot(vec[0], vec[1], vec[2]);
      if (mag < 1e-9) continue;
      const length = Math.min(robotHeight * (mag / weight), ARROW_MAX_WEIGHTS * robotHeight);
      addArrow(anchor, [vec[0] / mag, vec[1] / mag, vec[2] / mag], length);
    }
  }

  function drawPredictions(frame) {
    clearGroup(predGroup);
    if (!showPred || !bundle.buffers.predictions) return;
    const p = bundle.buffers.predictions, [T, H, L] = p.shape;
    const f = Math.min(frame, T - 1);
    function lines(linkIdxs, color) {
      const pos = [], col = [];
      linkIdxs.forEach(function (li) {
        if (li >= L) return;
        for (let sIdx = 0; sIdx < H - 1; sIdx++) {
          const a = ((f * H + sIdx) * L + li) * 3, b = ((f * H + (sIdx + 1)) * L + li) * 3;
          pos.push(p.data[a], p.data[a + 1], p.data[a + 2], p.data[b], p.data[b + 1], p.data[b + 2]);
          const fade = 1.0 - PRED_FADE * (sIdx / Math.max(H - 2, 1));
          const c = [color[0] / 255 * fade, color[1] / 255 * fade, color[2] / 255 * fade];
          col.push(c[0], c[1], c[2], c[0], c[1], c[2]);
        }
      });
      if (!pos.length) return;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
      predGroup.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true })));
    }
    if (predMode === "all") lines(Array.from({ length: L }, (_, i) => i), PRED_ALL_COLOR);
    if (predMode !== "torso") lines(PRED_FOOT_LINKS, PRED_FOOT_COLOR);
    lines([PRED_TORSO_LINK], PRED_TORSO_COLOR);
  }

  function setLayers() {
    visualHandles.forEach((h) => (h.visible = true));
    collisionHandles.forEach((h) => (h.visible = showCollision));
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
    applyingCamera = true;
    setCameraUp(cameraState.up);
    controls.target.set(t[0], t[1], t[2]);
    camera.position.set(t[0] + raw.x, t[1] + raw.y, t[2] + raw.z);
    camera.zoom = 1;
    applyFrustum(cameraState.scale);
    controls.update();
    applyingCamera = false;
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
      clock += elapsed * speed;
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
      setLayers();
      clock = 0;
      if (options.target !== false) {
        const nb = bp.shape[1];
        const at = Math.min(followBody, nb - 1) * 3;
        applyCam(Object.assign({}, cameraState, {
          target: [bp.data[at], bp.data[at + 1], bp.data[at + 2]],
        }));
      }
      seekFrame(0);
      return { duration: duration(), frames: nFrames };
    },
    play() { playing = true; last = 0; },
    pause() { playing = false; },
    toggle() { playing = !playing; last = 0; return playing; },
    seek(t) { clock = Math.min(Math.max(t, 0), duration()); seekFrame(clock); },
    setSpeed(value) { speed = Number(value) || 1; },
    setView(name) { applyCam(cameraPreset(name, cameraState.scale)); },
    setScale(value) { applyFrustum(Number(value) || cameraState.scale); },
    setCollision(on) { showCollision = !!on; setLayers(); },
    setForces(on) { showForces = !!on; if (bundle) drawForces(curFrame); },
    setPredictions(on, mode) {
      showPred = on !== false;
      if (typeof mode === "string") predMode = mode;
      if (bundle) drawPredictions(curFrame);
    },
    resize,
    /** Draw one frame now. A screenshot cannot wait for the next animation
     *  frame, which a headless browser may throttle away entirely. */
    render() { controls.update(); renderer.render(scene, camera); },
    get playing() { return playing; },
    get time() { return curFrame * dt; },
    get duration() { return duration(); },
    /** Give the WebGL context back; a deck keeps only a few slides alive. */
    dispose() {
      disposed = true;
      cancelAnimationFrame(frameHandle);
      if (observer) observer.disconnect();
      controls.dispose();
      bodyGroups.forEach(clearGroup);
      clearGroup(forcesGroup);
      clearGroup(predGroup);
      renderer.dispose();
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
      bundle = null;
    },
  };
}
