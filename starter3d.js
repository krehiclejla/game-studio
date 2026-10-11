// 3D reference game. It shows the studio's standard 3D toolkit, all free and
// open source, loaded from esm.sh:
//   three.js (MIT) for drawing, Rapier (Apache-2.0) for physics and the
//   character controller, three's own EffectComposer + UnrealBloomPass for glow,
//   and three.quarks (MIT) for particle effects.
// Plus the person's animated model (with a simple fallback), touch/keyboard/
// gamepad movement, jumping, pushable crates, platforms and a saved best time.
export const STARTER_3D_META = {
  id: 'robot-run',
  name: 'Robot Run',
  description: 'Collect the glowing orbs as fast as you can: climb the platforms and knock the crates around.',
  controls: 'Move with the stick, arrow keys, or WASD (push further to run). Jump with the button or Space.',
}

export const STARTER_3D_HTML = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robot Run</title>
<style>
html,body{margin:0;height:100%;overflow:hidden;background:#9fd3ff;touch-action:none;font-family:system-ui,sans-serif}
#hud{position:fixed;left:14px;top:12px;color:#fff;font-weight:700;font-size:20px;text-shadow:0 2px 6px rgba(0,0,0,.45);pointer-events:none}
#panel{position:fixed;inset:0;display:grid;place-items:center;background:rgba(10,20,40,.45);color:#fff;text-align:center;padding:24px}
#panel h1{margin:0 0 8px;font-size:40px}
#panel p{margin:0 0 6px;font-size:18px;opacity:.92}
#panel .go{margin-top:14px;display:inline-block;padding:14px 26px;border-radius:999px;background:#ffd84a;color:#1b1b1b;font-weight:800;font-size:18px}
</style>
</head>
<body>
<div id="hud"></div>
<div id="panel"><div><h1>Robot Run</h1><p>Collect all the glowing orbs as fast as you can.</p><p>Some float over the platforms: jump up!</p><span class="go">Tap to start</span></div></div>
<script type="module">
import * as THREE from 'https://esm.sh/three@0.180.0'
import { GLTFLoader } from 'https://esm.sh/three@0.180.0/examples/jsm/loaders/GLTFLoader.js'
import { EffectComposer } from 'https://esm.sh/three@0.180.0/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'https://esm.sh/three@0.180.0/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'https://esm.sh/three@0.180.0/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'https://esm.sh/three@0.180.0/examples/jsm/postprocessing/OutputPass.js'
import RAPIER from 'https://esm.sh/@dimforge/rapier3d-compat@0.21.0'
import * as QUARKS from 'https://esm.sh/three.quarks@0.16.0?deps=three@0.180.0'

studio.controls({ stick: true, buttons: ['Jump'] })
await RAPIER.init()

const ORB_COUNT = 10
const ARENA = 18
const hud = document.getElementById('hud')
const panel = document.getElementById('panel')

// ---------- renderer, scene, glow ----------
const renderer = new THREE.WebGLRenderer({ antialias: true })
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
renderer.setSize(window.innerWidth, window.innerHeight)
renderer.shadowMap.enabled = true
document.body.prepend(renderer.domElement)

const scene = new THREE.Scene()
scene.background = new THREE.Color(0x9fd3ff)
scene.fog = new THREE.Fog(0x9fd3ff, 28, 60)
const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 200)

// Glow: only things brighter than the threshold (emissive orbs, sparks) bloom.
const composer = new EffectComposer(renderer)
composer.addPass(new RenderPass(scene, camera))
const bloom = new UnrealBloomPass(new THREE.Vector2(window.innerWidth / 2, window.innerHeight / 2), 0.65, 0.3, 0.95)
composer.addPass(bloom)
composer.addPass(new OutputPass())

scene.add(new THREE.HemisphereLight(0xffffff, 0x4a6b3a, 1.5))
const sun = new THREE.DirectionalLight(0xffffff, 2.4)
sun.position.set(8, 16, 6)
sun.castShadow = true
sun.shadow.mapSize.set(1024, 1024)
Object.assign(sun.shadow.camera, { left: -24, right: 24, top: 24, bottom: -24 })
scene.add(sun, sun.target)

// ---------- physics (Rapier) ----------
const world = new RAPIER.World({ x: 0, y: -20, z: 0 })
const physicsLinks = [] // [mesh, body]: meshes that follow a dynamic body

