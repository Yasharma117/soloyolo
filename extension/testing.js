// For the tests: a pretend browser. Cookies come from a map; fetch answers from fixtures by URL and records every call.
import { readFileSync } from 'node:fs'

export const fixture = (name) => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url)))

export function browser(cookies, answer) {
  const calls = []
  globalThis.chrome = { cookies: { get: async ({ name }) => (name in cookies ? { value: cookies[name] } : null) } }
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), method: init.method || 'GET', headers: init.headers || {} })
    const body = answer(String(url))
    if (typeof body === 'number') return { ok: false, status: body, json: async () => ({}) }
    return { ok: true, status: 200, json: async () => structuredClone(body) }
  }
  return calls
}

export const opts = { since: 0, maxPages: 5, pause: async () => {} }
