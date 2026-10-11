// 3D survivor-roguelike reference ("Vampire Survivors" style): waves close in, the
// hero fights with a combo (attack -> attack2 -> attack3 finisher) and a dodge,
// enemies drop XP gems, every level offers 3 upgrade cards (stats, new items such as
// orbiting blades / spirit flames / shockwave, new moves such as dash strike),
// mini bosses on a timer and a final boss with a health bar.
// The cast comes from the person's Characters by role (studio.characters()):
// hero, enemy, miniboss, boss, each scaled to its height. Everything has a
// fallback, so the game runs before any character exists.
export const SURVIVOR_3D_META = {
  id: 'survivor-3d',
  name: 'Survivor',
  description: 'Survive the waves: chain combos, collect XP, pick upgrades and defeat the final boss.',
  controls: 'Move with the stick, arrows or WASD. Attack with the button, J or Space (press again to combo). Dodge with the other button, K or Shift.',
}

export const SURVIVOR_3D_HTML = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Survivor</title>
<style>
html,body{margin:0;height:100%;overflow:hidden;background:#15131a;touch-action:none;font-family:system-ui,sans-serif;color:#fff}
#hud{position:fixed;left:12px;right:12px;top:10px;pointer-events:none;font-weight:700;text-shadow:0 2px 6px rgba(0,0,0,.6)}
.bar{height:10px;border-radius:6px;background:rgba(255,255,255,.18);overflow:hidden;margin-top:6px}
.bar i{display:block;height:100%;width:0}
#hp i{background:linear-gradient(90deg,#ff4d4d,#ff9a6b)}#xp i{background:linear-gradient(90deg,#57c7ff,#b48cff)}
#row{display:flex;justify-content:space-between;font-size:16px}
#boss{position:fixed;left:50%;transform:translateX(-50%);top:70px;width:min(80vw,520px);display:none;text-align:center;font-weight:800;letter-spacing:.06em;text-shadow:0 2px 6px #000}
#boss .bar{height:14px}#boss i{background:linear-gradient(90deg,#b0122b,#ff5a3c)}
#panel,#cards{position:fixed;inset:0;display:grid;place-items:center;background:rgba(8,6,12,.62);text-align:center;padding:20px}
#panel h1{margin:0 0 8px;font-size:38px}#panel p{margin:4px 0;opacity:.92}
.go{margin-top:14px;display:inline-block;padding:14px 26px;border-radius:999px;background:#ffcf4a;color:#1b1b1b;font-weight:800}
#cards{display:none}#cards .wrap{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;max-width:760px}
.card{width:200px;min-height:130px;padding:14px;border-radius:14px;background:#221d2c;border:2px solid #4b3f63;text-align:left;cursor:pointer}
.card b{display:block;font-size:17px;margin-bottom:6px;color:#ffcf4a}.card span{font-size:14px;opacity:.9}.card small{display:block;margin-top:8px;opacity:.6}
</style>
</head>
<body>
<div id="hud"><div id="row"><span id="lvl">Lv 1</span><span id="time">0:00</span><span id="kills">0</span></div>
<div class="bar" id="hp"><i></i></div><div class="bar" id="xp"><i></i></div></div>
<div id="boss"><div id="bossName"></div><div class="bar"><i></i></div></div>
<div id="cards"><div><h2>Level up! Pick one</h2><div class="wrap" id="cardWrap"></div></div></div>
<div id="panel"><div><h1>Survivor</h1><p>They are coming from every side.</p><p>Attack again and again to combo. Dodge through danger.</p><span class="go">Tap to start</span></div></div>
<script type="module">
import * as THREE from 'https://esm.sh/three@0.180.0'
import { GLTFLoader } from 'https://esm.sh/three@0.180.0/examples/jsm/loaders/GLTFLoader.js'
import * as SkeletonUtils from 'https://esm.sh/three@0.180.0/examples/jsm/utils/SkeletonUtils.js'
import { EffectComposer } from 'https://esm.sh/three@0.180.0/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'https://esm.sh/three@0.180.0/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'https://esm.sh/three@0.180.0/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'https://esm.sh/three@0.180.0/examples/jsm/postprocessing/OutputPass.js'
import * as QUARKS from 'https://esm.sh/three.quarks@0.16.0?deps=three@0.180.0'

studio.controls({ stick: true, buttons: ['Attack', 'Dodge'] })
const $ = (id) => document.getElementById(id)

// ---------- tuning ----------
const MINIBOSS_AT = [75, 150, 225]   // seconds
const BOSS_AT = 300
const MAX_ENEMIES = 34

// ---------- renderer ----------
const renderer = new THREE.WebGLRenderer({ antialias: true })
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
renderer.setSize(innerWidth, innerHeight)
renderer.shadowMap.enabled = true
document.body.prepend(renderer.domElement)
const scene = new THREE.Scene()
scene.background = new THREE.Color(0x2a2533)
scene.fog = new THREE.Fog(0x2a2533, 22, 55)
const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 300)
const composer = new EffectComposer(renderer)
composer.addPass(new RenderPass(scene, camera))
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth / 2, innerHeight / 2), 0.65, 0.3, 0.95)
composer.addPass(bloom)
composer.addPass(new OutputPass())
scene.add(new THREE.HemisphereLight(0xcfd8ff, 0x3b2a2a, 1.4))
const sun = new THREE.DirectionalLight(0xffe2c4, 2.2)
sun.castShadow = true
sun.shadow.mapSize.set(1024, 1024)
Object.assign(sun.shadow.camera, { left: -22, right: 22, top: 22, bottom: -22 })
scene.add(sun, sun.target)
const ground = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.MeshStandardMaterial({ color: 0x4a4436 }))
ground.rotation.x = -Math.PI / 2
ground.receiveShadow = true
scene.add(ground)
// Scattered stones and grass tufts so movement reads.
for (let i = 0; i < 220; i++) {
  const r = Math.random() < 0.3
  const m = new THREE.Mesh(r ? new THREE.DodecahedronGeometry(0.3 + Math.random() * 0.5) : new THREE.ConeGeometry(0.15, 0.5, 4),
    new THREE.MeshStandardMaterial({ color: r ? 0x6d6a66 : 0x5f7a3a, flatShading: true }))
  m.position.set((Math.random() - 0.5) * 160, r ? 0.1 : 0.25, (Math.random() - 0.5) * 160)
  scene.add(m)
}