const ground = new THREE.Mesh(new THREE.CircleGeometry(ARENA + 12, 48), new THREE.MeshStandardMaterial({ color: 0x74c05c }))
ground.rotation.x = -Math.PI / 2
ground.receiveShadow = true
scene.add(ground)
world.createCollider(RAPIER.ColliderDesc.cuboid(ARENA + 12, 0.5, ARENA + 12).setTranslation(0, -0.5, 0))
// An invisible fence around the arena.
for (let i = 0; i < 32; i++) {
  const a = (i / 32) * Math.PI * 2
  world.createCollider(RAPIER.ColliderDesc.cuboid(0.3, 3, 2.1).setTranslation(Math.cos(a) * (ARENA + 0.6), 3, Math.sin(a) * (ARENA + 0.6)).setRotation(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), -a)))
}
const ring = new THREE.Mesh(new THREE.RingGeometry(ARENA + 0.4, ARENA + 1, 64), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 }))
ring.rotation.x = -Math.PI / 2
ring.position.y = 0.02
scene.add(ring)

// Fixed platforms to climb.
const platforms = [[6, 1, 4], [10, 2.2, -3], [-7, 1.3, -6], [-11, 2.6, 2]]
for (const [x, y, z] of platforms) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(4, 0.5, 4), new THREE.MeshStandardMaterial({ color: 0xd9b27c }))
  mesh.position.set(x, y, z)
  mesh.castShadow = mesh.receiveShadow = true
  scene.add(mesh)
  world.createCollider(RAPIER.ColliderDesc.cuboid(2, 0.25, 2).setTranslation(x, y, z))
}

// Dynamic crates: the player shoves them around.
const crateMaterial = new THREE.MeshStandardMaterial({ color: 0xb4793f })
for (let i = 0; i < 8; i++) {
  const a = (i / 8) * Math.PI * 2 + 0.3
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), crateMaterial)
  mesh.castShadow = mesh.receiveShadow = true
  scene.add(mesh)
  const body = world.createRigidBody(RAPIER.RigidBodyDesc.dynamic().setTranslation(Math.cos(a) * 9, 0.5 + (i % 2) * 1.1, Math.sin(a) * 9))
  world.createCollider(RAPIER.ColliderDesc.cuboid(0.5, 0.5, 0.5).setDensity(0.4), body)
  physicsLinks.push([mesh, body])
}

// Scenery: trees around the arena (drawing only, outside the fence).
for (let i = 0; i < 26; i++) {
  const angle = (i / 26) * Math.PI * 2 + Math.random() * 0.2
  const r = ARENA + 3 + Math.random() * 6
  const tree = new THREE.Group()
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.35, 1.6), new THREE.MeshStandardMaterial({ color: 0x8b5a2b }))
  trunk.position.y = 0.8
  const top = new THREE.Mesh(new THREE.ConeGeometry(1.3, 3, 8), new THREE.MeshStandardMaterial({ color: 0x2f8f4e, flatShading: true }))
  top.position.y = 2.9
  tree.add(trunk, top)
  tree.position.set(Math.cos(angle) * r, 0, Math.sin(angle) * r)
  tree.scale.setScalar(0.8 + Math.random() * 0.6)
  tree.traverse((o) => { o.castShadow = true })
  scene.add(tree)
}

// ---------- particles (three.quarks) ----------
const particles = new QUARKS.BatchedRenderer()
scene.add(particles)
const sparkTexture = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 64
  const g = c.getContext('2d'); const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32)
  grad.addColorStop(0, 'rgba(255,255,255,1)'); grad.addColorStop(0.4, 'rgba(255,255,255,.6)'); grad.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64)
  return new THREE.CanvasTexture(c)
})()
// A one-off burst of sparks: burst(position, color, count).
function burst(position, color = new THREE.Color(1, 1, 1), count = 40) {
  const system = new QUARKS.ParticleSystem({
    duration: 0.3, looping: false, autoDestroy: true, worldSpace: true,
    startLife: new QUARKS.IntervalValue(0.4, 0.9),
    startSpeed: new QUARKS.IntervalValue(3, 8),
    startSize: new QUARKS.IntervalValue(0.15, 0.35),
    startColor: new QUARKS.ConstantColor(new THREE.Vector4(color.r * 1.5 + 0.2, color.g * 1.5 + 0.2, color.b * 1.5 + 0.2, 1)),
    emissionOverTime: new QUARKS.ConstantValue(0),
    emissionBursts: [{ time: 0, count: new QUARKS.ConstantValue(count), cycle: 1, interval: 0.01, probability: 1 }],
    shape: new QUARKS.SphereEmitter({ radius: 0.3 }),
    material: new THREE.MeshBasicMaterial({ map: sparkTexture, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }),
    renderMode: QUARKS.RenderMode.BillBoard,
  })
  system.addBehavior(new QUARKS.SizeOverLife(new QUARKS.PiecewiseBezier([[new QUARKS.Bezier(1, 0.8, 0.4, 0), 0]])))
  system.addBehavior(new QUARKS.ApplyForce(new THREE.Vector3(0, -1, 0), new QUARKS.ConstantValue(9)))
  system.emitter.position.copy(position)
  scene.add(system.emitter)
  particles.addSystem(system)
}

