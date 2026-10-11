#!/usr/bin/env node
// Add pieces (a hat, a cape, a sword, a backpack) to ANY rigged character and
// fix them to one of its bones, so they move with it. Also lists the bones.
//
//   node attach.mjs joints MODEL.glb              bone names, their positions and the model's height
//   node attach.mjs add MODEL.glb PARTS.json OUT.glb
//
// PARTS.json: [ { "bone": "Head", "shape": "cone", "offset": [0, 0.25, 0], "radius": 0.4, "height": 0.2,
//                 "rotate": [0, 0, 0], "scale": [1, 1, 1], "color": "#cfae62", "segments": 24, "metal": false }, ... ]
// Positions are in the MODEL's units, relative to the bone's joint (read "joints"
// first: it prints the height so you can size parts). Shapes: box (size), sphere
// (radius), capsule/cylinder/cone (radius, radiusBottom, height), torus (radius,
// tube). "from"/"to" (two bone names, with optional fromOffset/toOffset) lay a
// capsule or cylinder between joints instead of "offset".
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { join } from 'node:path'
import { homedir } from 'node:os'
import { pathToFileURL } from 'node:url'

const NODE_DIR = join(homedir(), '.cache', 'game-studio', 'node')
if (!existsSync(join(NODE_DIR, 'node_modules', 'three'))) execSync(`mkdir -p "${NODE_DIR}" && cd "${NODE_DIR}" && (test -f package.json || npm init -y) && npm install --silent three@0.180.0`, { stdio: 'ignore' })
const THREE = await import(pathToFileURL(join(NODE_DIR, 'node_modules', 'three', 'build', 'three.module.js')).href)

function readGlb(path) {
  const buf = readFileSync(path)
  let off = 12, json = null, bin = Buffer.alloc(0)
  while (off < buf.length) {
    const len = buf.readUInt32LE(off), type = buf.readUInt32LE(off + 4)
    const chunk = buf.subarray(off + 8, off + 8 + len)
    if (type === 0x4e4f534a) json = JSON.parse(chunk.toString('utf8')); else if (type === 0x004e4942) bin = Buffer.from(chunk)
    off += 8 + len
  }
  return { json, bin }
}
function writeGlb(path, json, bin) {
  const pad = (b, f) => (b.length % 4 ? Buffer.concat([b, Buffer.alloc(4 - (b.length % 4), f)]) : b)
  bin = pad(bin, 0); json.buffers = [{ byteLength: bin.length }]
  const js = pad(Buffer.from(JSON.stringify(json)), 0x20)
  const h = Buffer.alloc(12); h.writeUInt32LE(0x46546c67, 0); h.writeUInt32LE(2, 4); h.writeUInt32LE(28 + js.length + bin.length, 8)
  const c1 = Buffer.alloc(8); c1.writeUInt32LE(js.length, 0); c1.writeUInt32LE(0x4e4f534a, 4)
  const c2 = Buffer.alloc(8); c2.writeUInt32LE(bin.length, 0); c2.writeUInt32LE(0x004e4942, 4)
  writeFileSync(path, Buffer.concat([h, c1, js, c2, bin]))
  return 28 + js.length + bin.length
}

const [cmd, modelPath, partsPath, outPath] = process.argv.slice(2)
const { json, bin } = readGlb(modelPath)
const skinIndex = 0
const skin = json.skins?.[skinIndex]
if (!skin) { console.error('This model has no skeleton; pieces cannot follow bones.'); process.exit(1) }
const acc = json.accessors[skin.inverseBindMatrices]
const view = json.bufferViews[acc.bufferView]
const base = (view.byteOffset || 0) + (acc.byteOffset || 0)
const joints = skin.joints.map((node, i) => {
  const m = new THREE.Matrix4().fromArray(Array.from({ length: 16 }, (_, k) => bin.readFloatLE(base + (i * 16 + k) * 4))).invert()
  return { i, node, name: json.nodes[node].name || `bone${i}`, pos: new THREE.Vector3().setFromMatrixPosition(m) }
})
// Mesh vertices are in the skinned mesh's bind space, like the joints above.
const skinnedMesh = json.nodes.findIndex((n) => n.skin === skinIndex && n.mesh != null)
let lo = new THREE.Vector3(Infinity, Infinity, Infinity), hi = new THREE.Vector3(-Infinity, -Infinity, -Infinity)
for (const p of json.meshes[json.nodes[skinnedMesh].mesh].primitives) {
  const a = json.accessors[p.attributes.POSITION]
  if (a.min) { lo.min(new THREE.Vector3(...a.min)); hi.max(new THREE.Vector3(...a.max)) }
}
// Which axis is up in this model's own space (Blender exports are often Z-up).
const ext = hi.clone().sub(lo)
const upAxis = ext.z > ext.y * 1.3 ? 'Z' : 'Y'
const toUp = upAxis === 'Z' ? new THREE.Matrix4().makeRotationX(Math.PI / 2) : new THREE.Matrix4()
const height = upAxis === 'Z' ? ext.z : ext.y
const find = (name) => {
  const clean = (s) => String(s).toLowerCase().replace(/^mixamorig\d*[:_]|^def[-_]|[^a-z0-9]/g, '')
  return joints.find((j) => j.name === name) || joints.find((j) => clean(j.name) === clean(name)) || joints.find((j) => clean(j.name).includes(clean(name)))
}