// ---------- particles ----------
const particles = new QUARKS.BatchedRenderer()
scene.add(particles)
const dot = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d'); const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32); gr.addColorStop(0, '#fff'); gr.addColorStop(0.4, 'rgba(255,255,255,.6)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c) })()
function burst(pos, color, count = 24, speed = 6) {
  const s = new QUARKS.ParticleSystem({
    duration: 0.2, looping: false, autoDestroy: true, worldSpace: true,
    startLife: new QUARKS.IntervalValue(0.25, 0.6), startSpeed: new QUARKS.IntervalValue(speed * 0.4, speed), startSize: new QUARKS.IntervalValue(0.12, 0.3),
    startColor: new QUARKS.ConstantColor(new THREE.Vector4(color.r * 1.6 + 0.2, color.g * 1.6 + 0.2, color.b * 1.6 + 0.2, 1)),
    emissionOverTime: new QUARKS.ConstantValue(0), emissionBursts: [{ time: 0, count: new QUARKS.ConstantValue(count), cycle: 1, interval: 0.01, probability: 1 }],
    shape: new QUARKS.SphereEmitter({ radius: 0.3 }), renderMode: QUARKS.RenderMode.BillBoard,
    material: new THREE.MeshBasicMaterial({ map: dot, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }),
  })
  s.addBehavior(new QUARKS.SizeOverLife(new QUARKS.PiecewiseBezier([[new QUARKS.Bezier(1, 0.8, 0.4, 0), 0]])))
  s.emitter.position.copy(pos)
  scene.add(s.emitter)
  particles.addSystem(s)
}