// ---------- player: a Rapier character controller ----------
const PLAYER_HALF = 0.5, PLAYER_RADIUS = 0.4 // capsule: 1.8 m tall
const playerBody = world.createRigidBody(RAPIER.RigidBodyDesc.kinematicPositionBased().setTranslation(0, 1, 0))
const playerCollider = world.createCollider(RAPIER.ColliderDesc.capsule(PLAYER_HALF, PLAYER_RADIUS), playerBody)
const controller = world.createCharacterController(0.02)
controller.enableSnapToGround(0.3)
controller.enableAutostep(0.35, 0.2, true)
controller.setApplyImpulsesToDynamicBodies(true)

const player = new THREE.Group()
scene.add(player)
let mixer = null
const actions = {}
let current = null
function play(name, fade = 0.2, once = false) {
  const next = actions[name]
  if (!next || next === current) return
  next.reset()
  next.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat)
  next.clampWhenFinished = once
  next.fadeIn(fade).play()
  if (current) current.fadeOut(fade)
  current = next
}

async function loadCharacter() {
  const buffer = studio.model('robot')
  if (buffer) {
    try {
      const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(buffer, '', resolve, reject))
      const model = gltf.scene
      const box = new THREE.Box3().setFromObject(model)
      model.scale.setScalar(1.9 / (box.max.y - box.min.y))
      model.traverse((o) => { if (o.isMesh) o.castShadow = true })
      player.add(model)
      mixer = new THREE.AnimationMixer(model)
      for (const clip of gltf.animations) actions[clip.name] = mixer.clipAction(clip)
      play('Idle', 0)
      return
    } catch (err) {
      console.warn('Robot model could not load, using the fallback', err)
    }
  }
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.45, 0.9, 6, 12), new THREE.MeshStandardMaterial({ color: 0xff7a59 }))
  body.position.y = 0.9
  body.castShadow = true
  const visor = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.22, 0.2), new THREE.MeshStandardMaterial({ color: 0x1b2040 }))
  visor.position.set(0, 1.35, 0.38)
  player.add(body, visor)
}

// ---------- orbs ----------
const orbGeometry = new THREE.IcosahedronGeometry(0.42, 1)
const orbs = []
function placeOrbs() {
  for (const orb of orbs) scene.remove(orb)
  orbs.length = 0
  for (let i = 0; i < ORB_COUNT; i++) {
    const hue = (i / ORB_COUNT) * 0.8
    const color = new THREE.Color().setHSL(hue, 1, 0.5)
    // Glow comes from a saturated emissive colour on a dark base, so it stays coloured, not white.
    const orb = new THREE.Mesh(orbGeometry, new THREE.MeshStandardMaterial({ color: 0x111111, emissive: color, emissiveIntensity: 6 }))
    if (i < platforms.length) {
      const [x, y, z] = platforms[i]
      orb.userData.base = new THREE.Vector3(x, y + 1.3, z)
    } else {
      const angle = Math.random() * Math.PI * 2
      const r = 4 + Math.random() * (ARENA - 5)
      orb.userData.base = new THREE.Vector3(Math.cos(angle) * r, 1, Math.sin(angle) * r)
    }
    orb.position.copy(orb.userData.base)
    orb.userData.phase = Math.random() * Math.PI * 2
    orbs.push(orb)
    scene.add(orb)
  }
}

let state = 'ready'
let collected = 0
let startedAt = 0
let finishedTime = 0
let vy = 0
let grounded = true
let heading = 0
const move = new THREE.Vector3()

function start() {
  if (state === 'playing') return
  collected = 0
  playerBody.setTranslation({ x: 0, y: 1, z: 0 }, true)
  vy = 0
  placeOrbs()
  state = 'playing'
  startedAt = performance.now()
  panel.style.display = 'none'
  play('Idle')
}

