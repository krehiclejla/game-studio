// Unpack meshopt-compressed 3D models for pages that cannot run WebAssembly.
//
//   node unpack_models.mjs <data.json>      (rewrites the file in place)
//
// Game Studio games ship their .glb models meshopt-compressed (half the size);
// three.js decodes them in the browser with a WebAssembly decoder. A Project's
// Play build is shown in a preview whose security policy does not allow
// WebAssembly, so every model would fail and the game would fall back to stand-in
// shapes. Decoding here, at build time, gives the page plain models that need no
// decoder. Models without meshopt compression are left exactly as they are.
// Resolves packages from GS_TOOLS_DIR (play_build.py installs them there).
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(path.join(process.env.GS_TOOLS_DIR || '.', 'package.json'))
const { NodeIO } = require('@gltf-transform/core')
const { ALL_EXTENSIONS } = require('@gltf-transform/extensions')
const { MeshoptDecoder } = require('meshoptimizer')

const file = process.argv[2]
const data = JSON.parse(readFileSync(file, 'utf8'))
await MeshoptDecoder.ready
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.decoder': MeshoptDecoder })

async function unpack(b64) {
  const bytes = Buffer.from(b64, 'base64')
  const json = bytes.toString('latin1', 20, 20 + bytes.readUInt32LE(12))
  if (!json.includes('EXT_meshopt_compression')) return null
  const doc = await io.readBinary(new Uint8Array(bytes))
  for (const ext of doc.getRoot().listExtensionsUsed()) {
    if (ext.extensionName === 'EXT_meshopt_compression') ext.dispose()
  }
  return Buffer.from(await io.writeBinary(doc)).toString('base64')
}

let count = 0
for (const group of [data.models, data.art?.models]) {
  for (const [name, b64] of Object.entries(group || {})) {
    if (typeof b64 !== 'string') continue
    try {
      const plain = await unpack(b64)
      if (plain) { group[name] = plain; count++ }
    } catch (err) {
      console.warn(`Could not unpack model ${name}: ${err.message}`)
    }
  }
}
writeFileSync(file, JSON.stringify(data))
console.log(`${count} compressed model(s) unpacked for the preview.`)