// ---------- cast ----------
const loader = new GLTFLoader()
const cast = studio.characters()
const byRole = (role) => cast.filter((c) => c.role === role)
const heroEntry = byRole('hero')[0] || cast.find((c) => c.body === 'humanoid' && !['enemy', 'miniboss', 'boss'].includes(c.role)) || null
const templates = {}
function template(entry) {
  if (!entry) return Promise.resolve(null)
  // One load per character, shared by every copy (many spawn at once).
  templates[entry.name] ||= (async () => {
    const buf = studio.model(entry.name)
    if (!buf) return null
    try {
      const gltf = await new Promise((res, rej) => loader.parse(buf, '', res, rej))
      gltf.scene.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false } })
      const box = new THREE.Box3().setFromObject(gltf.scene)
      return { scene: gltf.scene, clips: gltf.animations, rawHeight: Math.max(0.01, box.max.y - box.min.y) }
    } catch (e) { console.warn('Model failed', entry.name, e); return null }
  })()
  return templates[entry.name]
}
// Fallback body: a horned capsule in the given colour.
function fallbackBody(color, height) {
  const g = new THREE.Group()
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.35 * height / 1.8, height * 0.5, 6, 12), new THREE.MeshStandardMaterial({ color }))
  body.position.y = height / 2
  body.castShadow = true
  const hornMat = new THREE.MeshStandardMaterial({ color: 0xeeeadd })
  for (const s of [-1, 1]) { const h = new THREE.Mesh(new THREE.ConeGeometry(0.07 * height, 0.25 * height, 8), hornMat); h.position.set(s * 0.15 * height, height * 0.98, 0); h.rotation.z = -s * 0.4; g.add(h) }
  g.add(body)
  return g
}
// One actor = a scaled model (or fallback) with its clips; play(name) picks the first match.
function makeActor(tpl, height, color) {
  const root = new THREE.Group()
  const actor = { root, mixer: null, actions: {}, current: null, height }
  if (tpl) {
    const model = SkeletonUtils.clone(tpl.scene)
    model.scale.setScalar(height / tpl.rawHeight)
    root.add(model)
    actor.mixer = new THREE.AnimationMixer(model)
    for (const clip of tpl.clips) actor.actions[clip.name.toLowerCase()] = actor.mixer.clipAction(clip)
    actor.meshes = []
    model.traverse((o) => { if (o.isMesh) { o.material = o.material.clone(); actor.meshes.push(o) } })
  } else {
    const body = fallbackBody(color, height)
    root.add(body)
    actor.meshes = []
    body.traverse((o) => { if (o.isMesh) actor.meshes.push(o) })
  }
  scene.add(root)
  return actor
}
function find(actor, names) {
  for (const n of names) { const a = actor.actions[n]; if (a) return a }
  for (const n of names) { const k = Object.keys(actor.actions).find((key) => key.includes(n)); if (k) return actor.actions[k] }
  return null
}
function play(actor, names, { once = false, fade = 0.12, speed = 1 } = {}) {
  const next = find(actor, names)
  if (!next) return 0
  if (next === actor.current && !once) return next.getClip().duration
  next.reset()
  next.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat)
  next.clampWhenFinished = once
  next.timeScale = speed
  next.fadeIn(fade).play()
  if (actor.current && actor.current !== next) actor.current.fadeOut(fade)
  actor.current = next
  return next.getClip().duration / speed
}
function flash(actor, color) {
  for (const m of actor.meshes) if (m.material.emissive) { m.material.emissive.setHex(color); m.material.emissiveIntensity = 0.8 }
  setTimeout(() => { for (const m of actor.meshes) if (m.material.emissive) m.material.emissive.setHex(0x000000) }, 110)
}

// ---------- state ----------
const stats = { maxHp: 100, damage: 12, speed: 5.5, attackSpeed: 1, reach: 2.3, magnet: 2.5, regen: 0, crit: 0.05, armor: 0 }
const items = { blades: 0, flames: 0, shockwave: 0, dashStrike: false, whirlwind: false }
let hero, heroHp, level, xp, xpNext, kills, t, state = 'ready', paused = false
const enemies = [], gems = [], flames = [], blades = []
let spawnTimer = 0, minibossIndex = 0, bossSpawned = false, boss = null
let combo = 0, attackTimer = 0, comboWindow = 0, queued = false, hitDone = false, attackDur = 0
let dodgeTimer = 0, dodgeCooldown = 0, invuln = 0, shockTimer = 0, flameTimer = 0
const dodgeDir = new THREE.Vector3(), facing = new THREE.Vector3(0, 0, 1)

async function start() {
  $('panel').style.display = 'none'
  Object.assign(stats, { maxHp: 100, damage: 12, speed: 5.5, attackSpeed: 1, reach: 2.3, magnet: 2.5, regen: 0, crit: 0.05, armor: 0 })
  Object.assign(items, { blades: 0, flames: 0, shockwave: 0, dashStrike: false, whirlwind: false })
  for (const e of enemies) scene.remove(e.actor.root)
  for (const g of gems) scene.remove(g)
  for (const b of blades) scene.remove(b)
  enemies.length = 0; gems.length = 0; blades.length = 0
  if (hero) scene.remove(hero.root)
  hero = makeActor(await template(heroEntry), 1.8, 0x3b5bdb)
  heroHp = stats.maxHp; level = 1; xp = 0; xpNext = 5; kills = 0; t = 0
  spawnTimer = 0; minibossIndex = 0; bossSpawned = false; boss = null; combo = 0; attackTimer = 0
  $('boss').style.display = 'none'
  play(hero, ['idle'])
  state = 'playing'
}

