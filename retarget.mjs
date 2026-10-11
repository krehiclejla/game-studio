#!/usr/bin/env node
// Copy animations from one humanoid skeleton to another (e.g. the free
// Quaternius Universal Animation Library onto a Kenney, Mixamo or imported
// character). Bones are matched by meaning (hips, spine, left upper arm…),
// not by exact name, and motion is transferred relative to each skeleton's
// rest pose, so different rigs and proportions line up.
//
//   node retarget.mjs list SOURCE.glb
//   node retarget.mjs TARGET.glb SOURCE.glb OUT.glb "Walk_Loop=walk,Sprint_Loop=run,Jump_Loop=jump"
//
// The target keeps its textures and existing clips; retargeted clips are added
// (replacing clips of the same name). Skinned humanoids only.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { join } from 'node:path'
import { homedir } from 'node:os'
import { pathToFileURL } from 'node:url'

const NODE_DIR = join(homedir(), '.cache', 'game-studio', 'node')
if (!existsSync(join(NODE_DIR, 'node_modules', 'three'))) {
  execSync(`mkdir -p "${NODE_DIR}" && cd "${NODE_DIR}" && (test -f package.json || npm init -y) && npm install --silent three@0.180.0`, { stdio: 'ignore' })
}
const threeUrl = (p) => pathToFileURL(join(NODE_DIR, 'node_modules', 'three', p)).href
const THREE = await import(threeUrl('build/three.module.js'))
const { GLTFLoader } = await import(threeUrl('examples/jsm/loaders/GLTFLoader.js'))

// ---------- GLB bytes ----------
function readGlb(path) {
  const buf = readFileSync(path)
  let off = 12
  let json = null
  let bin = Buffer.alloc(0)
  while (off < buf.length) {
    const len = buf.readUInt32LE(off)
    const type = buf.readUInt32LE(off + 4)
    const chunk = buf.subarray(off + 8, off + 8 + len)
    if (type === 0x4e4f534a) json = JSON.parse(chunk.toString('utf8'))
    else if (type === 0x004e4942) bin = Buffer.from(chunk)
    off += 8 + len
  }
  return { json, bin }
}
function writeGlb(path, json, bin) {
  const pad = (b, fill) => (b.length % 4 ? Buffer.concat([b, Buffer.alloc(4 - (b.length % 4), fill)]) : b)
  bin = pad(bin, 0)
  json.buffers = [{ byteLength: bin.length }]
  const js = pad(Buffer.from(JSON.stringify(json)), 0x20)
  const header = Buffer.alloc(12)
  header.writeUInt32LE(0x46546c67, 0); header.writeUInt32LE(2, 4); header.writeUInt32LE(12 + 8 + js.length + 8 + bin.length, 8)
  const h1 = Buffer.alloc(8); h1.writeUInt32LE(js.length, 0); h1.writeUInt32LE(0x4e4f534a, 4)
  const h2 = Buffer.alloc(8); h2.writeUInt32LE(bin.length, 0); h2.writeUInt32LE(0x004e4942, 4)
  writeFileSync(path, Buffer.concat([header, h1, js, h2, bin]))
}
// three only needs the skeleton and clips here; drop textures so node needs no image decoding.
function stripped({ json, bin }) {
  const j = JSON.parse(JSON.stringify(json))
  delete j.images; delete j.textures; delete j.samplers
  for (const m of j.materials || []) {
    for (const k of ['normalTexture', 'occlusionTexture', 'emissiveTexture']) delete m[k]
    if (m.pbrMetallicRoughness) { delete m.pbrMetallicRoughness.baseColorTexture; delete m.pbrMetallicRoughness.metallicRoughnessTexture }
    delete m.extensions
  }
  const tmp = join(process.env.TMPDIR || '/tmp', `rt-${process.pid}-${Math.random().toString(36).slice(2)}.glb`)
  writeGlb(tmp, j, Buffer.from(bin))
  const b = readFileSync(tmp)
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength)
}
async function load(path) {
  const glb = readGlb(path)
  const gltf = await new Promise((res, rej) => new GLTFLoader().parse(stripped(glb), '', res, rej))
  return { glb, gltf }
}

