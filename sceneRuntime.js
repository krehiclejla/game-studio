// Scene games: the game is a scene (scene.json) of objects with behaviours, built
// into a live three.js world by this runtime. The studio shows it in Edit mode
// (orbit, tap to select, drag to move) and Play mode (player, behaviours, scripts).
// The assistant edits the scene with scene.py; the same runtime runs in games
// installed as apps. See SCENE.md for the format.
//
// SCENE_RUNTIME is the module's source text: it is written into each game's HTML
// (sceneDocument here, and scene.py for the assistant), so keep it free of
// backticks and dollar-brace sequences.

export const SCENE_RUNTIME = String.raw`
import * as THREE from 'https://esm.sh/three@0.180.0';
import { GLTFLoader } from 'https://esm.sh/three@0.180.0/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'https://esm.sh/three@0.180.0/examples/jsm/controls/OrbitControls.js';
import * as SkeletonUtils from 'https://esm.sh/three@0.180.0/examples/jsm/utils/SkeletonUtils.js';
import { RoomEnvironment } from 'https://esm.sh/three@0.180.0/examples/jsm/environments/RoomEnvironment.js';

const send = (m) => { try { parent.postMessage(m, '*'); } catch (e) {} };
const studio = window.studio || { input: { x: 0, y: 0, a: false, b: false }, model: () => null, image: () => null, characters: () => [], controls: () => {}, sound: () => {}, music: () => {}, stopMusic: () => {} };
let SCENE = JSON.parse(document.getElementById('scene').textContent || '{}');
let MODE = window.__sceneMode || 'play';

// ---------- renderer, camera, world ----------
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
document.body.appendChild(renderer.domElement);
renderer.domElement.style.cssText = 'display:block;width:100vw;height:100vh;touch-action:none';
const world = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.05, 2000);
camera.position.set(12, 10, 14);
const orbit = new OrbitControls(camera, renderer.domElement);
orbit.enableDamping = true;
orbit.maxPolarAngle = Math.PI * 0.49;
// While the person drags the view (and a moment after), the play camera doesn't swing on its own.
let viewDragging = false, viewDraggedAt = -Infinity;
orbit.addEventListener('start', () => { viewDragging = true; });
orbit.addEventListener('end', () => { viewDragging = false; viewDraggedAt = performance.now(); });
const hemi = new THREE.HemisphereLight(0xffffff, 0x445544, 1.0);
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -40; sun.shadow.camera.right = 40; sun.shadow.camera.top = 40; sun.shadow.camera.bottom = -40;
sun.shadow.camera.far = 200;
// Toy style: a soft rim light from behind the scene, off unless the game uses it.
const rim = new THREE.DirectionalLight(0xbfd8ff, 0);
rim.position.set(-40, 25, -50);
world.add(hemi, sun, sun.target, rim);
const grid = new THREE.GridHelper(100, 100, 0x888888, 0x555555);
grid.material.transparent = true; grid.material.opacity = 0.25;
world.add(grid);
addEventListener('resize', () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });

// A visual style for the whole game. 'ps2': a low-resolution, hard-shadowed, low-poly look.
const PS2 = () => (SCENE.settings || {}).style === 'ps2';
// 'toy': a bright, glossy, cartoony look, like plastic toys under studio lights.
const TOY = () => (SCENE.settings || {}).style === 'toy';
let toyEnv = null;
const getToyEnv = () => { if (!toyEnv) { const pm = new THREE.PMREMGenerator(renderer); toyEnv = pm.fromScene(new RoomEnvironment(), 0.04).texture; pm.dispose(); } return toyEnv; };
// Performance defaults (settings.performance: false turns them all off): culling of
// off-screen and far-away props, a lower resolution when frames stay slow, and
// shaders compiled before play starts.
const PERF_ON = () => (SCENE.settings || {}).performance !== false;
const perf = { scale: 1, slow: 1 / 60, frame: 0 };
function applyPixelRatio() {
  const ratio = PS2() ? Math.min(1, 448 / innerHeight) : Math.min(devicePixelRatio, 2) * perf.scale;
  renderer.setPixelRatio(ratio);
  renderer.setSize(innerWidth, innerHeight);
}
function applyStyle() {
  const ps2 = PS2();
  applyPixelRatio();
  renderer.domElement.style.imageRendering = ps2 ? 'pixelated' : '';
  // Gritty screen: washed-out colour, film grain and a dark vignette.
  renderer.domElement.style.filter = ps2 ? 'contrast(1.1) saturate(0.78) brightness(0.97)' : '';
  grain.style.display = ps2 ? 'block' : 'none';
  const toy = TOY();
  if (toy) {
    renderer.domElement.style.filter = 'saturate(1.25) contrast(1.08)';
  }
  renderer.toneMappingExposure = 1;
  rim.intensity = toy ? 1.6 : 0;
  const type = ps2 ? THREE.BasicShadowMap : THREE.PCFSoftShadowMap;
  if (renderer.shadowMap.type !== type) {
    renderer.shadowMap.type = type;
    sun.shadow.mapSize.set(ps2 ? 512 : 2048, ps2 ? 512 : 2048);
    if (sun.shadow.map) { sun.shadow.map.dispose(); sun.shadow.map = null; }
  }
}
const grain = document.createElement('div');
{
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'), img = g.createImageData(128, 128);
  for (let i = 0; i < img.data.length; i += 4) { const v = Math.random() * 255; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255; }
  g.putImageData(img, 0, 0);
  grain.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:4;display:none;mix-blend-mode:overlay;opacity:.14;image-rendering:pixelated;'
    + 'background:radial-gradient(ellipse at center,transparent 55%,rgba(0,0,0,.55) 100%),url(' + c.toDataURL() + ');background-size:100% 100%,256px 256px';
  document.body.appendChild(grain);
  let f = 0; setInterval(() => { if (grain.style.display !== 'none') grain.style.backgroundPosition = '0 0,' + ((f = (f + 37) % 256)) + 'px ' + ((f * 3) % 256) + 'px'; }, 70);
}
addEventListener('resize', applyStyle);
// A grimy, low-res surface texture every PS2-style material is multiplied with: blotches, streaks and speckle.
let gritTex = null;
function grit(repeat) {
  if (!gritTex) {
    const N = 64, c = document.createElement('canvas'); c.width = c.height = N;
    const g = c.getContext('2d'), img = g.createImageData(N, N);
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const blot = noise2(x / 9, y / 9, 3) * 0.6 + noise2(x / 4, y / 4, 5) * 0.4;
      const streak = noise2(x / 2, y / 14, 9);
      let v = 165 + blot * 65 + streak * 25 + (Math.random() - 0.5) * 28;
      if (Math.random() < 0.02) v -= 60;
      v = Math.max(70, Math.min(255, v));
      const i = (y * N + x) * 4; img.data[i] = v; img.data[i + 1] = v * 0.97; img.data[i + 2] = v * 0.92; img.data[i + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    gritTex = new THREE.CanvasTexture(c);
    gritTex.wrapS = gritTex.wrapT = THREE.RepeatWrapping;
    gritTex.magFilter = THREE.NearestFilter; gritTex.colorSpace = THREE.SRGBColorSpace;
  }
  const t = gritTex.clone(); t.repeat.set(repeat, repeat); t.needsUpdate = true;
  return t;
}
const gritFor = (o) => { const sc = Array.isArray(o.scale) ? Math.max(...o.scale.map(Number).filter(Number.isFinite)) : num(o.scale, 1); return grit(Math.max(1, Math.min(8, Math.round(sc * 1.2)))); };
const segs = (n) => PS2() ? Math.max(6, Math.round(n / 4)) : n;

// ---------- helpers ----------
const col = (c, d) => new THREE.Color(c || d || '#888888');
const num = (v, d) => (typeof v === 'number' && isFinite(v) ? v : d);
const vec = (a, d) => (Array.isArray(a) ? a : d);
const deg = (v) => (num(v, 0) * Math.PI) / 180;
function hash(n) { const s = Math.sin(n * 127.1) * 43758.5453; return s - Math.floor(s); }
function noise2(x, z, seed) {
  const xi = Math.floor(x), zi = Math.floor(z), xf = x - xi, zf = z - zi;
  const r = (a, b) => hash(a * 57 + b * 131 + seed * 17.3);
  const u = xf * xf * (3 - 2 * xf), v = zf * zf * (3 - 2 * zf);
  const a = r(xi, zi), b = r(xi + 1, zi), c = r(xi, zi + 1), d = r(xi + 1, zi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

// A river carved into a terrain: terrain.river = { points: [[x, z], ...], width, depth, color, bed, flow }.
function riverInfo(o) {
  const r = o.river, pts = r && Array.isArray(r.points) ? r.points.filter((p) => Array.isArray(p) && p.length >= 2) : [];
  if (pts.length < 2) return null;
  return { pts, half: num(r.width, 4) / 2, depth: num(r.depth, 1.2), color: r.color || '#5cc8e8', bed: r.bed || '#e6cf92', flow: num(r.flow, 1) };
}
function riverDist(R, x, z) {
  let best = Infinity;
  for (let i = 0; i < R.pts.length - 1; i++) {
    const [ax, az] = R.pts[i], [bx, bz] = R.pts[i + 1], dx = bx - ax, dz = bz - az;
    const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz || 1)));
    best = Math.min(best, Math.hypot(x - ax - dx * t, z - az - dz * t));
  }
  return best;
}
// 1 in the river bed, easing to 0 at the top of its banks.
function riverCarve(R, x, z) {
  const d = riverDist(R, x, z), u = Math.max(0, Math.min(1, (d - R.half * 0.6) / (R.half * 0.4 + 1.2)));
  return 1 - u * u * (3 - 2 * u);
}
function terrainHeightFn(o) {
  const base = baseHeightFn(o), R = riverInfo(o);
  return R ? (x, z) => base(x, z) - R.depth * riverCarve(R, x, z) : base;
}
// Flowing water along the river's path: a ribbon with a scrolling ripple texture.
function riverWater(o, R) {
  const base = baseHeightFn(o), w = R.half + 1.2, step = 0.5, pos = [], uv = [], idx = [];
  const samples = [];
  for (let i = 0; i < R.pts.length - 1; i++) {
    const [ax, az] = R.pts[i], [bx, bz] = R.pts[i + 1], n = Math.max(1, Math.ceil(Math.hypot(bx - ax, bz - az) / step));
    for (let k = 0; k < n; k++) samples.push([ax + (bx - ax) * k / n, az + (bz - az) * k / n]);
  }
  samples.push(R.pts[R.pts.length - 1]);
  let along = 0;
  samples.forEach(([x, z], i) => {
    const a = samples[Math.max(0, i - 1)], b = samples[Math.min(samples.length - 1, i + 1)];
    let tx = b[0] - a[0], tz = b[1] - a[1]; const l = Math.hypot(tx, tz) || 1; tx /= l; tz /= l;
    if (i) along += Math.hypot(x - samples[i - 1][0], z - samples[i - 1][1]);
    const y = base(x, z) - R.depth * 0.38;
    pos.push(x + tz * w, y, z - tx * w, x - tz * w, y, z + tx * w);
    uv.push(0, along / 6, 1, along / 6);
    if (i) { const q = i * 2; idx.push(q - 2, q - 1, q, q - 1, q + 1, q); }
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx); geo.computeVertexNormals();
  // Ripple texture: the water colour with soft lighter streaks running downstream.
  const cv = document.createElement('canvas'); cv.width = 128; cv.height = 256;
  const g = cv.getContext('2d'), c = col(R.color);
  g.fillStyle = '#' + c.getHexString(); g.fillRect(0, 0, 128, 256);
  let seed = 3; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 70; i++) {
    const x = rnd() * 128, y = rnd() * 256, len = 10 + rnd() * 30;
    g.strokeStyle = 'rgba(255,255,255,' + (0.18 + rnd() * 0.35).toFixed(2) + ')'; g.lineWidth = 1.5 + rnd() * 2.5; g.lineCap = 'round';
    g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(x + 4, y + len / 2, x, y + len); g.stroke();
  }
  const tex = new THREE.CanvasTexture(cv); tex.wrapS = tex.wrapT = THREE.RepeatWrapping; tex.colorSpace = THREE.SRGBColorSpace;
  const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: tex, transparent: true, opacity: 0.85, roughness: 0.15, metalness: 0.05, depthWrite: false }));
  mesh.receiveShadow = true;
  mesh.userData.flow = (dt) => { tex.offset.y -= R.flow * dt / 6; };
  return mesh;
}

// Terrain height functions, in the terrain's own space (0 at its position).
function baseHeightFn(o) {
  const shape = o.shape || 'flat', h = num(o.height, shape === 'mountains' ? 12 : 4), size = num(o.size, 60), seed = num(o.seed, 1);
  if (shape === 'flat') return () => 0;
  return (x, z) => {
    const s = 8 / size;
    let n = 0, amp = 1, f = s, tot = 0;
    for (let i = 0; i < (shape === 'mountains' ? 5 : 3); i++) { n += amp * noise2(x * f, z * f, seed + i); tot += amp; amp *= 0.5; f *= 2; }
    n /= tot;
    if (shape === 'mountains') n = Math.pow(n, 1.6);
    let y = (n - (shape === 'island' ? 0.2 : 0.35)) * h * (shape === 'mountains' ? 1.6 : 1);
    if (shape === 'island') {
      // A round island: a gently rolling top inside a softly wobbling circular coast
      // (about 70% of the terrain's half-size), a beach slope, then the sea floor.
      // coast (0..0.35) pushes out headlands and bays; hills raises rolling hills
      // outside the flat middle (flat, default: the paving) except in the clear circles.
      const a = Math.atan2(z, x), r = Math.hypot(x, z), coast = num(o.coast, -1);
      const cn = noise2(Math.cos(a) * 1.3 + 50, Math.sin(a) * 1.3 + 50, seed + 9);
      const wob = coast < 0 ? 1 + 0.1 * (cn - 0.5)
        : 1 + coast * (0.65 * cn + 0.35 * noise2(Math.cos(a) * 3.1 + 80, Math.sin(a) * 3.1 + 80, seed + 13));
      const e = r / (size / 2 * 0.7 * wob);
      const top = h * 0.6 + (n - 0.5) * h * Math.max(0, 1 - e * e);
      const t = Math.min(1, Math.max(0, (e - 0.82) / 0.3)), s = t * t * (3 - 2 * t);
      y = top * (1 - s) - 1.6 * s - Math.max(0, e - 1.12) * 4;
      const hills = num(o.hills, 0);
      if (hills > 0) {
        const P = o.paving === true ? {} : o.paving, pavR = P ? num(P.radius, size / 2 * 0.7 * 0.8) : 0;
        const flat = num(o.flat, pavR ? pavR + 0.6 : 0);
        const ss = (a0, a1, v) => { const q = Math.min(1, Math.max(0, (v - a0) / (a1 - a0))); return q * q * (3 - 2 * q); };
        let k = ss(flat, flat + 3, r) * (1 - ss(0.72, 1.0, e));
        for (const c of Array.isArray(o.clear) ? o.clear : []) k *= ss(num(c[2], 3), num(c[2], 3) + 2.5, Math.hypot(x - num(c[0], 0), z - num(c[1], 0)));
        const hn = noise2(x * 0.14 + 20, z * 0.14 + 20, seed + 21) * 0.7 + noise2(x * 0.33 + 5, z * 0.33 + 5, seed + 23) * 0.3;
        y += hills * k * Math.pow(hn, 1.4) * 1.5;
      }
      y = Math.max(y, -3);
    }
    return y;
  };
}

// ---------- objects ----------
const loader = new GLTFLoader();
const gltfCache = new Map();
function loadGltf(name) {
  if (!gltfCache.has(name)) {
    const buf = studio.model(name);
    gltfCache.set(name, buf ? new Promise((res, rej) => loader.parse(buf, '', res, rej)) : Promise.resolve(null));
  }
  return gltfCache.get(name);
}
const libraryHeight = (name) => { const c = (studio.characters ? studio.characters() : []).find((e) => e.name === name); return c && c.height; };

const live = new Map(); // id -> { data, root, mixer, actions, terrain, box }
let terrains = [];
// The highest ground under (x, z): terrain, the top of solid objects, and the real
// surface of walkable models (a bridge deck, stairs). With "below", a walkable
// surface only counts up to that height, so rails and roofs above you are not floor.
// Returns -Infinity where there is nothing at all.
const downRay = new THREE.Raycaster(), DOWN = new THREE.Vector3(0, -1, 0);
const FOOT = [[0, 0], [0, 0.12], [0, -0.12], [0.12, 0], [-0.12, 0]];
const STEP = 0.35; // the highest step a player takes onto a walkable surface (a plank, a stair), not a railing
function landAt(x, z, except, below) {
  let y = -Infinity;
  for (const t of terrains) {
    const half = t.size / 2, lx = x - t.x, lz = z - t.z;
    if (Math.abs(lx) <= half && Math.abs(lz) <= half) y = Math.max(y, t.y + t.fn(lx, lz));
  }
  for (const e of live.values()) {
    if (e === except || !e.box || !(e.solid || e.data.walkable)) continue;
    const b = e.box;
    if (x < b.min.x || x > b.max.x || z < b.min.z || z > b.max.z) continue;
    if (e.solid) { y = Math.max(y, b.max.y); continue; }
    // The surface right underfoot; only where that is a gap between planks do the
    // spots just around it count, so gaps aren't holes and railings beside you aren't floor.
    for (const [dx, dz] of FOOT) {
      downRay.set(new THREE.Vector3(x + dx, below === undefined ? b.max.y + 1 : below, z + dz), DOWN);
      const hit = downRay.intersectObject(e.root, true).find((h) => h.object.visible && !h.object.userData.editOnly);
      if (hit) { y = Math.max(y, hit.point.y); break; }
    }
  }
  return y;
}
function groundAt(x, z, except, below) {
  const y = landAt(x, z, except, below);
  return y === -Infinity ? 0 : y;
}
// Water the player can't walk into: a spot is wet when a water surface covers it
// and there is no ground above that surface (the sea around an island).
let seas = [];
function wetAt(x, z, except, below) {
  const covering = seas.filter((w) => Math.abs(x - w.x) <= w.half && Math.abs(z - w.z) <= w.half);
  if (!covering.length) return false;
  const land = landAt(x, z, except, below);
  return covering.some((w) => land < w.y + 0.08);
}

// Toy style: turn a material into glossy, clear-coated plastic.
function toyMaterial(m, gloss) {
  const p = new THREE.MeshPhysicalMaterial({ color: m.color, map: m.map || null, vertexColors: m.vertexColors, transparent: m.transparent, opacity: m.opacity,
    emissive: m.emissive || new THREE.Color(0), emissiveMap: m.emissiveMap || null, normalMap: m.normalMap || null, emissiveIntensity: num(m.emissiveIntensity, 1), side: m.side,
    roughness: gloss ? 0.4 : 0.85, metalness: Math.min(num(m.metalness, 0), 0.3), clearcoat: gloss ? 1 : 0, clearcoatRoughness: gloss ? 0.12 : 0.5, envMap: gloss ? getToyEnv() : null, envMapIntensity: 0.4, flatShading: m.flatShading });
  p.name = m.name || '';
  return p;
}
function material(o, fallback) {
  if (TOY()) return toyMaterial(new THREE.MeshStandardMaterial({ color: col(o.color, fallback), metalness: num(o.metalness, 0), transparent: num(o.opacity, 1) < 1, opacity: num(o.opacity, 1) }), true);
  const gritty = PS2() && num(o.opacity, 1) >= 1 && !o.clean;
  return new THREE.MeshStandardMaterial({ map: gritty ? gritFor(o) : null, color: col(o.color, fallback), roughness: num(o.roughness, 0.85), metalness: num(o.metalness, 0), transparent: num(o.opacity, 1) < 1, opacity: num(o.opacity, 1) });
}

// A mountain border: a snowy range that rises from the terrain's edges and fences the player in.
function borderFn(o, inner) {
  const b = o.border === true ? {} : o.border, half = num(o.size, 60) / 2;
  const w = num(b.width, 45), h = num(b.height, 26), seed = num(o.seed, 1) + 40;
  const ridge = (x, z) => {
    let n = 0, amp = 1, f = 1 / 22, tot = 0;
    for (let i = 0; i < 5; i++) { const r = 1 - Math.abs(2 * noise2(x * f, z * f, seed + i) - 1); n += amp * r * r; tot += amp; amp *= 0.5; f *= 2.1; }
    return n / tot;
  };
  const fn = (x, z) => {
    const d = Math.max(Math.abs(x), Math.abs(z)) - half;
    if (d <= 0) return inner(x, z);
    const t = Math.min(1, d / (w * 0.4)), rise = t * t * (3 - 2 * t);
    return inner(x, z) * (1 - rise) + h * rise * (0.25 + 0.95 * ridge(x, z)) * (0.75 + 0.25 * Math.min(1, d / w));
  };
  return { fn, size: half * 2 + w * 2, snow: col(b.snow, '#f4f7fb'), rock: col(b.rock, '#5d6470') };
}

// A floating island: one sculpted piece of land hanging in the sky. A wavy outline,
// a gently rolling grassy top with a sandy rim, and a layered rocky underside that
// tapers into hanging points, plus a few rock spikes. The object's position is the
// middle of its grass; walking off the edge means falling.
function floatingIsland(o) {
  const size = num(o.size, 24), half = size / 2, seed = num(o.seed, 1), hills = num(o.height, 1.2);
  const depth = num(o.depth, size * 0.55), TAU = Math.PI * 2;
  const ring = (a, f, s) => noise2(Math.cos(a) * f + 50, Math.sin(a) * f + 50, s); // seamless around the circle
  const edgeR = (a) => half * (0.8 + 0.3 * (0.65 * ring(a, 1.6, seed) + 0.35 * ring(a, 4.2, seed + 3) - 0.5));
  const lobe = (a) => 0.5 + 0.95 * Math.pow(0.6 * ring(a, 2.4, seed + 7) + 0.4 * ring(a, 6.5, seed + 9), 1.8);
  const smooth = (a, b, x) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  const fbm = (x, z, s) => { let n = 0, amp = 1, f = 3 / size, tot = 0; for (let i = 0; i < 4; i++) { n += amp * noise2(x * f, z * f, s + i); tot += amp; amp *= 0.5; f *= 2; } return n / tot; };
  const top = (x, z) => {
    const e = Math.hypot(x, z) / edgeR(Math.atan2(z, x));
    if (e > 1) return -1000;
    return (fbm(x, z, seed + 20) - 0.45) * 2 * hills * (1 - smooth(0.55, 0.95, e)) - 0.45 * smooth(0.8, 1, e);
  };
  return { size, half, seed, depth, TAU, ring, edgeR, lobe, smooth, fbm, top };
}

function buildFloatingIsland(o) {
  const I = floatingIsland(o), { TAU, edgeR, lobe, smooth, fbm, top, depth, seed } = I;
  const grass = col(o.color, '#8ed65a'), grass2 = col(o.color2, '#6cbf45'), sand = col(o.sand, '#f1dfae');
  const rock = col(o.rock, '#b08058'), rock2 = col(o.rock2, '#7a5a40'), c = new THREE.Color();
  const NS = 180, NR = 44, NK = 16, group = new THREE.Group();
  const mat = (flat) => new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, flatShading: flat });
  const mesh = (pos, colors, idx, flat) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    g.setIndex(idx); g.computeVertexNormals();
    const m = new THREE.Mesh(g, mat(flat)); m.castShadow = true; m.receiveShadow = true; group.add(m); return m;
  };
  // Grassy top: rings from the middle out to the wavy edge.
  { const pos = [0, top(0, 0), 0], colors = [], idx = [];
    c.copy(grass); colors.push(c.r, c.g, c.b);
    for (let r = 1; r <= NR; r++) for (let s = 0; s < NS; s++) {
      const a = (s / NS) * TAU, e = r / NR, R = edgeR(a) * e, x = Math.cos(a) * R, z = Math.sin(a) * R;
      const y = top(x, z); pos.push(x, y < -100 ? -0.45 : y, z);   // (the rim itself can round past the edge)
      c.copy(grass).lerp(grass2, smooth(0.35, 0.75, fbm(x * 1.7, z * 1.7, seed + 40)));
      c.lerp(sand, smooth(0.84, 0.93, e + (fbm(x * 3, z * 3, seed + 50) - 0.5) * 0.06));
      colors.push(c.r, c.g, c.b);
    }
    const at = (r, s) => (r === 0 ? 0 : 1 + (r - 1) * NS + (s % NS));
    for (let r = 0; r < NR; r++) for (let s = 0; s < NS; s++) {
      if (r === 0) { idx.push(0, at(1, s + 1), at(1, s)); continue; }
      const a = at(r, s), b = at(r, s + 1), d = at(r + 1, s), e = at(r + 1, s + 1);
      idx.push(a, b, d, b, e, d);
    }
    mesh(pos, colors, idx, false);
  }
  // Rocky underside: from the rim down to hanging points, bumpy and layered.
  { const pos = [], colors = [], idx = [], S2 = 64;
    for (let k = 0; k <= NK; k++) for (let s = 0; s < S2; s++) {
      const a = (s / S2) * TAU, v = k / NK, R0 = edgeR(a);
      // Rocky bumps, fading out at the rim so it meets the beach cleanly.
      const bump = 1 + smooth(0, 0.15, v) * (0.1 * (noise2(a * 9, v * 7, seed + 60) - 0.5) + 0.06 * (noise2(a * 22, v * 16, seed + 61) - 0.5));
      const R = R0 * Math.pow(1 - v, 0.8) * bump;
      const y = -0.45 - 0.5 * smooth(0, 0.1, v) - depth * Math.pow(v, 1.15) * lobe(a) * (0.9 + 0.2 * noise2(a * 5, v * 4, seed + 62));
      pos.push(Math.cos(a) * R, y, Math.sin(a) * R);
      const band = 0.5 + 0.5 * Math.sin(y * 2.3 + 2.5 * noise2(a * 6, y * 0.4, seed + 63));
      c.copy(rock).lerp(rock2, band * 0.45).multiplyScalar(1 - 0.18 * v);
      c.lerp(sand, 1 - smooth(0.02, 0.09, v));
      colors.push(c.r, c.g, c.b);
    }
    for (let k = 0; k < NK; k++) for (let s = 0; s < S2; s++) {
      const a = k * S2 + s, b = k * S2 + ((s + 1) % S2), d = a + S2, e = b + S2;
      idx.push(a, b, d, b, e, d);
    }
    mesh(pos, colors, idx, true);
  }
  // Hanging rock spikes.
  const n = Math.max(0, Math.round(num(o.spikes, 8)));
  let r = seed * 9301 + 49297; const rnd = () => ((r = (r * 9301 + 49297) % 233280) / 233280);
  for (let i = 0; i < n; i++) {
    const a = rnd() * TAU, e = 0.25 + rnd() * 0.45, v = 1 - Math.pow(e, 1 / 0.8);
    const y = -0.95 - depth * Math.pow(v, 1.15) * lobe(a), len = depth * (0.2 + rnd() * 0.3), w = len * (0.18 + rnd() * 0.1);
    const g = new THREE.ConeGeometry(w, len, 7, 4, true); g.rotateX(Math.PI);
    const p = g.attributes.position;
    for (let j = 0; j < p.count; j++) { const k = 1 + 0.25 * (hash(j * 3.1 + i * 17 + seed) - 0.5); p.setX(j, p.getX(j) * k); p.setZ(j, p.getZ(j) * k); }
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: rock2.clone().lerp(rock, rnd() * 0.5), roughness: 0.95, flatShading: true }));
    m.position.set(Math.cos(a) * edgeR(a) * e, y - len / 2 + w * 1.5 + 0.6, Math.sin(a) * edgeR(a) * e);
    m.castShadow = true; group.add(m);
  }
  return { root: group, terrain: { size: I.size * 1.2, fn: top } };
}

// A real ground material on a terrain (world_library.py): "surface" names the colour map in
// the game's art, with NAME_normal and NAME_rough beside it; "surfaceSize" is one tile in metres.
function surfaceTexture(name, srgb, repeat, material) {
  const url = studio.image && studio.image(name);
  if (!url) return null;
  const t = new THREE.TextureLoader().load(url, () => { material.needsUpdate = true; });
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8; t.repeat.set(repeat, repeat);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
function applySurface(material, o, size) {
  if (!o.surface) return;
  const repeat = Math.max(1, size / Math.max(0.2, num(o.surfaceSize, 3)));
  const map = surfaceTexture(o.surface, true, repeat, material);
  if (!map) return;
  material.map = map;
  const normal = surfaceTexture(o.surface + '_normal', false, repeat, material);
  if (normal) { material.normalMap = normal; material.normalScale = new THREE.Vector2(1, 1); }
  const rough = surfaceTexture(o.surface + '_rough', false, repeat, material);
  if (rough) { material.roughnessMap = rough; material.roughness = 1; }
  material.needsUpdate = true;
}

function buildTerrain(o) {
  if (o.shape === 'floating') return buildFloatingIsland(o);
  if (o.border) return buildBorderTerrain(o);
  const R = riverInfo(o);
  const size = num(o.size, 60), seg = Math.min(200, Math.max(1, Math.round(size * (R ? 3 : o.shape === 'flat' || !o.shape ? 0.1 : 2))));
  const geo = new THREE.PlaneGeometry(size, size, seg, seg);
  geo.rotateX(-Math.PI / 2);
  const fn = terrainHeightFn(o);
  const pos = geo.attributes.position, colors = [];
  // A surface material brings its own colour: then color/color2 only tint it.
  const c1 = col(o.color, o.surface ? '#ffffff' : '#6fa34d'), c2 = col(o.color2 || o.color, o.surface ? '#ffffff' : '#8a7a5a');
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < pos.count; i++) { const y = fn(pos.getX(i), pos.getZ(i)); pos.setY(i, y); lo = Math.min(lo, y); hi = Math.max(hi, y); }
  const sand = o.sand && o.shape === 'island' ? col(o.sand) : null;
  const bed = R && col(R.bed), baseFn = baseHeightFn(o), blo = R ? Math.min(...Array.from({ length: pos.count }, (_, i) => baseFn(pos.getX(i), pos.getZ(i)))) : lo, bhi = R ? Math.max(...Array.from({ length: pos.count }, (_, i) => baseFn(pos.getX(i), pos.getZ(i)))) : hi;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i), by = R ? baseFn(x, z) : pos.getY(i);
    const t = bhi > blo ? (by - blo) / (bhi - blo) : 0; const c = c1.clone().lerp(c2, t * t);
    if (R) { const k = riverCarve(R, x, z); c.lerp(bed, Math.min(1, k * 2.2)); c.multiplyScalar(1 - 0.25 * k * k); }
    if (sand) { const q = Math.min(1, Math.max(0, (0.28 - by) / 0.3)); c.lerp(sand, q * q * (3 - 2 * q)); }
    colors.push(c.r, c.g, c.b);
  }
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  let tm = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, flatShading: o.shape === 'mountains', map: PS2() ? grit(Math.round(size / 3)) : null });
  if (TOY()) tm = toyMaterial(tm, false);
  applySurface(tm, o, size);
  const mesh = new THREE.Mesh(geo, tm);
  mesh.receiveShadow = true;
  if (R) mesh.add(riverWater(o, R));
  if (o.paving) mesh.add(paving(o, fn));
  return { root: mesh, terrain: { size, fn } };
}

// Cobblestone paving laid over a terrain: terrain.paving = { color, mortar, radius, stone }.
// A round paved disc (on an island it stops short of the beach) hugging the ground.
function cobbleCanvas(stone, mortar) {
  // Natural cobbles: a seamless Voronoi pattern of irregular, rounded stones of mixed sizes,
  // each with its own tint, a cartoony highlight on its upper-left rim and shade on the lower-right.
  const S = 512, c = document.createElement('canvas'); c.width = c.height = S;
  const b = document.createElement('canvas'); b.width = b.height = S;
  let r = 12345; const rnd = () => ((r = (r * 9301 + 49297) % 233280) / 233280);
  const pts = [], G = 7, cell = S / G;
  for (let y = 0; y < G; y++) for (let x = 0; x < G; x++) {
    pts.push({ x: (x + 0.15 + rnd() * 0.7) * cell, y: (y + 0.15 + rnd() * 0.7) * cell,
      tint: stone.clone().offsetHSL((rnd() - 0.5) * 0.04, (rnd() - 0.5) * 0.06, (rnd() - 0.5) * 0.12) });
  }
  const all = [];
  for (const p of pts) for (const dx of [-S, 0, S]) for (const dy of [-S, 0, S]) all.push({ x: p.x + dx, y: p.y + dy, p });
  const img = c.getContext('2d').createImageData(S, S), bimg = b.getContext('2d').createImageData(S, S);
  const grout = 4.5, bevel = 9;
  for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
    let d1 = Infinity, d2 = Infinity, n1 = null, n2 = null;
    for (const q of all) {
      const dx = x - q.x, dy = y - q.y;
      if (Math.abs(dx) > cell * 2 || Math.abs(dy) > cell * 2) continue;
      const d = dx * dx + dy * dy;
      if (d < d1) { d2 = d1; n2 = n1; d1 = d; n1 = q; } else if (d < d2) { d2 = d; n2 = q; }
    }
    // distance to the cell border along the line between the two nearest seeds
    const ax = n2.x - n1.x, ay = n2.y - n1.y, len = Math.hypot(ax, ay);
    const edge = ((x - (n1.x + n2.x) / 2) * -ax + (y - (n1.y + n2.y) / 2) * -ay) / len;
    const k = (y * S + x) * 4;
    // wobble the grout line a little so stones look hand-laid
    const wob = 1.6 * Math.sin(x * 0.09 + y * 0.05) * Math.cos(y * 0.07 - x * 0.03);
    const e = edge - grout - wob;
    if (e <= 0) {
      const m = mortar.clone().offsetHSL(0, 0, (Math.random() - 0.5) * 0.03).convertLinearToSRGB();
      img.data[k] = m.r * 255; img.data[k + 1] = m.g * 255; img.data[k + 2] = m.b * 255; img.data[k + 3] = 255;
      bimg.data[k] = bimg.data[k + 1] = bimg.data[k + 2] = 0; bimg.data[k + 3] = 255;
      continue;
    }
    const t = Math.min(1, e / bevel), dome = Math.sqrt(t * (2 - t));
    // light from the upper left: rim facing it brightens, the opposite rim darkens
    const vx = x - n1.x, vy = y - n1.y, vl = Math.hypot(vx, vy) || 1;
    const facing = -(vx + vy) / (vl * 1.414), rim = 1 - t;
    const col2 = n1.p.tint.clone().offsetHSL(0, 0, rim * facing * 0.16 + (Math.random() - 0.5) * 0.02 - rim * 0.04).convertLinearToSRGB();
    img.data[k] = col2.r * 255; img.data[k + 1] = col2.g * 255; img.data[k + 2] = col2.b * 255; img.data[k + 3] = 255;
    const h = 60 + dome * 195; bimg.data[k] = bimg.data[k + 1] = bimg.data[k + 2] = h; bimg.data[k + 3] = 255;
  }
  c.getContext('2d').putImageData(img, 0, 0); b.getContext('2d').putImageData(bimg, 0, 0);
  const tex = (cv, srgb) => { const t = new THREE.CanvasTexture(cv); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8; if (srgb) t.colorSpace = THREE.SRGBColorSpace; return t; };
  return { map: tex(c, true), bump: tex(b, false) };
}
function paving(o, fn) {
  const P = o.paving === true ? {} : o.paving, size = num(o.size, 60);
  const radius = num(P.radius, o.shape === 'island' ? size / 2 * 0.7 * 0.8 : size / 2), stoneSize = num(P.stone, 0.55);
  // subdivide into rings so the disc follows the ground
  const rings = Math.max(8, Math.round(radius * 2)), seg = 128, verts = [], uvs = [], idx = [];
  for (let i = 0; i <= rings; i++) for (let j = 0; j <= seg; j++) {
    const rr = radius * i / rings, a = j / seg * Math.PI * 2, x = Math.cos(a) * rr, z = Math.sin(a) * rr;
    verts.push(x, fn(x, z) + 0.035, z); uvs.push(x / (stoneSize * 7), z / (stoneSize * 7));
  }
  for (let i = 0; i < rings; i++) for (let j = 0; j < seg; j++) {
    const a = i * (seg + 1) + j, b2 = a + seg + 1;
    idx.push(a, a + 1, b2, a + 1, b2 + 1, b2);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  g.setIndex(idx); g.computeVertexNormals();
  const t = cobbleCanvas(col(P.color, '#3b3452'), col(P.mortar, '#1f1a2c'));
  const m = new THREE.MeshPhysicalMaterial({ map: t.map, bumpMap: t.bump, bumpScale: 2.5, roughness: 0.92, metalness: 0, specularIntensity: 0.25 });
  const mesh = new THREE.Mesh(g, m); mesh.receiveShadow = true;
  // a curb of paler stone around the edge
  const curb = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.12, 8, 160), new THREE.MeshPhysicalMaterial({ color: col(P.curb, '#6d5f93'), roughness: 0.5, clearcoat: TOY() ? 0.6 : 0 }));
  curb.rotation.x = -Math.PI / 2; curb.receiveShadow = true; curb.castShadow = true;
  const cg = curb.geometry, cp = cg.attributes.position;
  for (let i = 0; i < cp.count; i++) { const x = cp.getX(i), y = cp.getY(i); cp.setZ(i, cp.getZ(i) * 0.6 + fn(x, -y) + 0.03); }
  cg.computeVertexNormals();
  const grp = new THREE.Group(); grp.add(mesh, curb);
  return grp;
}

function buildBorderTerrain(o) {
  const inner = num(o.size, 60), B = borderFn(o, terrainHeightFn(o));
  const size = B.size, seg = PS2() ? 110 : 220;
  const geo = new THREE.PlaneGeometry(size, size, seg, seg);
  geo.rotateX(-Math.PI / 2);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setY(i, B.fn(pos.getX(i), pos.getZ(i)));
  geo.computeVertexNormals();
  const nrm = geo.attributes.normal, colors = [], c1 = col(o.color, o.surface ? '#ffffff' : '#6fa34d'), c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i), d = Math.max(Math.abs(x), Math.abs(z)) - inner / 2;
    if (d <= 0) { colors.push(c1.r, c1.g, c1.b); continue; }
    // Snow settles on gentle slopes; steep faces show bare rock.
    const up = nrm.getY(i), speck = noise2(x * 0.9, z * 0.9, 7) * 0.12;
    const snowy = Math.min(1, Math.max(0, (up - 0.62 + speck) / 0.12));
    c.copy(B.rock).lerp(B.snow, snowy);
    const edge = Math.min(1, d / 3); c.lerp(c1, 1 - edge);
    colors.push(c.r, c.g, c.b);
  }
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  const bm = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, map: PS2() ? grit(Math.round(size / 3)) : null });
  applySurface(bm, o, size);
  const mesh = new THREE.Mesh(geo, bm);
  mesh.receiveShadow = true;
  return { root: mesh, terrain: { size, fn: B.fn, inner: inner / 2 } };
}

function buildPrimitive(o) {
  const t = o.type;
  let geo;
  if (t === 'box') geo = new THREE.BoxGeometry(1, 1, 1);
  else if (t === 'sphere') geo = new THREE.SphereGeometry(0.5, segs(32), segs(16));
  else if (t === 'cylinder') geo = new THREE.CylinderGeometry(0.5, 0.5, 1, segs(32));
  else if (t === 'cone') geo = new THREE.ConeGeometry(0.5, 1, segs(32));
  else if (t === 'plane') { geo = new THREE.PlaneGeometry(1, 1); geo.rotateX(-Math.PI / 2); }
  else geo = new THREE.BoxGeometry(1, 1, 1);
  if (t !== 'plane') geo.translate(0, 0.5, 0); // the object's position is its base
  const mesh = new THREE.Mesh(geo, material(o, '#c8c8c8'));
  mesh.castShadow = true; mesh.receiveShadow = true;
  return { root: mesh };
}

function buildWater(o) {
  const size = num(o.size, 60);
  const geo = new THREE.PlaneGeometry(size, size, 1, 1); geo.rotateX(-Math.PI / 2);
  const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: col(o.color, '#2f7fb8'), transparent: true, opacity: num(o.opacity, 0.75), roughness: num(o.roughness, 0.15), metalness: 0.1 }));
  return { root: mesh };
}

function buildLight(o) {
  const light = new THREE.PointLight(col(o.color, '#ffd9a0'), num(o.intensity, 20), num(o.range, 15));
  light.castShadow = false;
  const g = new THREE.Group(); g.add(light); light.position.y = 0.5;
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 8), new THREE.MeshBasicMaterial({ color: col(o.color, '#ffd9a0') }));
  bulb.position.y = 0.5; bulb.userData.editOnly = true; g.add(bulb);
  return { root: g };
}

function buildMarker(color) {
  const g = new THREE.Group();
  const m = new THREE.Mesh(new THREE.ConeGeometry(0.35, 0.9, 16), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.7 }));
  m.rotation.x = Math.PI; m.position.y = 0.45; m.userData.editOnly = true; g.add(m);
  return { root: g };
}

async function buildModel(o) {
  const name = o.type === 'character' ? o.character : o.asset;
  const g = new THREE.Group();
  const gltf = name ? await loadGltf(name) : null;
  if (!gltf) {
    const ph = new THREE.Mesh(new THREE.CapsuleGeometry(0.35, 1.1, 4, 12), material({ color: '#b0b0c0' }));
    ph.position.y = 0.9; ph.castShadow = true; g.add(ph);
    return { root: g, missing: name };
  }
  const inner = SkeletonUtils.clone(gltf.scene);
  // Godot collision helpers (Builder models: wall-colonly, crate-convcolonly) are invisible here too.
  inner.traverse((n) => { if (/-(conv)?colonly$/.test(n.name || '')) n.visible = false; });
  inner.traverse((n) => { if (n.isMesh) { n.castShadow = true; n.receiveShadow = true; n.frustumCulled = !PERF_ON() || !!n.isSkinnedMesh; if (TOY() && n.material) n.material = Array.isArray(n.material) ? n.material.map((m) => toyMaterial(m, true)) : toyMaterial(n.material, true); } });
  const box = new THREE.Box3().setFromObject(inner);
  const size = box.getSize(new THREE.Vector3());
  const want = num(o.height, o.type === 'character' ? (libraryHeight(name) || 1.8) : 0);
  const k = want > 0 && size.y > 0 ? want / size.y : 1;
  inner.scale.setScalar(k);
  inner.position.set(-(box.min.x + size.x / 2) * k, -box.min.y * k, -(box.min.z + size.z / 2) * k);
  g.add(inner);
  let mixer = null; const actions = {};
  if (gltf.animations && gltf.animations.length) {
    mixer = new THREE.AnimationMixer(inner);
    for (const clip of gltf.animations) actions[clip.name] = mixer.clipAction(clip);
  }
  return { root: g, mixer, actions };
}

async function buildObject(o) {
  const t = o.type || 'box';
  let built;
  if (t === 'terrain') built = buildTerrain(o);
  else if (t === 'water') built = buildWater(o);
  else if (t === 'light') built = buildLight(o);
  else if (t === 'spawn') built = buildMarker(0x44aaff);
  else if (t === 'model' || t === 'character') built = await buildModel(o);
  else built = buildPrimitive(o);
  const root = built.root;
  root.userData.id = o.id;
  root.traverse((n) => { n.userData.id = o.id; });
  const s = o.scale;
  if (typeof s === 'number') root.scale.setScalar(s);
  else if (Array.isArray(s)) root.scale.set(num(s[0], 1), num(s[1], 1), num(s[2], 1));
  const r = vec(o.rotation, [0, 0, 0]);
  root.rotation.set(deg(r[0]), deg(r[1]), deg(r[2]));
  if (o.hidden) root.visible = false;
  return Object.assign({ data: o, root, solid: !!(o.solid || (o.behaviors || []).some((b) => b.type === 'solid')) }, built);
}

function place(e) {
  const o = e.data, p = vec(o.position, [0, null, 0]);
  const x = num(p[0], 0), z = num(p[2], 0);
  // A missing height means "standing on the ground".
  const onGround = p[1] === null || p[1] === undefined;
  const y = onGround && o.type !== 'terrain' && o.type !== 'water' ? groundAt(x, z, e) : num(p[1], 0);
  e.root.position.set(x, y, z);
  if (e.terrain) Object.assign(e.terrain, { x, y, z });
  e.root.updateMatrixWorld(true);
  e.box = new THREE.Box3().setFromObject(e.root);
}

let building = 0;
async function rebuild(scene) {
  const token = ++building;
  SCENE = scene || SCENE;
  const objs = Array.isArray(SCENE.objects) ? SCENE.objects : [];
  const built = await Promise.all(objs.map((o) => buildObject(o).catch((err) => { send({ type: 'studio:error', message: 'Could not build ' + (o.name || o.id) + ': ' + err.message }); return null; })));
  if (token !== building) return; // a newer scene arrived meanwhile
  for (const e of live.values()) world.remove(e.root);
  live.clear();
  terrains = [];
  // Terrains first (everything else stands on them), then the rest in order.
  const order = built.filter(Boolean).sort((a, b) => (a.data.type === 'terrain' ? -1 : 0) - (b.data.type === 'terrain' ? -1 : 0));
  for (const e of order) {
    live.set(e.data.id, e);
    world.add(e.root);
    place(e);
    if (e.terrain) terrains.push(e.terrain);
  }
  seas = [...live.values()].filter((e) => e.data.type === 'water')
    .map((e) => ({ x: e.root.position.x, y: e.root.position.y, z: e.root.position.z, half: num(e.data.size, 60) / 2 }));
  applySettings();
  applyMode();
  highlight(selected);
  if (wantCut !== null && MODE === 'edit') for (const e of live.values()) applyCut(e);
  send({ type: 'scene:built', count: live.size, missing: [...live.values()].filter((e) => e.missing).map((e) => e.missing) });
}

function applySettings() {
  const s = SCENE.settings || {};
  const sky = col(s.sky, '#9fc9ea');
  world.background = sky;
  const fog = s.fog;
  world.fog = fog ? new THREE.Fog(col(fog.color, s.sky || '#9fc9ea'), num(fog.near, 20), num(fog.far, 120)) : null;
  const light = s.light || {};
  sun.color = col(light.sun, '#ffffff');
  sun.intensity = num(light.sunIntensity, 2.2);
  const a = deg(num(light.sunAngle, 50)), dir = deg(num(light.sunDirection, 35));
  sun.position.set(Math.cos(dir) * Math.cos(a) * 60, Math.sin(a) * 60, Math.sin(dir) * Math.cos(a) * 60);
  hemi.intensity = num(light.ambient, 1.0);
  hemi.color = col(light.skyLight, '#ffffff');
  hemi.groundColor = col(light.groundLight, '#445544');
  applySkybox(s);
  applyStyle();
}

// A 360° sky picture (world_library.py), named by settings.skybox: the backdrop, and the
// light and reflections the scene gets from its sky ("skyboxLight", default 1).
let skybox = { name: null, tex: null, env: null };
function applySkybox(s) {
  const name = s.skybox || null;
  if (name !== skybox.name) {
    if (skybox.tex) skybox.tex.dispose();
    if (skybox.env) skybox.env.dispose();
    skybox = { name, tex: null, env: null };
    const url = name && studio.image && studio.image(name);
    if (url) {
      const tex = new THREE.TextureLoader().load(url, () => {
        if (skybox.tex !== tex) return;
        const pm = new THREE.PMREMGenerator(renderer);
        skybox.env = pm.fromEquirectangular(tex).texture; pm.dispose();
        applySkybox(SCENE.settings || {});
      });
      tex.mapping = THREE.EquirectangularReflectionMapping; tex.colorSpace = THREE.SRGBColorSpace;
      skybox.tex = tex;
    }
  }
  if (skybox.tex) {
    world.background = skybox.tex;
    world.backgroundIntensity = num(s.skyboxBrightness, 1.1);
    world.environment = skybox.env;
    world.environmentIntensity = num(s.skyboxLight, 1);
  } else {
    world.environment = null;
  }
}

// ---------- edit mode: select and move ----------
// Objects that share a "group" (a house built from many parts) select and move as one.
// selected: the ids selected together (a whole group, or one object).
let selected = null, helper = null;
const groupIds = (id) => {
  const e = live.get(id);
  const g = e && e.data.group;
  return g ? [...live.values()].filter((x) => x.data.group === g).map((x) => x.data.id) : (e ? [id] : []);
};
function highlight(ids) {
  selected = ids && ids.length ? ids : null;
  if (helper) { world.remove(helper); helper = null; }
  if (!selected || MODE !== 'edit') return;
  const box = new THREE.Box3();
  for (const id of selected) { const e = live.get(id); if (e) box.expandByObject(e.root); }
  if (!box.isEmpty()) { helper = new THREE.Box3Helper(box, 0x33c3ff); world.add(helper); }
}
function refreshHelper() { if (selected) highlight(selected); }
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
function pick(ev) {
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const hits = ray.intersectObjects([...live.values()].map((e) => e.root), true).filter((h) => (h.object.visible || h.object.userData.editOnly)
    // With "see inside" on, what is sliced away can't be picked: clicks reach the rooms.
    && !(wantCut !== null && h.point.y > cutPlane.constant + 0.001 && !['terrain', 'water'].includes((live.get(h.object.userData.id) || { data: {} }).data.type)));
  // Things on the terrain win over the terrain itself.
  const hit = hits.find((h) => { const e = live.get(h.object.userData.id); return e && e.data.type !== 'terrain'; }) || hits[0];
  return hit ? { id: hit.object.userData.id, point: hit.point } : null;
}
// Play: tapping an object with "launch" (or any part of its group) opens that studio
// game full screen over this one; the host (the studio, or Worlds) decides how.
function openGame(id) { if (id) send({ type: 'studio:open-game', game: String(id) }); }
const launchFor = (e) => e.data.launch || (e.data.group ? (([...live.values()].find((x) => x.data.group === e.data.group && x.data.launch) || { data: {} }).data.launch) : null);
let playTap = null;
renderer.domElement.addEventListener('pointerdown', (ev) => { playTap = MODE === 'play' ? { x: ev.clientX, y: ev.clientY, t: performance.now() } : null; });
renderer.domElement.addEventListener('pointerup', (ev) => {
  const t = playTap; playTap = null;
  if (MODE !== 'play' || !t || Math.hypot(ev.clientX - t.x, ev.clientY - t.y) > 10 || performance.now() - t.t > 800) return;
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const hit = ray.intersectObjects([...live.values()].filter((e) => e.root.visible).map((e) => e.root), true)
    .map((h) => live.get(h.object.userData.id)).find((e) => e && e.data.type !== 'terrain' && e.data.type !== 'water');
  if (hit) openGame(launchFor(hit));
});
const isOnGround = (o) => !Array.isArray(o.position) || o.position[1] === null || o.position[1] === undefined;
// Every finger or button on the view. A gesture is a tap only while it stays one
// short, still pointer: a pinch or two-finger turn is never a tap, so letting go of
// one doesn't select things or count as a double-tap.
let drag = null, down = null, multi = false;
const pointers = new Map();
function cancelDrag() {
  if (!drag) return;
  for (const { e, start } of drag.parts) e.root.position.copy(start);
  drag = null; orbit.enabled = true; refreshHelper();
}
renderer.domElement.addEventListener('pointerdown', (ev) => {
  if (MODE !== 'edit') return;
  pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY, t: performance.now() });
  // A second finger turns the gesture into camera movement.
  if (pointers.size > 1) { multi = true; down = null; cancelDrag(); return; }
  down = { x: ev.clientX, y: ev.clientY };
  const hit = pick(ev);
  const e = hit && live.get(hit.id);
  if (e && selected && selected.includes(hit.id) && e.data.type !== 'terrain') {
    const parts = selected.map((id) => live.get(id)).filter(Boolean).map((x) => ({ e: x, start: x.root.position.clone() }));
    drag = { parts, plane: new THREE.Plane(new THREE.Vector3(0, 1, 0), -hit.point.y), from: hit.point.clone(), moved: false, pointer: ev.pointerId };
    orbit.enabled = false;
    renderer.domElement.setPointerCapture(ev.pointerId);
  }
});
renderer.domElement.addEventListener('pointermove', (ev) => {
  if (!drag || ev.pointerId !== drag.pointer) return;
  const r = renderer.domElement.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const p = new THREE.Vector3();
  if (!ray.ray.intersectPlane(drag.plane, p)) return;
  const dx = p.x - drag.from.x, dz = p.z - drag.from.z;
  for (const { e, start } of drag.parts) {
    const x = start.x + dx, z = start.z + dz;
    e.root.position.set(x, isOnGround(e.data) ? groundAt(x, z, e) : start.y, z);
  }
  drag.moved = true;
  refreshHelper();
});
// True when this pointer-up ends a single short, still press (not part of a pinch).
function endPointer(ev) {
  const s = pointers.get(ev.pointerId);
  pointers.delete(ev.pointerId);
  const tap = !multi && !!s && performance.now() - s.t < 400 && Math.hypot(ev.clientX - s.x, ev.clientY - s.y) < 8;
  if (pointers.size === 0) multi = false;
  return tap;
}
renderer.domElement.addEventListener('pointercancel', (ev) => { endPointer(ev); cancelDrag(); down = null; });
let lastTap = null;
renderer.domElement.addEventListener('pointerup', (ev) => {
  if (MODE !== 'edit') return;
  const tap = endPointer(ev);
  if (drag && ev.pointerId === drag.pointer) {
    orbit.enabled = true;
    if (drag.moved) {
      const moves = drag.parts.map(({ e }) => {
        const p = e.root.position, o = e.data;
        o.position = [+p.x.toFixed(2), isOnGround(o) ? null : +p.y.toFixed(2), +p.z.toFixed(2)];
        place(e);
        return { id: o.id, position: o.position };
      });
      send({ type: 'scene:moved', moves });
    }
    drag = null;
    return;
  }
  if (down && (ev.pointerType === 'mouse' ? Math.hypot(ev.clientX - down.x, ev.clientY - down.y) < 6 : tap)) {
    const hit = pick(ev);
    const e = hit && live.get(hit.id);
    highlight(hit ? groupIds(hit.id) : null);
    send({ type: 'scene:pick', id: hit ? hit.id : null, group: e && e.data.group ? e.data.group : null });
  }
  down = null;
  // Touch double-tap: two taps close together in time and place fly the camera there.
  if (ev.pointerType !== 'mouse' && tap) {
    const now = performance.now();
    if (lastTap && now - lastTap.t < 300 && Math.hypot(ev.clientX - lastTap.x, ev.clientY - lastTap.y) < 30) { lastTap = null; flyTo(ev); }
    else lastTap = { t: now, x: ev.clientX, y: ev.clientY };
  } else if (ev.pointerType !== 'mouse') lastTap = null;
});

// ---------- edit mode: see inside ----------
// Slice the world above a height (a dollhouse with the roof off) so the insides of
// buildings show: every object except the ground and water gets a clipping plane.
// The height counts from the ground where the camera looks when the cut starts.
renderer.localClippingEnabled = true;
const cutPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0); // keeps y <= constant
let cutBase = null, wantCut = null;
function applyCut(e) {
  const on = wantCut !== null && e.data.type !== 'terrain' && e.data.type !== 'water';
  e.root.traverse((n) => {
    if (!n.isMesh) return;
    if (on && !n.userData.uncut) {
      n.userData.uncut = n.material;
      // Clones share materials: give this object its own, seen from both sides (inner walls).
      const own = (Array.isArray(n.material) ? n.material : [n.material]).map((mt) => { const c = mt.clone(); c.clippingPlanes = [cutPlane]; c.side = THREE.DoubleSide; return c; });
      n.material = own.length === 1 ? own[0] : own;
    } else if (!on && n.userData.uncut) {
      n.material = n.userData.uncut; delete n.userData.uncut;
    }
  });
}
function cutaway(height) {
  if (typeof height === 'number') {
    if (cutBase === null) cutBase = groundAt(orbit.target.x, orbit.target.z);
    wantCut = height;
    cutPlane.constant = cutBase + height;
  } else { wantCut = null; cutBase = null; }
  for (const e of live.values()) applyCut(e);
}

// Double-tap (or double-click) a spot to fly the camera close to it: into rooms,
// up to a doorway, next to a small object.
// Touch double-taps are detected in the pointer handlers above; the browser's own
// dblclick is used only for a mouse.
let lastPointerType = 'mouse';
let flying = 0;
renderer.domElement.addEventListener('pointerdown', (ev) => { lastPointerType = ev.pointerType; flying++; }, true);
renderer.domElement.addEventListener('dblclick', (ev) => {
  if (MODE === 'edit' && lastPointerType === 'mouse') flyTo(ev);
});
function flyTo(ev) {
  const hit = pick(ev);
  if (!hit) return;
  const to = hit.point.clone();
  const dir = camera.position.clone().sub(orbit.target).normalize();
  const from = { t: orbit.target.clone(), c: camera.position.clone() };
  const dest = { t: to, c: to.clone().add(dir.multiplyScalar(3.5)) };
  const start = performance.now(), flight = ++flying;
  (function step(now) {
    if (flight !== flying) return; // a new touch took over the camera
    const k = Math.min(1, (now - start) / 450), e = k * k * (3 - 2 * k);
    orbit.target.lerpVectors(from.t, dest.t, e); camera.position.lerpVectors(from.c, dest.c, e);
    if (k < 1) requestAnimationFrame(step);
  })(start);
}

// ---------- play mode ----------
const hud = document.createElement('div');
hud.style.cssText = 'position:fixed;left:0;right:0;bottom:0;padding:0 16px max(18px, env(safe-area-inset-bottom));display:flex;justify-content:center;gap:24px;align-items:flex-end;pointer-events:none;font:700 18px system-ui,sans-serif;color:#fff;text-shadow:0 2px 6px rgba(0,0,0,.6);z-index:5';
const hudLeft = document.createElement('div'), hudRight = document.createElement('div');
hud.append(hudLeft, hudRight);
const banner = document.createElement('div');
banner.style.cssText = 'position:fixed;left:50%;top:38%;transform:translate(-50%,-50%);padding:14px 22px;border-radius:14px;background:rgba(0,0,0,.55);color:#fff;font:700 22px system-ui,sans-serif;text-align:center;pointer-events:none;opacity:0;transition:opacity .3s;z-index:6;max-width:80vw';
document.body.append(hud, banner);
let bannerTimer = 0;
function message(text, seconds) { banner.textContent = text; banner.style.opacity = '1'; clearTimeout(bannerTimer); if (seconds !== 0) bannerTimer = setTimeout(() => { banner.style.opacity = '0'; }, (seconds || 2.5) * 1000); }


// --- Cutscenes: api.cutscene(async (c) => { ... }, { once: 'intro' }) ---------------------------
// Steps can be awaited, so a cutscene reads top to bottom. While one plays the player can't move,
// chasers wait and nothing hurts; the Skip button (or button B) finishes it at once.
const cutUi = (() => {
  const bar = 'position:fixed;left:0;right:0;height:12vh;background:#000;z-index:50;transition:transform .4s ease;pointer-events:none;';
  const top = document.createElement('div'), bottom = document.createElement('div'), sub = document.createElement('div'), skip = document.createElement('button');
  top.style.cssText = bar + 'top:0;transform:translateY(-101%)';
  bottom.style.cssText = bar + 'bottom:0;transform:translateY(101%)';
  sub.style.cssText = 'position:fixed;left:6%;right:6%;bottom:calc(12vh + 16px);z-index:51;text-align:center;color:#fff;font:600 clamp(16px,3.6vw,24px)/1.35 system-ui,sans-serif;text-shadow:0 2px 6px #000,0 0 2px #000;opacity:0;transition:opacity .25s;pointer-events:none';
  skip.type = 'button'; skip.textContent = 'Skip »';
  skip.style.cssText = 'position:fixed;top:calc(env(safe-area-inset-top) + 10px);right:12px;z-index:52;min-height:44px;padding:0 18px;border-radius:22px;border:1px solid rgba(255,255,255,.4);background:rgba(0,0,0,.4);color:#fff;font:600 15px system-ui,sans-serif;cursor:pointer;display:none';
  document.body.append(top, bottom, sub, skip);
  return { top, bottom, sub, skip };
})();
const cut = { active: false, skipping: false, tweens: [], bWas: false };
let cutQueue = Promise.resolve();
const easeInOut = (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);
function cutTween(seconds, apply) {
  return new Promise((resolve) => {
    if (cut.skipping || !(seconds > 0)) { apply(1); resolve(); return; }
    cut.tweens.push({ t: 0, d: seconds, apply, resolve });
  });
}
function updateCutscene(dt) {
  if (!cut.active) return;
  const b = !!(studio.input && studio.input.b);
  if (b && !cut.bWas) skipCutscene();
  cut.bWas = b;
  for (const tw of cut.tweens.slice()) {
    tw.t += dt; const k = Math.min(1, tw.t / tw.d); tw.apply(k);
    if (k >= 1) { cut.tweens.splice(cut.tweens.indexOf(tw), 1); tw.resolve(); }
  }
}
function skipCutscene() {
  if (!cut.active || cut.skipping) return;
  cut.skipping = true;
  for (const tw of cut.tweens.splice(0)) { tw.apply(1); tw.resolve(); }
  if (studio.stopSpeaking) studio.stopSpeaking();
  cutUi.sub.style.opacity = '0';
}
cutUi.skip.addEventListener('pointerdown', (e) => { e.stopPropagation(); e.preventDefault(); skipCutscene(); });
function cutEntry(key) {
  if (!key) return null;
  const id = typeof key === 'object' && !Array.isArray(key) && !key.isVector3 ? key.id : key;
  for (const e of live.values()) if (e.data.id === id || e.data.name === id) return e;
  return null;
}
// A place: [x, y, z] (y null = 1.6 m above the ground there), a THREE.Vector3, or an object (its chest).
function cutPoint(t, chest) {
  if (Array.isArray(t)) { const y = t[1] == null ? groundAt(t[0], t[2]) + 1.6 : t[1]; return new THREE.Vector3(t[0], y, t[2]); }
  if (t && t.isVector3) return t.clone();
  const e = cutEntry(t);
  if (e) { const h = new THREE.Box3().setFromObject(e.root).getSize(new THREE.Vector3()).y || 1.7; return e.root.position.clone().add(new THREE.Vector3(0, chest === false ? 0 : h * 0.7, 0)); }
  return orbit.target.clone();
}
function cutFace(e, target) {
  const d = cutPoint(target, false).sub(e.root.position); d.y = 0;
  if (d.lengthSq() < 1e-4) return;
  e.root.rotation.y = Math.atan2(d.x, d.z);
  if (play && e === play.player) e.yaw = e.root.rotation.y;
}
function cutsceneSteps() {
  return {
    // Glide the camera to a place, looking at a place or an object (default 1.5 s).
    camera: (pos, lookAt, seconds) => {
      const toPos = cutPoint(pos), toLook = cutPoint(lookAt);
      const fromPos = camera.position.clone(), fromLook = orbit.target.clone();
      return cutTween(seconds == null ? 1.5 : seconds, (k) => { const e = easeInOut(k); camera.position.lerpVectors(fromPos, toPos, e); orbit.target.lerpVectors(fromLook, toLook, e); });
    },
    // Cut straight to a shot.
    cut: (pos, lookAt) => { camera.position.copy(cutPoint(pos)); orbit.target.copy(cutPoint(lookAt)); return Promise.resolve(); },
    // Walk a character to a place or another object (its walk clip, then idle).
    walk: (who, to, seconds) => {
      const e = cutEntry(who); if (!e) return Promise.resolve();
      const from = e.root.position.clone(), dest = cutPoint(to, false);
      if (!Array.isArray(to) && cutEntry(to)) { const d = dest.clone().sub(from); d.y = 0; const len = d.length(); if (len > 1.2) dest.copy(from).addScaledVector(d.normalize(), len - 1.1); else dest.copy(from); }
      cutFace(e, dest);
      fade(e, 'walk');
      return cutTween(seconds == null ? 2 : seconds, (k) => {
        e.root.position.lerpVectors(from, dest, k);
        e.root.position.y = groundAt(e.root.position.x, e.root.position.z, e);
      }).then(() => fade(e, 'idle'));
    },
    face: (who, target) => { const e = cutEntry(who); if (e) cutFace(e, target); return Promise.resolve(); },
    // Play one of its moves once and wait for it (then back to idle); { loop: true } keeps it going.
    play: (who, clip, opts) => {
      const e = cutEntry(who); opts = opts || {};
      if (!e || !e.actions || !e.actions[clip]) return Promise.resolve();
      const a = e.actions[clip];
      if (opts.loop) { a.setLoop(THREE.LoopRepeat, Infinity); fade(e, clip); return Promise.resolve(); }
      a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = true;
      fade(e, clip);
      return cutTween(a.getClip().duration / (a.timeScale || 1), () => {}).then(() => {
        a.setLoop(THREE.LoopRepeat, Infinity); a.clampWhenFinished = false;
        fade(e, opts.then || 'idle');
      });
    },
    // A subtitle line; { who: 'Name' } prefixes the speaker, { voice: 'af_heart' } speaks it (a
    // voice line made with voice_lines.py, else the Möbius voice). Waits until it's said or read.
    say: (text, opts) => {
      opts = opts || {};
      if (cut.skipping) return Promise.resolve();
      cutUi.sub.textContent = (opts.who ? opts.who + ': ' : '') + text;
      cutUi.sub.style.opacity = '1';
      const reading = Math.min(6, Math.max(1.4, String(text).length * 0.06));
      const started = performance.now();
      const spoken = opts.voice && studio.say ? Promise.resolve(studio.say(String(text), { voice: opts.voice })).catch(() => {}) : Promise.resolve();
      const skipped = new Promise((r) => { const t = setInterval(() => { if (cut.skipping || !cut.active) { clearInterval(t); r(); } }, 100); spoken.then(() => clearInterval(t)); });
      return Promise.race([spoken, skipped])
        .then(() => cutTween(Math.max(0, reading - (performance.now() - started) / 1000), () => {}))
        .then(() => { cutUi.sub.style.opacity = '0'; });
    },
    wait: (seconds) => cutTween(seconds, () => {}),
    message,
    get skipping() { return cut.skipping; },
  };
}
function runCutscene(fn, opts) {
  opts = opts || {};
  const key = opts.once ? 'cutscene:' + opts.once : null;
  const run = async () => {
    if (!play || play.over || MODE !== 'play') return false;
    if (key && studio.load && studio.load(key)) return false;
    const P = play.player;
    const offset = camera.position.clone().sub(orbit.target);
    const savedTarget = orbit.target.clone(), savedOrbit = orbit.enabled;
    cut.active = true; cut.skipping = false; cut.bWas = !!(studio.input && studio.input.b);
    orbit.enabled = false;
    hudLeft.style.visibility = 'hidden'; hudRight.style.visibility = 'hidden';
    document.querySelectorAll('[data-studio-controls]').forEach((n) => { n.style.visibility = 'hidden'; });
    cutUi.top.style.transform = 'translateY(0)'; cutUi.bottom.style.transform = 'translateY(0)';
    cutUi.skip.style.display = 'block';
    if (P) fade(P, 'idle');
    try { await fn(cutsceneSteps()); } catch (err) { send({ type: 'studio:error', message: 'Cutscene: ' + err.message }); }
    cut.skipping = false;
    cutUi.sub.style.opacity = '0'; cutUi.skip.style.display = 'none';
    cutUi.top.style.transform = 'translateY(-101%)'; cutUi.bottom.style.transform = 'translateY(101%)';
    // Back to the game's view: behind the player again (or where the camera was).
    const look = P ? P.root.position.clone().add(new THREE.Vector3(0, 1.5, 0)) : savedTarget;
    const fromPos = camera.position.clone(), fromLook = orbit.target.clone(), toPos = look.clone().add(offset);
    await cutTween(0.6, (k) => { const e = easeInOut(k); camera.position.lerpVectors(fromPos, toPos, e); orbit.target.lerpVectors(fromLook, look, e); });
    orbit.enabled = savedOrbit;
    hudLeft.style.visibility = ''; hudRight.style.visibility = '';
    document.querySelectorAll('[data-studio-controls]').forEach((n) => { n.style.visibility = ''; });
    cut.active = false;
    if (key && studio.save) studio.save(key, true);
    return true;
  };
  cutQueue = cutQueue.then(run, run);
  return cutQueue;
}

let play = null; // per-play state
const updaters = [];
function behaviorsOf(e, type) { return (e.data.behaviors || []).filter((b) => b.type === type); }
function fade(e, name, t) {
  if (!e.mixer) return;
  const next = e.actions[name] || e.actions.idle;
  if (!next || e.current === next) return;
  next.reset().fadeIn(t || 0.2).play();
  if (e.current) e.current.fadeOut(t || 0.2);
  e.current = next;
}

function startPlay() {
  play = { score: 0, health: 100, maxHealth: 100, over: false, time: 0, collected: 0, collectibles: 0, hurtCooldown: 0, handlers: { update: [], collect: [], start: [], late: [] } };
  const players = [...live.values()].filter((e) => behaviorsOf(e, 'player').length);
  play.player = players[0] || null;
  if (play.player) {
    const b = behaviorsOf(play.player, 'player')[0];
    play.player.vel = new THREE.Vector3();
    play.player.speed = num(b.speed, 5); play.player.jump = num(b.jump, 6);
    play.player.yaw = play.player.root.rotation.y;
    fade(play.player, 'idle');
    studio.controls && studio.controls({ stick: true, buttons: ['Jump'] });
  }
  for (const e of live.values()) {
    e.home = e.root.position.clone();
    if (behaviorsOf(e, 'collectible').length) play.collectibles++;
    if (e !== play.player && e.mixer) fade(e, e.data.animation || 'idle');
  }
  const api = makeApi();
  for (const s of SCENE.scripts || []) {
    try { new Function('api', 'THREE', s.code)(api, THREE); } catch (err) { send({ type: 'studio:error', message: 'Script "' + s.name + '": ' + err.message }); }
  }
  for (const e of live.values()) for (const b of behaviorsOf(e, 'script')) {
    try { new Function('api', 'self', 'THREE', b.code)(api, handle(e), THREE); } catch (err) { send({ type: 'studio:error', message: 'Script on ' + (e.data.name || e.data.id) + ': ' + err.message }); }
  }
  // Background music: settings.music names a sound file (the game's own or the Assets tab).
  const tune = (SCENE.settings || {}).music;
  if (tune && studio.music) studio.music(tune, { volume: num((SCENE.settings || {}).musicVolume, 0.5) });
  else if (studio.stopMusic) studio.stopMusic();
  play.handlers.start.forEach((f) => f());
  drawHud();
}

function handle(e) {
  return { id: e.data.id, name: e.data.name, data: e.data, object: e.root, get position() { return e.root.position; },
    play: (clip) => fade(e, clip), hide: () => { e.root.visible = false; e.gone = true; }, show: () => { e.root.visible = true; e.gone = false; } };
}
function makeApi() {
  const find = (key) => { for (const e of live.values()) if (e.data.id === key || e.data.name === key) return handle(e); return null; };
  const api = {
    get: find,
    all: (type) => [...live.values()].filter((e) => !type || e.data.type === type || behaviorsOf(e, type).length).map(handle),
    get player() { return play.player ? handle(play.player) : null; },
    get score() { return play.score; }, set score(v) { play.score = v; drawHud(); },
    get health() { return play.health; }, set health(v) { play.health = Math.max(0, Math.min(play.maxHealth, v)); drawHud(); if (play.health <= 0) api.lose('You were defeated'); },
    get time() { return play.time; },
    input: studio.input,
    message, sound: (p, o) => studio.sound && studio.sound(p, null, o),
    music: (name, o) => studio.music && studio.music(name, o), stopMusic: (f) => studio.stopMusic && studio.stopMusic(f),
    onUpdate: (f) => play.handlers.update.push(f), onLateUpdate: (f) => play.handlers.late.push(f),
    buttons: (labels) => studio.controls && studio.controls({ stick: true, buttons: labels }), onCollect: (f) => play.handlers.collect.push(f), onStart: (f) => play.handlers.start.push(f),
    openGame,
    cutscene: runCutscene,
    get inCutscene() { return cut.active; },
    win: (t) => endGame(t || 'You win!'), lose: (t) => endGame(t || 'Game over'),
    world, camera, THREE,
  };
  return api;
}
function endGame(text) { if (!play || play.over) return; play.over = true; if (play.player && play.health > 0) fade(play.player, 'idle'); message(text + '  —  tap to play again', 0); addEventListener('pointerdown', () => { if (MODE === 'play') { banner.style.opacity = '0'; rebuild().then(() => {}); } }, { once: true }); }
function drawHud() {
  if (!play) { hudLeft.textContent = ''; hudRight.textContent = ''; return; }
  const parts = [];
  if (play.collectibles) parts.push('Found ' + play.collected + ' / ' + play.collectibles);
  if (play.score && play.score !== play.collected) parts.push('Score ' + play.score);
  hudLeft.textContent = parts.join('   ');
  const hurts = [...live.values()].some((e) => behaviorsOf(e, 'hurts').length);
  hudRight.textContent = hurts ? '♥ ' + Math.round(play.health) : '';
}

const tmp = new THREE.Vector3();
function updatePlay(dt) {
  if (!play || play.over) return;
  play.time += dt;
  const P = play.player;
  if (P) {
    const inp = cut.active ? { x: 0, y: 0, a: false, b: false } : (studio.input || { x: 0, y: 0 });
    // Camera-relative movement.
    const fwd = new THREE.Vector3(); camera.getWorldDirection(fwd); fwd.y = 0; fwd.normalize();
    const right = new THREE.Vector3().crossVectors(fwd, new THREE.Vector3(0, 1, 0));
    const move = new THREE.Vector3().addScaledVector(right, inp.x).addScaledVector(fwd, -inp.y);
    const mag = Math.min(1, move.length());
    if (mag > 0.05) { move.normalize(); P.yaw = Math.atan2(move.x, move.z); }
    const pos = P.root.position;
    const ground = groundAt(pos.x, pos.z, P, pos.y + STEP);
    const onGround = pos.y <= ground + 0.05;
    if (onGround && inp.a && !P.jumped) { P.vel.y = P.jump; P.jumped = true; }
    if (!inp.a) P.jumped = false;
    P.vel.y -= 18 * dt;
    const speed = P.speed * (mag > 0.85 ? 1.6 : 1);
    let nx = pos.x + move.x * speed * mag * dt; let nz = pos.z + move.z * speed * mag * dt;
    // Solid objects block the way unless you can step onto them.
    let blocked = false;
    for (const e of live.values()) {
      if (!e.solid || e === P || !e.box) continue;
      const b = e.box;
      if (nx > b.min.x - 0.3 && nx < b.max.x + 0.3 && nz > b.min.z - 0.3 && nz < b.max.z + 0.3 && pos.y < b.max.y - 0.35) blocked = true;
    }
    for (const t of terrains) if (t.inner && Math.abs(pos.x - t.x) <= t.size / 2 && Math.abs(pos.z - t.z) <= t.size / 2
      && (Math.abs(nx - t.x) > t.inner - 0.4 || Math.abs(nz - t.z) > t.inner - 0.4)) blocked = true; // the mountain border fences you in
    // The sea is not walkable: stop at the shore or the side of a bridge (from the water you can always get out).
    // It looks a body's width (0.3) ahead, so the player stops before the edge, not half over it.
    const step = pos.y + STEP, ax = move.x * 0.3, az = move.z * 0.3;
    if (!blocked && mag > 0.05 && wetAt(nx + ax, nz + az, P, step) && !wetAt(pos.x, pos.z, P, step)) {
      if (Math.abs(move.x) > 0.1 && !wetAt(nx + ax, pos.z, P, step)) nz = pos.z; // slide along the shore instead of sticking
      else if (Math.abs(move.z) > 0.1 && !wetAt(pos.x, nz + az, P, step)) nx = pos.x;
      else blocked = true;
    }
    if (!blocked) { pos.x = nx; pos.z = nz; }
    pos.y += P.vel.y * dt;
    const g2 = groundAt(pos.x, pos.z, P, pos.y + STEP);
    if (pos.y <= g2) { pos.y = g2; P.vel.y = 0; }
    if (pos.y < -30) { pos.copy(P.home); P.vel.set(0, 0, 0); }
    let r = P.yaw - P.root.rotation.y; r = Math.atan2(Math.sin(r), Math.cos(r));
    P.root.rotation.y += r * Math.min(1, dt * 12);
    if (!cut.active) fade(P, pos.y > g2 + 0.3 ? 'jump' : mag < 0.05 ? 'idle' : mag > 0.85 && P.actions && P.actions.run ? 'run' : 'walk');
    // Third-person camera: it travels with the player and, while they walk, swings
    // gently round behind them. Dragging the view turns it by hand; following resumes
    // shortly after. Walking towards the camera doesn't spin it round.
    const target = pos.clone().add(new THREE.Vector3(0, 1.5, 0));
    if (!cut.active) {
    const before = orbit.target.clone();
    orbit.target.lerp(target, Math.min(1, dt * 8));
    camera.position.add(orbit.target.clone().sub(before));
    if (mag > 0.05 && !viewDragging && performance.now() - viewDraggedAt > 1200) {
      const off = camera.position.clone().sub(orbit.target);
      let turn = (P.yaw + Math.PI) - Math.atan2(off.x, off.z); turn = Math.atan2(Math.sin(turn), Math.cos(turn));
      if (Math.abs(turn) < Math.PI * 0.75) {
        off.applyAxisAngle(new THREE.Vector3(0, 1, 0), turn * Math.min(1, dt * 1.2 * mag));
        camera.position.copy(orbit.target).add(off);
      }
    }
    } // (the cutscene drives the camera while one plays)
  }
  for (const e of live.values()) {
    if (e.gone) continue;
    for (const b of e.data.behaviors || []) {
      if (b.type === 'spin') e.root.rotation.y += deg(num(b.speed, 90)) * dt;
      else if (b.type === 'bob') e.root.position.y = e.home.y + Math.sin(play.time * num(b.speed, 2)) * num(b.height, 0.3);
      else if (b.type === 'collectible' && P && tmp.subVectors(e.root.position, P.root.position).length() < num(b.radius, 1.2)) {
        e.root.visible = false; e.gone = true; play.score += num(b.points, 1); play.collected++;
        studio.sound && studio.sound([, , 1200, , .02, .12, 1, 1.6]);
        play.handlers.collect.forEach((f) => f(handle(e)));
        if (b.message) message(b.message);
        drawHud();
        if (play.collectibles && play.collected >= play.collectibles && !(SCENE.scripts || []).length) endGame(SCENE.winMessage || 'You found them all!');
      } else if (b.type === 'chase' && P && !cut.active) {
        const d = tmp.subVectors(P.root.position, e.root.position); d.y = 0;
        const dist = d.length();
        if (dist < num(b.range, 12) && dist > 0.9) {
          d.normalize();
          e.root.position.x += d.x * num(b.speed, 2.5) * dt; e.root.position.z += d.z * num(b.speed, 2.5) * dt;
          e.root.position.y = groundAt(e.root.position.x, e.root.position.z, e);
          e.root.rotation.y = Math.atan2(d.x, d.z);
          fade(e, 'walk');
        } else fade(e, e.data.animation || 'idle');
      } else if (b.type === 'trigger' && P) {
        const inside = tmp.subVectors(e.root.position, P.root.position).length() < num(b.radius, 2);
        if (inside && !e.triggered && b.message) message(b.message);
        e.triggered = inside;
      }
      if (b.type === 'hurts' && P && !cut.active && play.hurtCooldown <= 0 && tmp.subVectors(e.root.position, P.root.position).length() < num(b.radius, 1.1)) {
        play.health -= num(b.damage, 10); play.hurtCooldown = 0.8; fade(P, 'hurt');
        drawHud();
        if (play.health <= 0) { fade(P, 'die'); endGame('You were defeated'); }
      }
    }
    if (e.solid) e.box.setFromObject(e.root);
  }
  play.hurtCooldown -= dt;
  play.handlers.update.forEach((f) => { try { f(dt); } catch (err) { send({ type: 'studio:error', message: 'Script: ' + err.message }); } });
}

// ---------- modes ----------
function applyMode() {
  const edit = MODE === 'edit';
  pointers.clear(); multi = false; down = null; lastTap = null; cancelDrag();
  if (!edit && wantCut !== null) cutaway(null);
  grid.visible = edit;
  for (const e of live.values()) e.root.traverse((n) => { if (n.userData.editOnly) n.visible = edit; });
  if (edit) {
    play = null; drawHud(); banner.style.opacity = '0'; studio.stopMusic && studio.stopMusic(0.3);
    for (const e of live.values()) { place(e); e.gone = false; e.root.visible = !e.data.hidden; if (e.mixer) fade(e, e.data.animation || 'idle'); }
    document.querySelectorAll('[data-studio-controls]').forEach((layer) => layer.remove());
  } else {
    highlight(null);
    startPlay();
    if (play.player) {
      const p = play.player.root.position;
      camera.position.set(p.x, p.y + 3.2, p.z + 6);
      orbit.target.set(p.x, p.y + 1.5, p.z);
    }
  }
  orbit.enablePan = edit;
}

// First view: frame the scene.
function frameAll() {
  // Frame the things placed in the world; the ground only when there is nothing else.
  const box = new THREE.Box3();
  // backdrop objects (a moon, a star dome, far mountains) are scenery, not what the camera frames
  const things = [...live.values()].filter((e) => !['light', 'terrain', 'water'].includes(e.data.type) && !e.data.backdrop);
  for (const e of (things.length ? things : [...live.values()].filter((e) => e.data.type !== 'light' && !e.data.backdrop))) box.expandByObject(e.root);
  if (box.isEmpty()) { camera.position.set(12, 10, 14); orbit.target.set(0, 0, 0); return; }
  const c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
  const r = Math.max(things.length ? 5 : 6, Math.min(80, Math.max(s.x, s.z, s.y) * (things.length ? 1.1 : 0.8)));
  camera.position.set(c.x + r * 0.8, c.y + r * 0.7, c.z + r);
  orbit.target.copy(c);
}

addEventListener('message', (ev) => {
  const m = ev.data || {};
  if (m.type === 'scene:set') { rebuild(m.scene); }
  else if (m.type === 'scene:mode') { MODE = m.mode === 'edit' ? 'edit' : 'play'; applyMode(); }
  else if (m.type === 'scene:select') { highlight(m.ids || (m.id ? [m.id] : null)); }
  else if (m.type === 'scene:frame') { frameAll(); }
  else if (m.type === 'scene:cut') { cutaway(m.height); }
  else if (m.type === 'scene:where') { send({ type: 'scene:here', ask: m.ask, target: [+orbit.target.x.toFixed(2), +orbit.target.z.toFixed(2)] }); }
});

// Props too far away to be more than a few pixels are not drawn at all. Terrain, water, lights,
// characters, anything that moves with a mixer and the player always are; fog shortens the range.
function farCull() {
  const on = MODE === 'play' && PERF_ON();
  const cam = camera.position, fogFar = world.fog ? world.fog.far * 1.1 : Infinity;
  for (const e of live.values()) {
    if (!on) { if (e.farHidden) setFar(e, false); continue; }
    const t = e.data.type;
    if (t === 'terrain' || t === 'water' || t === 'light' || t === 'character' || t === 'spawn' || e.mixer || e.gone || e.data.hidden || e.data.backdrop) continue;
    if ((e.data.behaviors || []).some((b) => b.type === 'player')) continue;
    if (e.radius === undefined) e.radius = e.box && !e.box.isEmpty() ? e.box.getSize(new THREE.Vector3()).length() / 2 : Infinity;
    const far = e.root.position.distanceTo(cam) > Math.min(Math.max(50, e.radius * 400), fogFar + e.radius);
    if (far !== !!e.farHidden) setFar(e, far);
  }
}
function setFar(e, hidden) {
  e.farHidden = hidden;
  e.root.traverse((n) => { if (n.isMesh && !n.userData.editOnly) n.visible = !hidden; });
}

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const raw = clock.getDelta();
  const dt = Math.min(0.05, raw);
  perf.slow = perf.slow * 0.95 + Math.min(raw, 0.1) * 0.05;
  perf.frame++;
  if (PERF_ON() && MODE === 'play') {
    // Slower than about 30 fps for a good while (after startup settles): render fewer pixels, down to 60 percent.
    if (perf.frame > 120 && perf.frame % 90 === 0 && perf.slow > 0.034 && perf.scale > 0.6) { perf.scale = Math.max(0.6, perf.scale * 0.85); applyPixelRatio(); }
    if (perf.frame % 12 === 0) farCull();
  } else if (perf.frame % 12 === 0) farCull();
  if (MODE === 'play') { updatePlay(dt); updateCutscene(dt); }
  for (const e of live.values()) { if (e.mixer) e.mixer.update(dt); if (e.data.type === 'terrain') e.root.traverse((n) => n.userData.flow && n.userData.flow(dt)); }
  // Late scripts run after animation, so they can pose bones on top of it (a weapon swing).
  if (MODE === 'play' && play && !play.over) play.handlers.late.forEach((f) => { try { f(dt); } catch (err) { send({ type: 'studio:error', message: 'Script: ' + err.message }); } });
  // (the selection outline is a Box3Helper: it follows its box without updates)
  orbit.update();
  renderer.render(world, camera);
});

// What the renderer is doing right now, for the playtest and for measuring.
window.__sceneStats = () => {
  const i = renderer.info.render;
  return { calls: i.calls, triangles: i.triangles, pixelRatio: +renderer.getPixelRatio().toFixed(2), objects: live.size, culledFar: [...live.values()].filter((e) => e.farHidden).length, frameMs: +(perf.slow * 1000).toFixed(1) };
};

// Edit mode (and a scene without a player) starts framed on everything; Play starts behind the player.
rebuild(SCENE).then(async () => {
  if (MODE === 'edit' || !play || !play.player) frameAll();
  // Compile every shader now, behind the loading screen, so nothing stalls the first time it comes into view.
  if (PERF_ON()) { try { await renderer.compileAsync(world, camera); } catch (err) { /* compiling early is only a nicety */ } }
  send({ type: 'scene:ready' });
});
`

function scriptSafe(text) {
  return String(text).replace(/</g, '\\u003c')
}

// The game's HTML: the scene as data and the runtime that builds it. mode 'edit'
// starts in Edit mode (the studio); games and playtests start in Play mode.
export function sceneDocument(scene, mode = 'play') {
  const name = String(scene?.name || 'Game').replace(/[<&]/g, '')
  return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    + '<title>' + name + '</title><style>html,body{margin:0;height:100%;overflow:hidden;background:#0b1020}</style></head><body>'
    + '<script type="application/json" id="scene">' + scriptSafe(JSON.stringify(scene || {})) + '</script>'
    + (mode === 'edit' ? '<script>window.__sceneMode = "edit"</script>' : '')
    + '<script type="module">' + SCENE_RUNTIME + '</script></body></html>'
}

export const EMPTY_SCENE = { version: 1, name: 'Untitled game', settings: { sky: '#9fc9ea', light: {} }, objects: [], scripts: [] }
