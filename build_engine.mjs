#!/usr/bin/env node
// Pre-build the engine library: every web module Game Studio games import
// (three.js and its add-ons, Phaser, physics, particles, ZzFX) as one local ESM
// file each, so a game starts without fetching anything from esm.sh.
//
//   GS_TOOLS_DIR=.build/tools node build_engine.mjs [outDir]
//
// Writes outDir/<name>.mjs plus outDir/index.json {url: name}. Every add-on
// leaves three.js as an external import of its public URL, so the page's import
// map points all of them at ONE copy of three (a second copy breaks instanceof).
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, rmSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, join } from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const TOOLS = process.env.GS_TOOLS_DIR || join(HERE, '.build', 'tools')
const CACHE = join(HERE, '.build', 'esm-cache')
const OUT = process.argv[2] || join(HERE, 'engine')
const esbuild = createRequire(join(TOOLS, 'package.json'))('esbuild')

export const THREE = 'https://esm.sh/three@0.180.0'
const EXTRA = ['https://esm.sh/three@0.180.0/examples/jsm/postprocessing/ShaderPass.js', 'https://esm.sh/three@0.180.0/examples/jsm/utils/BufferGeometryUtils.js']

// Every esm.sh URL any studio source or template imports (plus EXTRA, used by shipped games).
const SOURCES = ['sceneRuntime.js', 'starter3d.js', 'starter.js', 'survivor3d.js', 'gameRuntime.js', 'kits/templates/physics.html', 'kits/templates/platformer.html', 'kits/templates/puzzle.html', 'kits/templates/racing.html']
const urls = new Set(EXTRA)
// GS_EXTRA_URLS: a file listing more esm.sh URLs (one per line), e.g. everything the studio's games import.
if (process.env.GS_EXTRA_URLS) for (const u of readFileSync(process.env.GS_EXTRA_URLS, 'utf8').split('\n')) if (/^https:\/\/esm\.sh\//.test(u.trim())) urls.add(u.trim())
for (const f of SOURCES) for (const m of readFileSync(join(HERE, f), 'utf8').matchAll(/https:\/\/esm\.sh\/[^'"`)\s]+/g)) urls.add(m[0])

async function download(url) {
  mkdirSync(CACHE, { recursive: true })
  const file = join(CACHE, createHash('sha256').update(url).digest('hex').slice(0, 32))
  if (existsSync(file)) return readFileSync(file, 'utf8')
  const res = await fetch(url, { redirect: 'follow' })
  if (!res.ok) throw new Error(`${url} answered ${res.status}`)
  const text = await res.text()
  writeFileSync(file, text)
  return text
}

// The module three.js itself lives in (esm.sh paths like /three@0.180.0/es2022/three.mjs).
const threeCore = new URL((/from\s*["']([^"']+)["']/.exec(await download(THREE)) || [])[1], THREE).href

const web = (entry) => ({
  name: 'web',
  setup(build) {
    build.onResolve({ filter: /^https?:\/\// }, (a) => a.path === entry ? { path: a.path, namespace: 'web' } : external(a.path))
    build.onResolve({ filter: /.*/, namespace: 'web' }, (a) => external(new URL(a.path, a.importer).href))
    build.onLoad({ filter: /.*/, namespace: 'web' }, async (a) => ({ contents: await download(a.path), loader: 'js' }))
    // three.js stays a bare import of its public URL (the page's import map supplies it), except in its own bundle.
    function external(href) {
      if (entry !== THREE && (href === THREE || href === threeCore)) return { path: THREE, external: true }
      return { path: href, namespace: 'web' }
    }
  },
})

if (existsSync(OUT)) for (const f of readdirSync(OUT)) rmSync(join(OUT, f))
mkdirSync(OUT, { recursive: true })
const index = {}
for (const url of [...urls].sort()) {
  const name = createHash('sha256').update(url).digest('hex').slice(0, 12) + '.mjs'
  const bundle = (contents) => esbuild.build({
    stdin: { contents, loader: 'js', resolveDir: HERE },
    bundle: true, write: false, format: 'esm', minify: true, target: 'es2022', plugins: [web(url)], logLevel: 'silent', charset: 'utf8',
  })
  let res
  try {
    try { res = await bundle(`export * from ${JSON.stringify(url)}; import d from ${JSON.stringify(url)}; export default d`) } // with a default export...
    catch { res = await bundle(`export * from ${JSON.stringify(url)}`) } // ...or without
  } catch (err) {
    console.log(`  skipped  ${url}  (${String(err.message || err).split('\n')[0].slice(0, 100)})`)
    continue
  }
  writeFileSync(join(OUT, name), res.outputFiles[0].text)
  index[url] = name
  console.log(`${Math.round(res.outputFiles[0].text.length / 1024).toString().padStart(6)} KB  ${url}`)
}
writeFileSync(join(OUT, 'index.json'), JSON.stringify(index, null, 1) + '\n')
