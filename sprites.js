// Procedural pixel sprites, in the spirit of zfedoran's pixel-sprite-generator:
// a half mask is randomised, mirrored, outlined, and shaded.
// Mask cells: 0 empty, 1 body or empty, 2 body or outline, -1 outline.
const MASKS = {
  hero: [5, [
    0, 0, 0, 0, 0,
    0, 0, 1, 1, 1,
    0, 0, 1, 2, 2,
    0, 0, 1, 1, 1,
    0, 0, 0, 1, 1,
    0, 1, 1, 1, 1,
    1, 1, 1, 2, 2,
    1, 0, 1, 1, 1,
    0, 0, 1, 1, 1,
    0, 0, 1, 1, 0,
    0, 0, 1, 1, 0,
    0, 1, 1, 0, 0,
  ]],
  ship: [6, [
    0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 1, 1,
    0, 0, 0, 0, 1, -1,
    0, 0, 0, 1, 1, -1,
    0, 0, 0, 1, 1, -1,
    0, 0, 1, 1, 1, -1,
    0, 1, 1, 1, 2, 2,
    0, 1, 1, 1, 2, 2,
    0, 1, 1, 1, 2, 2,
    0, 1, 1, 1, 1, -1,
    0, 0, 0, 1, 1, 1,
    0, 0, 0, 0, 0, 0,
  ]],
  enemy: [6, [
    0, 0, 0, 0, 0, 0,
    0, 1, 0, 0, 1, 1,
    0, 0, 1, 1, 2, 2,
    0, 1, 1, 2, 2, 2,
    1, 1, 2, 2, 2, 2,
    1, 1, 2, 2, 1, 1,
    0, 1, 0, 1, 0, 1,
    1, 0, 0, 1, 0, 0,
  ]],
  item: [4, [
    0, 0, 1, 1,
    0, 1, 2, 2,
    1, 2, 2, 2,
    1, 2, 2, 2,
    1, 2, 2, 2,
    0, 1, 2, 2,
    0, 0, 1, 1,
    0, 0, 0, 0,
  ]],
}

const TILE_STYLES = {
  grass: [[96, 55, 30], [104, 50, 38], [88, 45, 24]],
  stone: [[220, 8, 38], [220, 6, 48], [220, 10, 28]],
  water: [[205, 70, 42], [198, 75, 52], [210, 65, 34]],
  lava: [[14, 90, 48], [36, 95, 55], [4, 85, 34]],
  sand: [[42, 60, 62], [38, 55, 70], [46, 50, 54]],
}

export const SPRITE_KINDS = [...Object.keys(MASKS), 'tile']
export const TILE_KINDS = Object.keys(TILE_STYLES)

function rng(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function toDataUrl(width, height, pixels, scale) {
  const canvas = document.createElement('canvas')
  canvas.width = width * scale
  canvas.height = height * scale
  const ctx = canvas.getContext('2d')
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const color = pixels[y * width + x]
      if (!color) continue
      ctx.fillStyle = color
      ctx.fillRect(x * scale, y * scale, scale, scale)
    }
  }
  return canvas.toDataURL('image/png')
}

function characterPixels(kind, random) {
  const [half, mask] = MASKS[kind]
  const height = mask.length / half
  const width = half * 2
  const cells = new Array(width * height).fill(0)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < half; x += 1) {
      let value = mask[y * half + x]
      if (value === 1) value = random() < 0.5 ? 1 : 0
      else if (value === 2) value = random() < 0.5 ? 1 : -1
      cells[y * width + x] = value
      cells[y * width + (width - 1 - x)] = value
    }
  }
  // Outline every empty cell that touches the body.
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (cells[y * width + x] !== 1) continue
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const nx = x + dx
        const ny = y + dy
        if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue
        if (cells[ny * width + nx] === 0) cells[ny * width + nx] = -1
      }
    }
  }
  const hue = Math.floor(random() * 360)
  const accent = (hue + 150 + Math.floor(random() * 60)) % 360
  const pixels = cells.map((cell, index) => {
    if (cell === -1) return `hsl(${hue} 35% 12%)`
    if (cell !== 1) return null
    const y = Math.floor(index / width)
    const shade = 62 - (y / height) * 26 + (random() * 8 - 4)
    const tint = random() < 0.12 ? accent : hue
    return `hsl(${tint} 70% ${shade}%)`
  })
  if (kind === 'hero' || kind === 'enemy') {
    const eyeRow = kind === 'hero' ? 2 : 3
    const eyeX = half - 2
    pixels[eyeRow * width + eyeX] = '#0b0b12'
    pixels[eyeRow * width + (width - 1 - eyeX)] = '#0b0b12'
  }
  return { width, height, pixels }
}

function tilePixels(style, random) {
  const size = 16
  const palette = TILE_STYLES[style] || TILE_STYLES.grass
  const grid = 4
  const lattice = Array.from({ length: grid * grid }, () => random())
  const sample = (x, y) => {
    const gx = (x / size) * grid
    const gy = (y / size) * grid
    const x0 = Math.floor(gx)
    const y0 = Math.floor(gy)
    const fx = gx - x0
    const fy = gy - y0
    const at = (i, j) => lattice[((j + grid) % grid) * grid + ((i + grid) % grid)]
    const top = at(x0, y0) * (1 - fx) + at(x0 + 1, y0) * fx
    const bottom = at(x0, y0 + 1) * (1 - fx) + at(x0 + 1, y0 + 1) * fx
    return top * (1 - fy) + bottom * fy
  }
  const pixels = []
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const value = sample(x, y) * 0.75 + random() * 0.25
      const [h, s, l] = value > 0.62 ? palette[1] : value < 0.35 ? palette[2] : palette[0]
      pixels.push(`hsl(${h} ${s}% ${l}%)`)
    }
  }
  return { width: size, height: size, pixels }
}

export function generateSprite(kind, seed = Math.floor(Math.random() * 2 ** 31), tileStyle = 'grass') {
  const random = rng(seed)
  const art = kind === 'tile' ? tilePixels(tileStyle, random) : characterPixels(kind, random)
  const scale = kind === 'tile' ? 4 : 5
  return {
    dataUrl: toDataUrl(art.width, art.height, art.pixels, scale),
    width: art.width * scale,
    height: art.height * scale,
  }
}

// Shrink an uploaded picture so the whole asset set stays small enough to
// hand to every game.
export async function imageFileToDataUrl(file, maxSize = 256) {
  const url = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('That file could not be read.'))
    reader.readAsDataURL(file)
  })
  const image = await new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('That file is not an image this browser can open.'))
    img.src = url
  })
  const scale = Math.min(1, maxSize / Math.max(image.width, image.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(image.width * scale))
  canvas.height = Math.max(1, Math.round(image.height * scale))
  canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height)
  return { dataUrl: canvas.toDataURL('image/png'), width: canvas.width, height: canvas.height }
}