// ---------- spawning ----------
const FALLBACK_COLORS = [0xc0392b, 0x2e86de, 0x27ae60, 0x8e44ad, 0xd35400]
async function spawn(kind, entry) {
  const role = kind
  const pool = entry ? [entry] : byRole(role)
  const pick = pool.length ? pool[Math.floor(Math.random() * pool.length)] : null
  const height = pick?.height || (role === 'boss' ? 5 : role === 'miniboss' ? 3 : 2)
  const actor = makeActor(await template(pick), height, FALLBACK_COLORS[Math.floor(Math.random() * FALLBACK_COLORS.length)])
  const a = Math.random() * Math.PI * 2
  const d = role === 'enemy' ? 22 + Math.random() * 6 : 18
  actor.root.position.set(hero.root.position.x + Math.cos(a) * d, 0, hero.root.position.z + Math.sin(a) * d)
  const scale = 1 + t / 90
  const base = role === 'boss' ? 1800 : role === 'miniboss' ? 420 : 22
  const e = { actor, role, name: pick?.name || role, hp: base * scale, maxHp: base * scale, speed: role === 'enemy' ? 2.2 + Math.random() : role === 'miniboss' ? 2.4 : 2.0,
    damage: (role === 'boss' ? 28 : role === 'miniboss' ? 18 : 8) * (1 + t / 240), radius: Math.max(0.5, height * 0.22), reach: Math.max(1.4, height * 0.45),
    cooldown: 1 + Math.random(), attacking: 0, knock: new THREE.Vector3(), dead: 0, hitBy: 0 }
  play(actor, ['walk', 'run'])
  enemies.push(e)
  if (role !== 'enemy') {
    burst(actor.root.position.clone().setY(1), new THREE.Color(0xff3b3b), 60, 9)
    showBoss(e)
    studio.sound('boss', [null, null, 80, 0.1, 0.4, 0.6, 3, 0.5, null, null, null, null, null, 0.5])
  }
  return e
}
function showBoss(e) { if (boss && !boss.dead && boss.role === 'boss' && e.role !== 'boss') return; boss = e; $('boss').style.display = 'block'; $('bossName').textContent = e.name.replace(/-/g, ' ').toUpperCase() }

