import { ZZFX } from './zzfx.js'

// ZzFX parameter arrays. Holes are written as null so they survive JSON;
// playSound turns them back into "use the default".
export const SOUND_PRESETS = {
  coin: [null, null, 1675, null, 0.06, 0.24, 1, 1.82, null, null, 837, 0.06],
  jump: [null, null, 150, 0.03, 0.05, 0.18, null, 1.4, 12, null, null, null, null, 0.4],
  hit: [null, null, 90, null, 0.01, 0.12, 4, 2.2, null, null, null, null, null, 9, 50, 0.2],
  laser: [null, null, 925, 0.04, 0.3, 0.2, 1, 0.3, null, 6.27, -184, 0.09, 0.17],
  powerup: [null, null, 300, 0.04, 0.12, 0.35, null, 1.3, null, null, 420, 0.06, 0.1],
  explosion: [null, null, 333, 0.01, 0, 0.9, 4, 1.9, null, null, null, null, null, 0.5, null, 0.6],
}

export function normalizeParams(params) {
  return Array.from(params || [], (value) => (value == null ? undefined : value))
}

export function playSound(params) {
  try {
    ZZFX.audioContext.resume?.()
    ZZFX.play(...normalizeParams(params))
  } catch {
    // Audio can be unavailable (no device, blocked context); sound is optional.
  }
}

// A small random variation of a preset: pitch, length, and a little texture.
export function varySound(params) {
  const next = [...params]
  const jitter = (value, spread) => Math.round((value ?? 0) * (1 + (Math.random() * 2 - 1) * spread) * 1000) / 1000
  next[2] = Math.max(20, jitter(next[2] ?? 220, 0.45))
  next[5] = Math.max(0.02, jitter(next[5] ?? 0.1, 0.4))
  if (Math.random() < 0.4) next[7] = jitter(next[7] ?? 1, 0.3)
  return next
}