if (cmd === 'joints') {
  console.log(JSON.stringify({
    height: +height.toFixed(4), up: upAxis, bounds: { min: lo.toArray().map((v) => +v.toFixed(4)), max: hi.toArray().map((v) => +v.toFixed(4)) },
    note: `Units are the model's own: size parts relative to "height" (${height.toFixed(4)}). "up" is the ${upAxis} axis: offsets go along it for height; shapes (cones, cylinders) are stood upright for you, so "rotate" is relative to upright.`,
    joints: Object.fromEntries(joints.map((j) => [j.name, j.pos.toArray().map((v) => +v.toFixed(3))])),
  }, null, 1))
  process.exit(0)
}
if (cmd !== 'add' || !partsPath || !outPath) { console.error('usage: node attach.mjs joints MODEL.glb | node attach.mjs add MODEL.glb PARTS.json OUT.glb'); process.exit(2) }

const parts = JSON.parse(readFileSync(partsPath, 'utf8'))
let data = Buffer.from(bin)
const addAccessor = (typed, type, componentType, extra = {}) => {
  while (data.length % 4) data = Buffer.concat([data, Buffer.alloc(1)])
  json.bufferViews.push({ buffer: 0, byteOffset: data.length, byteLength: typed.byteLength, target: extra.index ? 34963 : 34962 })
  data = Buffer.concat([data, Buffer.from(typed.buffer, typed.byteOffset, typed.byteLength)])
  const comps = { SCALAR: 1, VEC3: 3, VEC4: 4 }[type]
  json.accessors.push({ bufferView: json.bufferViews.length - 1, componentType, count: typed.length / comps, type, ...(extra.normalized ? { normalized: true } : {}), ...(extra.min ? { min: extra.min, max: extra.max } : {}) })
  return json.accessors.length - 1
}
json.materials ||= []
const mesh = json.meshes[json.nodes[skinnedMesh].mesh]
const added = []
for (const p of parts) {
  const bone = find(p.bone || p.from)
  if (!bone) { console.error(`No bone like "${p.bone || p.from}". Run: node attach.mjs joints MODEL.glb`); process.exit(1) }
  const seg = p.segments ?? 16
  let g
  const between = p.from && p.to
  const a = between ? find(p.from).pos.clone().add(new THREE.Vector3(...(p.fromOffset || [0, 0, 0]))) : null
  const b = between ? find(p.to).pos.clone().add(new THREE.Vector3(...(p.toOffset || [0, 0, 0]))) : null
  const len = between ? a.distanceTo(b) : p.height ?? 0.2
  switch (p.shape) {
    case 'box': g = new THREE.BoxGeometry(...(p.size || [0.1, 0.1, 0.1])); break
    case 'sphere': g = new THREE.SphereGeometry(p.radius ?? 0.1, seg, Math.max(4, Math.round(seg * 0.75))); break
    case 'capsule': g = new THREE.CapsuleGeometry(p.radius ?? 0.05, Math.max(0.001, len - 2 * (p.radius ?? 0.05)), 4, seg); break
    case 'cylinder': g = new THREE.CylinderGeometry(p.radius ?? 0.05, p.radiusBottom ?? p.radius ?? 0.05, len, seg); break
    case 'cone': g = new THREE.ConeGeometry(p.radius ?? 0.1, len, seg); break
    case 'torus': g = new THREE.TorusGeometry(p.radius ?? 0.1, p.tube ?? 0.02, Math.max(3, seg / 2), seg); break
    default: console.error(`Unknown shape "${p.shape}"`); process.exit(1)
  }
  if (p.scale) g.scale(...p.scale)
  if (p.rotate) g.applyMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(...p.rotate.map((d) => (d * Math.PI) / 180))))
  if (!between) g.applyMatrix4(toUp)
  if (between) {
    g.applyMatrix4(new THREE.Matrix4().makeRotationFromQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize())))
    g.translate(...a.clone().add(b).multiplyScalar(0.5).toArray())
  } else g.translate(...bone.pos.clone().add(new THREE.Vector3(...(p.offset || [0, 0, 0]))).toArray())
  if (p.flat) { g = g.toNonIndexed(); g.computeVertexNormals() }
  const pos = g.getAttribute('position'), nor = g.getAttribute('normal')
  const box = new THREE.Box3().setFromBufferAttribute(pos)
  const n = pos.count
  const J = new Uint8Array(n * 4), W = new Uint8Array(n * 4)
  for (let i = 0; i < n; i++) { J[i * 4] = bone.i; W[i * 4] = 255 }
  const c = new THREE.Color(p.color || '#cccccc')
  json.materials.push({ name: `added-${json.materials.length}`, pbrMetallicRoughness: { baseColorFactor: [c.r, c.g, c.b, 1], metallicFactor: p.metal ? 0.9 : 0, roughnessFactor: p.rough ?? (p.metal ? 0.3 : 0.8) } })
  const prim = {
    attributes: {
      POSITION: addAccessor(new Float32Array(pos.array), 'VEC3', 5126, { min: box.min.toArray(), max: box.max.toArray() }),
      NORMAL: addAccessor(new Float32Array(nor.array), 'VEC3', 5126),
      JOINTS_0: addAccessor(J, 'VEC4', 5121),
      WEIGHTS_0: addAccessor(W, 'VEC4', 5121, { normalized: true }),
    },
    material: json.materials.length - 1,
  }
  // Other primitives may carry extra attributes (UVs, colours); these parts only need their own.
  if (g.index) prim.indices = addAccessor(new Uint32Array(g.index.array), 'SCALAR', 5125, { index: true })
  mesh.primitives.push(prim)
  added.push({ shape: p.shape, bone: bone.name })
}
const size = writeGlb(outPath, json, data)
console.log(JSON.stringify({ ok: true, out: outPath, bytes: size, added, next: 'Render it (model_tool.py render) in idle and a moving clip and Read it.' }))
