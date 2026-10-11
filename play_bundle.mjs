// Turn a game into one self-contained page for a Project's Play build.
//
//   node play_bundle.mjs <game.html> <data.json> <out.html>
//
// Project previews run with no network at all, but games import their engine
// (three.js, Phaser, ZzFX...) from esm.sh. This bundles every web import into
// the page itself, so a collaborator's Build shows the real game:
//   - each <script type="module"> becomes one bundled module (esbuild);
//   - import('https://...') in an ordinary script (the studio helper's sound
//     loader) is served from a bundled copy placed before it.
// Downloaded modules are cached on disk, so later builds are quick and the
// same engine version always gives the same code.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, join } from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const TOOLS = process.env.GS_TOOLS_DIR
const CACHE = join(HERE, '.build', 'esm-cache')
const esbuild = createRequire(join(TOOLS, 'package.json'))('esbuild')
const { buildGameDocument } = await import(pathToFileURL(join(HERE, 'gameRuntime.js')).href)

const [htmlPath, dataPath, outPath] = process.argv.slice(2)
const data = JSON.parse(readFileSync(dataPath, 'utf8'))
const page = buildGameDocument(readFileSync(htmlPath, 'utf8'), data)
// GS_RAW_OUT: also keep the page as the studio builds it (engine still loaded from the web), for before/after measurements.
if (process.env.GS_RAW_OUT) writeFileSync(process.env.GS_RAW_OUT, page)
// GS_ENGINE_DIR (a studio's engine/ folder): also write the page as the studio plays it now, with the local engine library.
if (process.env.GS_ENGINE_DIR && process.env.GS_ENGINE_OUT) {
  const dir = process.env.GS_ENGINE_DIR
  const index = JSON.parse(readFileSync(join(dir, 'index.json'), 'utf8'))
  const html = readFileSync(htmlPath, 'utf8')
  const engine = {}
  for (const [url, name] of Object.entries(index)) if (html.includes(url) || url.includes('zzfx')) engine[url] = readFileSync(join(dir, name), 'utf8')
  if (Object.keys(engine).some((u) => !u.includes('zzfx') && u !== 'https://esm.sh/three@0.180.0')) engine['https://esm.sh/three@0.180.0'] = readFileSync(join(dir, index['https://esm.sh/three@0.180.0']), 'utf8')
  writeFileSync(process.env.GS_ENGINE_OUT, buildGameDocument(html, { ...data, engine }))
}

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

// esbuild resolves web imports through this: absolute URLs, and paths inside a
// downloaded module (esm.sh uses "/three@.../three.mjs") relative to it.
const web = {
  name: 'web',
  setup(build) {
    build.onResolve({ filter: /^https?:\/\// }, (args) => ({ path: args.path, namespace: 'web' }))
    build.onResolve({ filter: /.*/, namespace: 'web' }, (args) => ({ path: new URL(args.path, args.importer).href, namespace: 'web' }))
    build.onLoad({ filter: /.*/, namespace: 'web' }, async (args) => ({ contents: await download(args.path), loader: 'js' }))
  },
}

const bundle = async (contents, format, globalName) => (await esbuild.build({
  stdin: { contents, loader: 'js', resolveDir: HERE, sourcefile: 'game.js' },
  bundle: true, write: false, format, globalName, minify: true, target: 'es2022',
  plugins: [web], logLevel: 'silent', charset: 'utf8',
})).outputFiles[0].text

// A bundled script must never end its own <script> tag early.
const safe = (code) => code.replace(/<\/script/gi, '<\\/script')

const SCRIPT = /<script(\s[^>]*)?>([\s\S]*?)<\/script>/gi
const parts = []
let last = 0
let modules = 0
for (const match of page.matchAll(SCRIPT)) {
  const [whole, attrs = '', body] = match
  parts.push(page.slice(last, match.index))
  last = match.index + whole.length
  const type = (attrs.match(/type\s*=\s*["']?([^"'\s>]+)/i) || [])[1] || ''
  if (/\ssrc\s*=/i.test(attrs)) {
    // An external classic script: fetch it once and inline it.
    const src = attrs.match(/src\s*=\s*["']([^"']+)["']/i)[1]
    parts.push(`<script>${safe(await download(src))}</script>`)
  } else if (type === 'module') {
    modules += 1
    parts.push(`<script type="module">${safe(await bundle(body, 'esm'))}</script>`)
  } else if (!type || /javascript/i.test(type)) {
    const urls = [...new Set([...body.matchAll(/import\(\s*['"`](https?:\/\/[^'"`]+)['"`]\s*\)/g)].map((m) => m[1]))]
    let code = body
    let preload = ''
    for (const [i, url] of urls.entries()) {
      const name = `__gsWeb${i}`
      preload += `<script>${safe(await bundle(`export * from ${JSON.stringify(url)}`, 'iife', name))}</script>`
      code = code.split(`import('${url}')`).join(`Promise.resolve(${name})`)
    }
    parts.push(`${preload}<script${attrs}>${code}</script>`)
  } else {
    parts.push(whole) // data blocks such as <script type="application/json">
  }
}
parts.push(page.slice(last))
const out = parts.join('')
writeFileSync(outPath, out)
console.log(`Play page ready: ${Math.round(out.length / 1024)} KB, ${modules} game script(s) bundled.`)
