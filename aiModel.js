// Every chat the studio opens names a model the person can actually use.
// Möbius's model list includes providers that are not signed in (Claude and
// Codex appear even without a subscription), so filter it by the provider
// status first. A chat that names no model falls to Möbius's own default, which
// can land on a disconnected Claude ("Not signed in") for people who only use
// Möbius models, so prefer an explicit pick whenever one is connected.
const FAMILIES = {
  quick: [/^claude-haiku/, /^claude-sonnet/, /^gpt-.*-mini$/, /^evolve$/],
  creative: [/^claude-opus-5-5$/, /^claude-opus/, /^claude-sonnet/, /^evolve$/],
}
// Möbius models are the last resort: when nothing preferred is connected but
// they are, any Möbius model beats an unsigned-in default.
const LAST_RESORT_PROVIDER = 'mobius'

let token = ''
let registry = null

export function setModelToken(value) {
  if (value && value !== token) { token = value; registry = null }
}

const getJson = (path) => fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))

// { provider: [model ids] } for providers that are signed in and switched on.
// When the status check itself fails, keep the full list rather than none.
function available() {
  registry ||= Promise.all([getJson('/api/models'), getJson('/api/auth/providers/status').catch(() => null)])
    .then(([models, status]) => {
      const out = {}
      for (const [provider, list] of Object.entries(models?.providers || {})) {
        const state = status?.[provider]
        if (status && !(state?.configured && state?.available !== false)) continue
        out[provider] = (list || []).filter((m) => m && m.available !== false).map((m) => String(m.id))
      }
      return out
    })
    .catch(() => { registry = null; return {} })
  return registry
}

// Spread into window.mobius.chat.start options: `...(await modelFor('quick'))`.
export async function modelFor(kind) {
  const byProvider = await available()
  const ids = Object.values(byProvider).flat()
  for (const family of FAMILIES[kind] || []) {
    const id = ids.find((candidate) => family.test(candidate))
    if (id) return { model: id }
  }
  const fallback = byProvider[LAST_RESORT_PROVIDER]?.[0]
  return fallback ? { model: fallback } : {}
}