// ---------- bone meaning ----------
const SIDE = (n) => (/(^|[^a-z])(l|left)([^a-z]|$)|\.l$|_l$|left/i.test(n) ? 'left' : /(^|[^a-z])(r|right)([^a-z]|$)|\.r$|_r$|right/i.test(n) ? 'right' : '')
function meaning(raw) {
  const n = raw.replace(/^mixamorig\d*[:_]/i, '').replace(/^(def|org|mch)[-_.]/i, '').replace(/^(bip0?1|bone)[_ ]?/i, '').toLowerCase()
  const side = SIDE(raw.replace(/^mixamorig\d*[:_]/i, ''))
  const base = n.replace(/\.(l|r)$|[_.]?(left|right)|^(left|right)|[_.](l|r)$/g, '').replace(/[_.\s-]/g, '')
  const table = [
    [/^(hips?|pelvis)$/, 'hips'],
    [/^(spine|spine0?1|spine001)$/, 'spine'],
    [/^(chest|spine0?2|spine002)$/, 'chest'],
    [/^(upperchest|spine0?3|spine003)$/, 'upperchest'],
    [/^neck(0?1|001)?$/, 'neck'],
    [/^head$/, 'head'],
    [/^(shoulder|clavicle)$/, 'shoulder'],
    [/^(upperarm|arm)$/, 'upperarm'],
    [/^(forearm|lowerarm|elbow)$/, 'forearm'],
    [/^(hand|wrist)$/, 'hand'],
    [/^(thigh|upleg|upperleg)$/, 'thigh'],
    [/^(shin|leg|lowerleg|calf|knee)$/, 'shin'],
    [/^(foot|ankle)$/, 'foot'],
    [/^(toe|toes|toebase|ball)$/, 'toe'],
  ]
  for (const [re, key] of table) if (re.test(base)) return side && !['hips', 'spine', 'chest', 'upperchest', 'neck', 'head'].includes(key) ? `${side}-${key}` : side ? null : key
  return null
}
function bonesOf({ gltf, glb }) {
  // three strips '.' from names (upper_arm.L -> upper_armL); read the file's own names.
  const original = (b) => glb.json.nodes?.[gltf.parser.associations.get(b)?.nodes]?.name || b.name
  const skinned = []
  gltf.scene.traverse((o) => { if (o.isSkinnedMesh) skinned.push(o) })
  if (!skinned.length) throw new Error('This model has no skeleton (it may animate rigid parts instead); it cannot take retargeted clips.')
  const bones = new Set()
  for (const m of skinned) for (const b of m.skeleton.bones) bones.add(b)
  const byMeaning = {}
  for (const b of bones) {
    const key = meaning(original(b))
    if (key && !byMeaning[key]) byMeaning[key] = b
  }
  return byMeaning
}

// ---------- retarget ----------
const worldQuat = (o) => o.getWorldQuaternion(new THREE.Quaternion())
function restPose(gltf, restClip) {
  gltf.scene.updateMatrixWorld(true)
  if (restClip) {
    const mixer = new THREE.AnimationMixer(gltf.scene)
    mixer.clipAction(restClip).play()
    mixer.update(0)
    gltf.scene.updateMatrixWorld(true)
  }
}

