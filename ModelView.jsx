// A small live 3D viewer for gallery characters: plays the chosen animation
// and turns slowly; drag to spin it.
import React, { useEffect, useRef, useState } from 'react'

const THREE_URL = 'https://esm.sh/three@0.180.0'
const LOADER_URL = 'https://esm.sh/three@0.180.0/examples/jsm/loaders/GLTFLoader.js'
// three.js loads from esm.sh at runtime (allowed for apps), not into the studio bundle.
const loadRemote = (url) => import(/* @vite-ignore */ url)

// GLTFLoader fetches embedded textures from blob: URLs, which the app frame's
// security policy blocks; answer those fetches from the blobs themselves.
function allowBlobFetch() {
  if (window.__blobFetch) return
  window.__blobFetch = true
  const blobs = new Map()
  const create = URL.createObjectURL.bind(URL)
  const revoke = URL.revokeObjectURL.bind(URL)
  URL.createObjectURL = (obj) => { const url = create(obj); if (obj instanceof Blob) blobs.set(url, obj); return url }
  URL.revokeObjectURL = (url) => { blobs.delete(url); revoke(url) }
  const realFetch = window.fetch.bind(window)
  window.fetch = (input, init) => {
    const url = typeof input === 'string' ? input : input?.url
    return url && blobs.has(url) ? Promise.resolve(new Response(blobs.get(url))) : realFetch(input, init)
  }
}

// The storage keeps a local copy of files, and never re-checks binary files
// once it has one. Models are replaced on the server by the AI tools, so read
// the server copy whenever online (the local copy only when offline).
export async function readModel(path) {
  const storage = window.mobius.storage
  try {
    const fresh = await storage.getWithVersion(path, 'blob')
    if (fresh?.value) return fresh.value
    if (fresh && !fresh.offline) return null
  } catch {}
  return storage.getBlob(path).catch(() => null)
}

export default function ModelView({ path, anim, onClips, fallback }) {
  const mountRef = useRef(null)
  const stateRef = useRef({})
  const [error, setError] = useState('')

  useEffect(() => {
    let disposed = false
    let frame = 0
    const mount = mountRef.current
    ;(async () => {
      try {
        allowBlobFetch()
        const [THREE, { GLTFLoader }] = await Promise.all([loadRemote(THREE_URL), loadRemote(LOADER_URL)])
        const blob = await readModel(path)
        if (!blob) throw new Error('The model could not be found.')
        const buffer = await blob.arrayBuffer()
        if (disposed) return
        const size = mount.clientWidth || 220
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
        renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
        renderer.setSize(size, size)
        renderer.outputColorSpace = THREE.SRGBColorSpace
        mount.appendChild(renderer.domElement)
        const scene = new THREE.Scene()
        scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 2.2))
        const sun = new THREE.DirectionalLight(0xffffff, 2.2)
        sun.position.set(3, 5, 4)
        scene.add(sun)
        const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(buffer, '', resolve, reject))
        if (disposed) { renderer.dispose(); return }
        const root = gltf.scene
        const pivot = new THREE.Group()
        pivot.add(root)
        scene.add(pivot)
        const box = new THREE.Box3().setFromObject(root)
        const center = box.getCenter(new THREE.Vector3())
        const extent = box.getSize(new THREE.Vector3())
        root.position.sub(center)
        const r = Math.max(extent.x, extent.y, extent.z)
        const camera = new THREE.PerspectiveCamera(30, 1, r / 100, r * 100)
        camera.position.set(0, r * 0.35, r * 2.6)
        camera.lookAt(0, 0, 0)
        const mixer = new THREE.AnimationMixer(root)
        stateRef.current = { THREE, mixer, clips: gltf.animations, action: null }
        onClips?.(gltf.animations.map((c) => c.name))
        play(anim)
        const clock = new THREE.Clock()
        const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
        let drag = null
        renderer.domElement.addEventListener('pointerdown', (e) => { drag = e.clientX; renderer.domElement.setPointerCapture(e.pointerId) })
        renderer.domElement.addEventListener('pointermove', (e) => { if (drag != null) { pivot.rotation.y += (e.clientX - drag) * 0.01; drag = e.clientX } })
        renderer.domElement.addEventListener('pointerup', () => { drag = null })
        const loop = () => {
          frame = requestAnimationFrame(loop)
          const dt = clock.getDelta()
          // The move the person picked always plays (they asked to see it); "reduce motion"
          // only stops the automatic turning.
          mixer.update(dt)
          if (drag == null && !reduce) pivot.rotation.y += dt * 0.4
          renderer.render(scene, camera)
        }
        loop()
        stateRef.current.cleanup = () => { cancelAnimationFrame(frame); renderer.dispose(); renderer.domElement.remove() }
      } catch (err) {
        if (disposed) return
        setError(err?.message || 'The 3D preview could not load.')
        // Record it (Möbius logs uncaught app errors) so a device-only failure can be diagnosed.
        setTimeout(() => { throw new Error(`3D preview failed for ${path}: ${err?.message || err}`) })
      }
    })()
    return () => { disposed = true; stateRef.current.cleanup?.() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path])

  function play(name) {
    const { mixer, clips, action } = stateRef.current
    if (!mixer) return
    const clip = clips.find((c) => c.name === name) || clips.find((c) => /idle/i.test(c.name)) || clips[0]
    if (!clip) return
    const next = mixer.clipAction(clip)
    if (action && action !== next) action.fadeOut(0.2)
    next.reset().fadeIn(0.2).play()
    stateRef.current.action = next
  }
  useEffect(() => { play(anim) }, [anim])

  return (
    <div className="gs-model-view" ref={mountRef} role="img" aria-label={`3D preview${anim ? `, ${anim} animation` : ''}`}>
      {error && (fallback
        ? <><img src={fallback} alt="" className="gs-char-thumb gs-char-thumb--big" /><p className="gs-error">The 3D preview couldn't load on this device, so this is a still picture.</p></>
        : <p className="gs-error">{error}</p>)}
    </div>
  )
}
