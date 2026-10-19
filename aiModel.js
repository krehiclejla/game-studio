// Every chat the studio opens must run on a provider the person can actually use.
// - Möbius's model list includes providers that are not signed in (Claude and
//   Codex appear without a subscription), so it is filtered by provider status.
// - A chat that names no model falls to Möbius's own default, which can land on
//   a disconnected Claude ("Not signed in"), so picks are explicit.
// - Möbius models count as connected even with no credits left, and apps cannot
//   see the balance, so they are the last resort: only when neither Claude nor
//   Codex is connected.
// - A chat keeps the provider it started on. A saved or scoped chat stuck on a
//   provider that is no longer connected is replaced (keepsChat / scopeFor).
const FAMILIES = {
  quick: [/^claude-haiku/, /^claude-sonnet/, /^gpt-.*-mini$/, /^gpt-5\.6-terra$/, /^gpt-/, /^evolve$/],
  creative: [/^claude-opus-5-5$/, /^claude-opus/, /^claude-sonnet/, /^gpt-5\.6-sol$/, /^gpt-/, /^evolve$/],
}
const LAST_RESORT_PROVIDER = 'mobius'

let token = ''
let registry = null

export function setModelToken(value) {
  if (value && value !== token) { token = value; registry = null }
}

const getJson = (path) => fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))

// { known, byProvider: { provider: [model ids] } } for providers that are signed in
// and switched on. When the status check fails (known: false), keep every provider.
function available() {
  registry ||= Promise.all([getJson('/api/models'), getJson('/api/auth/providers/status').catch(() => null)])
    .then(([models, status]) => {
      const byProvider = {}
      for (const [provider, list] of Object.entries(models?.providers || {})) {
        const state = status?.[provider]
        if (status && !(state?.configured && state?.available !== false)) continue
        byProvider[provider] = (list || []).filter((m) => m && m.available !== false).map((m) => String(m.id))
      }
      return { known: !!status, byProvider }
    })
    .catch(() => { registry = null; return { known: false, byProvider: {} } })
  return registry
}

async function usable(provider) {
  const { known, byProvider } = await available()
  return !known || !provider || provider in byProvider
}

// Spread into window.mobius.chat.start options: `...(await modelFor('quick'))`.
export async function modelFor(kind) {
  const { byProvider } = await available()
  for (const family of FAMILIES[kind] || []) {
    for (const [provider, ids] of Object.entries(byProvider)) {
      const id = ids.find((candidate) => family.test(candidate))
      if (id) return { model: id, provider }
    }
  }
  const fallback = byProvider[LAST_RESORT_PROVIDER]?.[0]
  return fallback ? { model: fallback, provider: LAST_RESORT_PROVIDER } : {}
}

async function appChats(scope) {
  return getJson(`/api/app-chats${scope ? `?scope=${encodeURIComponent(scope)}` : ''}`).catch(() => null)
}

// Whether a saved chat id can keep going. Unknown (lookup failed or chat gone)
// counts as yes, so a hiccup never throws away a working conversation.
export async function keepsChat(id) {
  if (!id) return false
  const chat = (await appChats())?.find((c) => c.id === id)
  return !chat || await usable(chat.provider)
}

// Options for an embedded chat saved under `key`: a usable saved chat is kept as
// is (re-sending a model from another provider would be refused); a stuck one is
// forgotten so a new chat starts on the picked model.
export async function embedOptions(key, kind) {
  const storage = window.mobius?.storage
  const saved = await Promise.resolve(storage?.get(key)).catch(() => null)
  if (saved?.id) {
    if (await keepsChat(saved.id)) return {}
    await Promise.resolve(storage?.remove(key)).catch(() => {})
  }
  return modelFor(kind)
}

// The scope for a reusable scoped chat: `scope` itself, unless its chat is stuck on
// a provider that is no longer connected; then one per picked provider.
export async function scopeFor(scope, pick) {
  const chat = (await appChats(scope))?.[0]
  if (!chat || !pick?.provider || chat.provider === pick.provider || await usable(chat.provider)) return scope
  return `${scope}@${pick.provider}`
}