// ---------- combat ----------
const COMBO = [
  { clips: ['attack'], mult: 1, arc: 1.9, hitAt: 0.35 },
  { clips: ['attack2', 'attack'], mult: 1.25, arc: 2.1, hitAt: 0.35 },
  { clips: ['attack3', 'heavy', 'attack'], mult: 2.1, arc: 2.6, hitAt: 0.45, knock: 6 },
]
function attackPressed() {
  if (state !== 'playing' || paused) return
  if (dodgeTimer > 0) {
    if (items.dashStrike) { dodgeTimer = 0; doAttack(2, true) }
    return
  }
  if (attackTimer > 0) { queued = true; return }
  doAttack(0)
}
function doAttack(step, dash = false) {
  combo = step
  // Aim assist: swing toward the nearest enemy in range (a phone stick is imprecise).
  const near = enemies.filter((e) => !e.dead).map((e) => [e, e.actor.root.position.distanceTo(hero.root.position) - e.radius]).sort((a, b) => a[1] - b[1])[0]
  if (near && near[1] < stats.reach * 1.6) facing.copy(near[0].actor.root.position).sub(hero.root.position).setY(0).normalize()
  const move = dash ? { clips: ['dash-attack', 'attack3', 'attack'], mult: 2.4, arc: 2.2, hitAt: 0.3, knock: 5 } : COMBO[step]
  attackDur = play(hero, move.clips, { once: true, fade: 0.06, speed: 1.35 * stats.attackSpeed }) || 0.45
  attackDur = Math.min(Math.max(attackDur, 0.3), 1.1)
  attackTimer = attackDur
  hitDone = false
  queued = false
  hero.move = move
  if (dash) invuln = 0.35
  studio.sound('swing' + step, [0.6, 0.1, 300 + step * 90, 0.01, 0.03, 0.08, 4, 1.4, -8])
}
function heroHit(move) {
  const whirl = items.whirlwind && move === COMBO[2]
  const reach = stats.reach * (move.mult > 2 ? 1.2 : 1)
  let hitAny = false
  for (const e of enemies) {
    if (e.dead) continue
    const to = e.actor.root.position.clone().sub(hero.root.position).setY(0)
    const dist = to.length() - e.radius
    if (dist > reach) continue
    if (!whirl && to.normalize().dot(facing) < Math.cos(move.arc / 2)) continue
    const crit = Math.random() < stats.crit
    damage(e, stats.damage * move.mult * (crit ? 2 : 1), move.knock || 2, crit)
    hitAny = true
  }
  if (hitAny) studio.sound('hit', [1.2, 0.05, 200, 0, 0.02, 0.1, 4, 2, 0, 0, 0, 0, 0, 0.8])
  if (whirl) burst(hero.root.position.clone().setY(1), new THREE.Color(0xffe08a), 40, 8)
}
function damage(e, amount, knock, crit) {
  if (e.dead) return
  e.hp -= amount
  e.knock.copy(e.actor.root.position).sub(hero.root.position).setY(0).normalize().multiplyScalar(knock * (e.role === 'enemy' ? 1 : 0.25))
  flash(e.actor, crit ? 0xffd000 : 0xff2020)
  burst(e.actor.root.position.clone().setY(e.actor.height * 0.55), crit ? new THREE.Color(1, 0.8, 0.2) : new THREE.Color(1, 0.25, 0.2), crit ? 20 : 10, 5)
  if (e.hp <= 0) kill(e)
  else if (e.role === 'enemy' && Math.random() < 0.5) play(e.actor, ['hurt', 'hit'], { once: true, fade: 0.05 })
}
function kill(e) {
  e.dead = 1.6
  kills++
  play(e.actor, ['die', 'death'], { once: true, fade: 0.05 })
  const value = e.role === 'boss' ? 60 : e.role === 'miniboss' ? 20 : 1
  for (let i = 0; i < Math.min(value, 12); i++) dropGem(e.actor.root.position, Math.max(1, Math.round(value / Math.min(value, 12))))
  if (e === boss) { boss = null; $('boss').style.display = 'none' }
  if (e.role === 'boss') setTimeout(() => finish(true), 1500)
}
const gemGeo = new THREE.OctahedronGeometry(0.18)
function dropGem(pos, value) {
  const color = value > 3 ? 0xff5ad1 : value > 1 ? 0x7c5cff : 0x3fd6ff
  const g = new THREE.Mesh(gemGeo, new THREE.MeshStandardMaterial({ color: 0x111111, emissive: color, emissiveIntensity: 5 }))
  g.position.set(pos.x + (Math.random() - 0.5) * 1.5, 0.35, pos.z + (Math.random() - 0.5) * 1.5)
  g.userData.value = value
  scene.add(g)
  gems.push(g)
}
function hurtHero(amount) {
  if (invuln > 0 || state !== 'playing') return
  heroHp -= Math.max(1, amount - stats.armor)
  invuln = 0.5
  flash(hero, 0xff0000)
  studio.sound('hurt', [1.5, 0.1, 120, 0, 0.05, 0.2, 3, 1, -5])
  if (heroHp <= 0) finish(false)
}
function dodgePressed() {
  if (state !== 'playing' || paused || dodgeCooldown > 0 || dodgeTimer > 0) return
  dodgeDir.set(studio.input.x, 0, studio.input.y)
  if (dodgeDir.lengthSq() < 0.05) dodgeDir.copy(facing)
  dodgeDir.normalize()
  dodgeTimer = 0.45
  dodgeCooldown = 0.9
  invuln = 0.45
  attackTimer = 0
  play(hero, ['dodge', 'roll'], { once: true, fade: 0.05, speed: 1.3 })
}
studio.onPress('a', attackPressed)
studio.onPress('b', dodgePressed)
addEventListener('keydown', (e) => {
  if (e.code === 'KeyJ') attackPressed()
  if (e.code === 'KeyK') dodgePressed()
  if (paused && ['Digit1', 'Digit2', 'Digit3'].includes(e.code)) pickCard(Number(e.code.slice(-1)) - 1)
})

