// Free 3D models the studio can add in one tap. Each must be CC0 (or
// similarly free) and small enough to embed in a game (under ~3 MB).
export const MODEL_CATALOG = [
  {
    name: 'robot',
    title: 'Robot',
    description: 'Animated character: Idle, Walking, Running, Jump, Dance, Wave, Punch, Death and more.',
    url: 'https://raw.githubusercontent.com/mrdoob/three.js/r180/examples/models/gltf/RobotExpressive/RobotExpressive.glb',
    credit: 'Tomás Laulhé (Quaternius), CC0',
  },
]

const MAX_MODEL_BYTES = 3 * 1024 * 1024

export async function fetchCatalogModel(entry, token) {
  const res = await fetch(`/api/proxy?url=${encodeURIComponent(entry.url)}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error('The model could not be downloaded. Try again in a moment.')
  const blob = await res.blob()
  if (blob.size >= MAX_MODEL_BYTES) throw new Error('That model is too large to add.')
  return new Blob([blob], { type: 'model/gltf-binary' })
}

export function checkModelFile(file) {
  if (!/\.glb$/i.test(file.name)) throw new Error('Choose a .glb 3D model file.')
  if (file.size >= MAX_MODEL_BYTES) throw new Error('Models must be under 3 MB so games stay fast on phones.')
  return new Blob([file], { type: 'model/gltf-binary' })
}

export function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '')
    reader.onerror = () => reject(new Error('The model could not be read.'))
    reader.readAsDataURL(blob)
  })
}
