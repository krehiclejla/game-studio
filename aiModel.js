// Background helpers must run on a model the person actually has. Möbius lists
// only the providers they connected, so pick the preferred family from that list;
// when none of it is there, leave the model out and the chat uses their default.
const FAMILIES = {
  quick: [/^claude-haiku/, /^claude-sonnet/, /^gpt-.*-mini$/],
  creative: [/^claude-opus-5-5$/, /^claude-opus/, /^claude-sonnet/],
}

let token = ''
let registry = null

export function setModelToken(value) {
  if (value && value !== token) { token = value; registry = null }
}

function available() {
  registry ||= fetch('/api/models', { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
    .then((data) => Object.values(data?.providers || {}).flat().filter((m) => m && m.available !== false).map((m) => String(m.id)))
    .catch(() => { registry = null; return [] })
  return registry
}

// Spread into window.mobius.chat.start options: `...(await modelFor('quick'))`.
export async function modelFor(kind) {
  const ids = await available()
  for (const family of FAMILIES[kind] || []) {
    const id = ids.find((candidate) => family.test(candidate))
    if (id) return { model: id }
  }
  return {}
}