// ---------- upgrades ----------
const UPGRADES = [
  { id: 'dmg', name: 'Sharper Edge', text: '+25% damage', apply: () => { stats.damage *= 1.25 } },
  { id: 'hp', name: 'Iron Body', text: '+25 max health and heal fully', apply: () => { stats.maxHp += 25; heroHp = stats.maxHp } },
  { id: 'spd', name: 'Swift Feet', text: '+12% move speed', apply: () => { stats.speed *= 1.12 } },
  { id: 'as', name: 'Flowing Strikes', text: '+18% attack speed', apply: () => { stats.attackSpeed *= 1.18 } },
  { id: 'reach', name: 'Long Reach', text: '+18% attack reach', apply: () => { stats.reach *= 1.18 } },
  { id: 'mag', name: 'Spirit Pull', text: 'Pick up XP from further away', apply: () => { stats.magnet *= 1.5 } },
  { id: 'crit', name: 'Killing Intent', text: '+8% chance of double damage', apply: () => { stats.crit += 0.08 } },
  { id: 'regen', name: 'Second Wind', text: 'Heal 1.5 health per second', apply: () => { stats.regen += 1.5 } },
  { id: 'armor', name: 'Lacquered Armour', text: 'Take 3 less damage per hit', apply: () => { stats.armor += 3 } },
  { id: 'blades', name: 'Orbiting Blades', text: 'Spirit blades circle you and cut enemies (more each pick)', item: true, apply: () => { items.blades++; rebuildBlades() } },
  { id: 'flames', name: 'Spirit Flames', text: 'Homing flames seek the nearest enemy (more each pick)', item: true, apply: () => { items.flames++ } },
  { id: 'shock', name: 'Shockwave', text: 'A burst around you every few seconds (stronger each pick)', item: true, apply: () => { items.shockwave++ } },
  { id: 'dash', name: 'Dash Strike', text: 'New move: attack while dodging for a lunging strike', once: true, apply: () => { items.dashStrike = true } },
  { id: 'whirl', name: 'Whirlwind Finisher', text: 'New move: the 3rd combo hit spins and hits all around', once: true, apply: () => { items.whirlwind = true } },
]
let offered = []
function levelUp() {
  level++
  xp -= xpNext
  xpNext = Math.round(xpNext * 1.35 + 3)
  const pool = UPGRADES.filter((u) => !(u.once && (u.id === 'dash' ? items.dashStrike : items.whirlwind)))
  offered = pool.sort(() => Math.random() - 0.5).slice(0, 3)
  $('cardWrap').innerHTML = offered.map((u, i) => '<div class="card" data-i="' + i + '"><b>' + u.name + '</b><span>' + u.text + '</span><small>' + (u.item ? 'Item' : u.once ? 'New move' : 'Upgrade') + ' · ' + (i + 1) + '</small></div>').join('')
  $('cards').style.display = 'grid'
  paused = true
  burst(hero.root.position.clone().setY(1), new THREE.Color(0.6, 0.8, 1), 50, 7)
  studio.sound('level', [1, 0, 523, 0.02, 0.2, 0.3, 0, 1, 0, 0, 262, 0.08])
}
function pickCard(i) {
  const u = offered[i]
  if (!u || !paused) return
  u.apply()
  $('cards').style.display = 'none'
  paused = false
  if (xp >= xpNext) levelUp()
}
$('cardWrap').addEventListener('pointerdown', (e) => { const c = e.target.closest('.card'); if (c) pickCard(Number(c.dataset.i)) })
const bladeGeo = new THREE.ConeGeometry(0.12, 0.9, 4)
function rebuildBlades() {
  for (const b of blades) scene.remove(b)
  blades.length = 0
  for (let i = 0; i < items.blades + 1; i++) {
    const b = new THREE.Mesh(bladeGeo, new THREE.MeshStandardMaterial({ color: 0x111111, emissive: 0x9fd8ff, emissiveIntensity: 4 }))
    b.rotation.x = Math.PI / 2
    scene.add(b)
    blades.push(b)
  }
}

// ---------- flow ----------
function finish(won) {
  if (state !== 'playing') return
  state = won ? 'won' : 'lost'
  const best = studio.load('best') || 0
  if (won && (!best || t < best)) studio.save('best', t)
  play(hero, won ? ['victory', 'dance', 'idle'] : ['die', 'death'], { once: !won })
  $('panel').innerHTML = '<div><h1>' + (won ? 'Victory' : 'Fallen') + '</h1><p>Survived ' + fmt(t) + ' · Level ' + level + ' · ' + kills + ' defeated</p>' + (studio.load('best') ? '<p>Fastest win ' + fmt(studio.load('best')) + '</p>' : '') + '<span class="go">Tap to play again</span></div>'
  setTimeout(() => { $('panel').style.display = 'grid' }, 1200)
}
const fmt = (s) => Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0')
$('panel').addEventListener('pointerdown', () => { if (state !== 'playing') start() })
addEventListener('keydown', (e) => { if (state !== 'playing' && (e.code === 'Space' || e.code === 'Enter')) start() })