async function main() {
  const [a, b, out, spec] = process.argv.slice(2)
  if (a === 'list') {
    const { gltf } = await load(b)
    console.log(JSON.stringify({ clips: gltf.animations.map((c) => ({ name: c.name, seconds: +c.duration.toFixed(2) })) }, null, 1))
    return
  }
  if (!a || !b || !out || !spec) {
    console.error('usage: node retarget.mjs TARGET.glb SOURCE.glb OUT.glb "SourceClip=newName,..."   |   node retarget.mjs list SOURCE.glb')
    process.exit(2)
  }
  const target = await load(a)
  const source = await load(b)
  const tBones = bonesOf(target)
  const sBones = bonesOf(source)
  const keys = Object.keys(tBones).filter((k) => sBones[k])
  if (!keys.includes('hips') || keys.length < 10) throw new Error(`Only ${keys.length} bones matched (${keys.join(', ')}); these skeletons are too different.`)
  // Parents first, so each bone's parent world rotation is known when solving it.
  const depth = (o) => { let d = 0; while (o.parent) { d++; o = o.parent } return d }
  keys.sort((x, y) => depth(tBones[x]) - depth(tBones[y]))

  // Rest poses: the target's bind pose; the source's T-pose clip when it has one.
  restPose(target.gltf, null)
  const tRest = Object.fromEntries(keys.map((k) => [k, worldQuat(tBones[k])]))
  const tHipsY = tBones.hips.getWorldPosition(new THREE.Vector3()).y
  const tpose = source.gltf.animations.find((c) => /t_?pose/i.test(c.name))
  restPose(source.gltf, tpose)
  const sRest = Object.fromEntries(keys.map((k) => [k, worldQuat(sBones[k])]))
  const sHipsRestPos = sBones.hips.getWorldPosition(new THREE.Vector3())
  const scale = tHipsY && sHipsRestPos.y ? tHipsY / sHipsRestPos.y : 1

  const { json, bin } = target.glb
  let data = Buffer.from(bin)
  const assoc = target.gltf.parser.associations
  const nodeIndex = (o) => assoc.get(o)?.nodes
  json.accessors ||= []
  json.bufferViews ||= []
  json.animations ||= []
  const addAccessor = (floats, type, min, max) => {
    const bytes = Buffer.from(new Float32Array(floats).buffer)
    while (data.length % 4) data = Buffer.concat([data, Buffer.alloc(1)])
    json.bufferViews.push({ buffer: 0, byteOffset: data.length, byteLength: bytes.length })
    data = Buffer.concat([data, bytes])
    const comps = { SCALAR: 1, VEC3: 3, VEC4: 4 }[type]
    json.accessors.push({ bufferView: json.bufferViews.length - 1, componentType: 5126, count: floats.length / comps, type, ...(min ? { min, max } : {}) })
    return json.accessors.length - 1
  }

  const done = []
  for (const pair of spec.split(',')) {
    const [from, to] = pair.split('=').map((s) => s.trim())
    const clip = source.gltf.animations.find((c) => c.name === from) || source.gltf.animations.find((c) => c.name.toLowerCase() === from.toLowerCase())
    if (!clip) { done.push({ clip: from, error: 'not found' }); continue }
    const fps = 30
    const frames = Math.max(2, Math.round(clip.duration * fps) + 1)
    const mixer = new THREE.AnimationMixer(source.gltf.scene)
    mixer.stopAllAction()
    const action = mixer.clipAction(clip)
    action.play()
    const times = []
    const rot = Object.fromEntries(keys.map((k) => [k, []]))
    const hipPos = []
    // Working copies of the target's world rotations, solved parent-first per frame.
    for (let f = 0; f < frames; f++) {
      const t = Math.min(clip.duration, f / fps)
      times.push(t)
      action.time = t
      mixer.update(0)
      source.gltf.scene.updateMatrixWorld(true)
      const solved = {}
      for (const k of keys) {
        const bone = tBones[k]
        const delta = worldQuat(sBones[k]).multiply(sRest[k].clone().invert())
        const want = delta.multiply(tRest[k])
        // Parent world rotation: a solved mapped ancestor, else its rest world rotation.
        let parentWorld = new THREE.Quaternion()
        if (bone.parent) {
          const pk = keys.find((x) => tBones[x] === bone.parent)
          parentWorld = pk && solved[pk] ? solved[pk].clone() : worldQuat(bone.parent)
          // Unmapped parent under a solved bone: carry the solved ancestor's change.
          if (!pk) {
            let anc = bone.parent
            let ak = null
            while (anc && !(ak = keys.find((x) => tBones[x] === anc))) anc = anc.parent
            if (ak && solved[ak]) parentWorld = solved[ak].clone().multiply(tRest[ak].clone().invert()).multiply(worldQuat(bone.parent))
          }
        }
        solved[k] = want
        const local = parentWorld.invert().multiply(want)
        rot[k].push(local.x, local.y, local.z, local.w)
      }
      // Hips height and sway, scaled to the target's size, in the hips' parent space.
      const p = sBones.hips.getWorldPosition(new THREE.Vector3()).sub(sHipsRestPos).multiplyScalar(scale)
      const hp = tBones.hips.parent
      const parentInv = hp ? new THREE.Matrix4().copy(hp.matrixWorld).invert() : new THREE.Matrix4()
      const worldRest = tBones.hips.getWorldPosition(new THREE.Vector3())
      const local = worldRest.clone().add(new THREE.Vector3(p.x * 0, p.y, p.z * 0)).applyMatrix4(parentInv)
      hipPos.push(local.x, local.y, local.z)
    }
    const input = addAccessor(times, 'SCALAR', [times[0]], [times[times.length - 1]])
    const samplers = []
    const channels = []
    for (const k of keys) {
      const node = nodeIndex(tBones[k])
      if (node == null) continue
      samplers.push({ input, output: addAccessor(rot[k], 'VEC4'), interpolation: 'LINEAR' })
      channels.push({ sampler: samplers.length - 1, target: { node, path: 'rotation' } })
    }
    const hipsNode = nodeIndex(tBones.hips)
    if (hipsNode != null) {
      samplers.push({ input, output: addAccessor(hipPos, 'VEC3'), interpolation: 'LINEAR' })
      channels.push({ sampler: samplers.length - 1, target: { node: hipsNode, path: 'translation' } })
    }
    const name = to || from
    // Other rigs' channels on unmapped helper bones would fight these; this clip drives mapped bones only.
    json.animations = json.animations.filter((x) => x.name !== name)
    json.animations.push({ name, samplers, channels })
    done.push({ clip: from, as: name, bones: channels.length, seconds: +clip.duration.toFixed(2) })
  }
  writeGlb(out, json, data)
  console.log(JSON.stringify({ ok: true, out, matched: keys, added: done }, null, 1))
}

main().catch((err) => { console.error(String(err?.message || err)); process.exit(1) })