function finish() {
  state = 'won'
  finishedTime = (performance.now() - startedAt) / 1000
  const best = Math.min(finishedTime, studio.load('bestTime') || Infinity)
  studio.save('bestTime', best)
  studio.sound('powerup', [null, null, 300, 0.04, 0.12, 0.35, null, 1.3, null, null, 420, 0.06, 0.1])
  play('Dance')
  panel.innerHTML = '<div><h1>All orbs!</h1><p>Time ' + finishedTime.toFixed(1) + ' s</p><p>Best ' + best.toFixed(1) + ' s</p><span class="go">Tap to play again</span></div>'
  setTimeout(() => { panel.style.display = 'grid' }, 900)
}

panel.addEventListener('pointerdown', () => { if (state !== 'playing') start() })
studio.onPress('a', () => {
  if (state !== 'playing') return start()
  if (grounded) {
    vy = 9
    grounded = false
    studio.sound('jump', [null, null, 150, 0.03, 0.05, 0.18, null, 1.4, 12, null, null, null, null, 0.4])
    play('Jump', 0.1, true)
  }
})

function updateHud() {
  const time = state === 'playing' ? (performance.now() - startedAt) / 1000 : finishedTime
  hud.textContent = 'Orbs ' + collected + '/' + ORB_COUNT + '   ' + time.toFixed(1) + ' s'
}

const clock = new THREE.Clock()
const cameraOffset = new THREE.Vector3(0, 7, 10)
const step = new THREE.Vector3()
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05)
  const t = clock.elapsedTime
  step.set(0, 0, 0)
  if (state === 'playing') {
    const tilt = studio.input.tilt
    move.set(studio.input.x + (tilt ? tilt.x : 0), 0, studio.input.y + (tilt ? tilt.y : 0))
    const amount = Math.min(1, move.length())
    if (amount > 0.1) {
      move.normalize()
      step.addScaledVector(move, (amount > 0.75 ? 7.5 : 3.8) * amount * dt)
      const target = Math.atan2(move.x, move.z)
      let delta = target - heading
      delta = Math.atan2(Math.sin(delta), Math.cos(delta))
      heading += delta * Math.min(1, dt * 12)
      player.rotation.y = heading
      if (grounded) play(amount > 0.75 ? 'Running' : 'Walking')
    } else if (grounded) {
      play('Idle')
    }
  }
  // Gravity, then let Rapier slide the capsule along whatever it touches.
  vy -= 20 * dt
  step.y = vy * dt
  controller.computeColliderMovement(playerCollider, step)
  const moved = controller.computedMovement()
  const p = playerBody.translation()
  playerBody.setNextKinematicTranslation({ x: p.x + moved.x, y: p.y + moved.y, z: p.z + moved.z })
  grounded = controller.computedGrounded()
  if (grounded && vy < 0) vy = 0
  world.timestep = Math.max(dt, 1 / 240)
  world.step()
  const now = playerBody.translation()
  player.position.set(now.x, now.y - PLAYER_HALF - PLAYER_RADIUS, now.z)
  for (const [mesh, body] of physicsLinks) {
    mesh.position.copy(body.translation())
    mesh.quaternion.copy(body.rotation())
  }

  if (state === 'playing') {
    for (let i = orbs.length - 1; i >= 0; i--) {
      const orb = orbs[i]
      if (orb.position.distanceTo(now) < 1.3) {
        burst(orb.position, orb.material.emissive)
        scene.remove(orb)
        orbs.splice(i, 1)
        collected++
        studio.sound('coin', [null, null, 1675, null, 0.06, 0.24, 1, 1.82, null, null, 837, 0.06])
        if (collected === ORB_COUNT) finish()
      }
    }
  }
  for (const orb of orbs) {
    orb.position.y = orb.userData.base.y + Math.sin(t * 2 + orb.userData.phase) * 0.25
    orb.rotation.y += dt * 1.5
  }
  if (mixer) mixer.update(dt)
  particles.update(dt)
  camera.position.lerp(new THREE.Vector3().copy(player.position).add(cameraOffset), Math.min(1, dt * 5))
  camera.lookAt(player.position.x, player.position.y + 1, player.position.z)
  sun.position.set(player.position.x + 8, 16, player.position.z + 6)
  sun.target.position.copy(player.position)
  updateHud()
  composer.render(dt)
  requestAnimationFrame(frame)
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
  composer.setSize(window.innerWidth, window.innerHeight)
  bloom.resolution.set(window.innerWidth / 2, window.innerHeight / 2)
})

await loadCharacter()
placeOrbs()
camera.position.copy(cameraOffset)
frame()
</script>
</body>
</html>
`