// ---------- loop ----------
const clock = new THREE.Clock()
const tmp = new THREE.Vector3()
function update(dt) {
  t += dt
  // Spawning: steadily more enemies, mini bosses and a final boss on the clock.
  spawnTimer -= dt
  const alive = enemies.filter((e) => !e.dead && e.role === 'enemy').length
  if (spawnTimer <= 0 && alive < MAX_ENEMIES) { spawn('enemy'); spawnTimer = Math.max(0.35, 2.2 - t / 60) }
  if (minibossIndex < MINIBOSS_AT.length && t >= MINIBOSS_AT[minibossIndex]) {
    const pool = byRole('miniboss')
    spawn('miniboss', pool.length ? pool[minibossIndex % pool.length] : null)
    minibossIndex++
  }
  if (!bossSpawned && t >= BOSS_AT) { bossSpawned = true; spawn('boss') }
  heroHp = Math.min(stats.maxHp, heroHp + stats.regen * dt)
  if (xp >= xpNext && !paused) levelUp()
  invuln -= dt; dodgeCooldown -= dt

  // Hero movement, combo and dodge.
  const mv = tmp.set(studio.input.x + (studio.input.tilt?.x || 0), 0, studio.input.y + (studio.input.tilt?.y || 0))
  const amount = Math.min(1, mv.length())
  if (dodgeTimer > 0) {
    dodgeTimer -= dt
    hero.root.position.addScaledVector(dodgeDir, stats.speed * 2.1 * dt)
  } else if (attackTimer > 0) {
    attackTimer -= dt
    const move = hero.move
    const elapsed = attackDur - attackTimer
    if (!hitDone && elapsed >= attackDur * move.hitAt) { hitDone = true; heroHit(move) }
    hero.root.position.addScaledVector(facing, dt * (move.mult > 2 ? 3 : 1.2))
    if (attackTimer <= 0) {
      if (queued && combo < 2) doAttack(combo + 1)
      else { combo = 0; queued = false }
    }
  } else {
    if (amount > 0.1) {
      mv.normalize()
      facing.lerp(mv, Math.min(1, dt * 14)).normalize()
      hero.root.position.addScaledVector(mv, stats.speed * amount * dt)
      play(hero, amount > 0.7 ? ['run', 'sprint', 'walk'] : ['walk'])
    } else play(hero, ['idle'])
  }
  hero.root.rotation.y = Math.atan2(facing.x, facing.z)

  // Enemies: chase, keep apart, attack in reach, get knocked back.
  for (let i = enemies.length - 1; i >= 0; i--) {
    const e = enemies[i]
    const p = e.actor.root.position
    if (e.dead) {
      e.dead -= dt
      if (e.dead <= 0) { scene.remove(e.actor.root); enemies.splice(i, 1) }
      e.actor.mixer?.update(dt)
      continue
    }
    const to = hero.root.position.clone().sub(p).setY(0)
    const dist = to.length()
    to.normalize()
    e.actor.root.rotation.y = Math.atan2(to.x, to.z)
    e.cooldown -= dt
    if (e.attacking > 0) {
      e.attacking -= dt
      if (e.attacking <= 0.25 && !e.struck) { e.struck = true; if (dist < e.reach + 0.6) hurtHero(e.damage) }
    } else if (dist < e.reach && e.cooldown <= 0) {
      e.attacking = Math.min(1.2, play(e.actor, ['attack', 'heavy'], { once: true, fade: 0.08 }) || 0.8)
      e.struck = false
      e.cooldown = e.role === 'enemy' ? 1.6 : 2.4
    } else {
      p.addScaledVector(to, e.speed * dt)
      play(e.actor, ['walk', 'run'])
    }
    if (e.knock.lengthSq() > 0.001) { p.addScaledVector(e.knock, dt); e.knock.multiplyScalar(Math.pow(0.02, dt)) }
    for (const o of enemies) {
      if (o === e || o.dead) continue
      const d = p.clone().sub(o.actor.root.position).setY(0)
      const min = e.radius + o.radius
      const l = d.length()
      if (l > 0 && l < min) p.addScaledVector(d.divideScalar(l), (min - l) * 0.5)
    }
    if (dist < e.radius + 0.4 && e.role === 'enemy') hurtHero(e.damage * dt * 2)
    // Items hit enemies.
    for (const b of blades) if (b.position.distanceTo(p.clone().setY(1)) < e.radius + 0.6 && e.hitBy <= 0) { damage(e, stats.damage * 0.6, 1.5); e.hitBy = 0.4 }
    e.hitBy -= dt
    e.actor.mixer?.update(dt)
  }

  // Orbiting blades.
  blades.forEach((b, i) => {
    const a = t * 3 + (i / blades.length) * Math.PI * 2
    b.position.set(hero.root.position.x + Math.cos(a) * 2.4, 1, hero.root.position.z + Math.sin(a) * 2.4)
    b.rotation.z = a
  })
  // Spirit flames: homing shots.
  if (items.flames) {
    flameTimer -= dt
    if (flameTimer <= 0) {
      flameTimer = Math.max(0.35, 1.4 - items.flames * 0.2)
      for (let k = 0; k < items.flames; k++) {
        const f = new THREE.Mesh(new THREE.SphereGeometry(0.18, 8, 8), new THREE.MeshStandardMaterial({ color: 0x111111, emissive: 0x6effc8, emissiveIntensity: 6 }))
        f.position.copy(hero.root.position).setY(1.3)
        f.userData = { life: 2.5, vel: new THREE.Vector3((Math.random() - 0.5) * 4, 2, (Math.random() - 0.5) * 4) }
        scene.add(f); flames.push(f)
      }
    }
  }
  for (let i = flames.length - 1; i >= 0; i--) {
    const f = flames[i]
    const target = enemies.filter((e) => !e.dead).sort((a, b) => a.actor.root.position.distanceTo(f.position) - b.actor.root.position.distanceTo(f.position))[0]
    if (target) f.userData.vel.lerp(target.actor.root.position.clone().setY(1).sub(f.position).normalize().multiplyScalar(12), Math.min(1, dt * 4))
    f.position.addScaledVector(f.userData.vel, dt)
    f.userData.life -= dt
    if (target && f.position.distanceTo(target.actor.root.position.clone().setY(1)) < target.radius + 0.5) { damage(target, stats.damage * 0.8, 1); f.userData.life = 0 }
    if (f.userData.life <= 0) { scene.remove(f); flames.splice(i, 1) }
  }
  // Shockwave.
  if (items.shockwave) {
    shockTimer -= dt
    if (shockTimer <= 0) {
      shockTimer = Math.max(2, 5 - items.shockwave * 0.6)
      const r = 3.5 + items.shockwave
      burst(hero.root.position.clone().setY(0.4), new THREE.Color(1, 0.5, 0.2), 70, r * 2.5)
      for (const e of enemies) if (!e.dead && e.actor.root.position.distanceTo(hero.root.position) < r + e.radius) damage(e, stats.damage * (1 + items.shockwave * 0.5), 5)
    }
  }
  // XP gems drift to the hero inside the magnet radius.
  for (let i = gems.length - 1; i >= 0; i--) {
    const g = gems[i]
    g.rotation.y += dt * 3
    const d = g.position.distanceTo(tmp.copy(hero.root.position).setY(0.35))
    if (d < stats.magnet) g.position.lerp(tmp, Math.min(1, dt * 10 / Math.max(d, 0.3)))
    if (d < 0.6) {
      xp += g.userData.value
      scene.remove(g); gems.splice(i, 1)
      studio.sound('xp', [0.4, 0, 1200, 0, 0.01, 0.05, 0, 2])
      if (xp >= xpNext && !paused) levelUp()
    }
  }
}
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05)
  if (state === 'playing' && !paused && hero) update(dt)
  if (hero?.mixer && !paused) hero.mixer.update(dt)
  if (!paused) particles.update(dt)
  if (hero) {
    const target = hero.root.position
    camera.position.lerp(tmp.set(target.x, 10, target.z + 8.5), Math.min(1, dt * 6))
    camera.lookAt(target.x, 1, target.z)
    sun.position.set(target.x + 10, 20, target.z + 6); sun.target.position.copy(target)
    $('hp').firstChild.style.width = Math.max(0, heroHp / stats.maxHp * 100) + '%'
    $('xp').firstChild.style.width = Math.min(100, xp / xpNext * 100) + '%'
    $('lvl').textContent = 'Lv ' + level
    $('time').textContent = fmt(t)
    $('kills').textContent = kills + ' defeated'
    if (boss) $('boss').querySelector('i').style.width = Math.max(0, boss.hp / boss.maxHp * 100) + '%'
  }
  composer.render()
  requestAnimationFrame(frame)
}
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix()
  renderer.setSize(innerWidth, innerHeight); composer.setSize(innerWidth, innerHeight)
})
camera.position.set(0, 10, 8.5)
camera.lookAt(0, 1, 0)
hero = makeActor(await template(heroEntry), 1.8, 0x3b5bdb)
play(hero, ['idle'])
frame()
</script>
</body>
</html>
`
