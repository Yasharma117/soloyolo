// One data layer for every screen. It talks to `python -m spike serve` on your Mac when it can
// reach it, and otherwise to the made-up demo, and says which.
//
// The iOS Simulator shares the Mac's network, so 127.0.0.1:8765 reaches the server directly.
// In a browser on the Mac, open http://127.0.0.1:8765 (scripts/build-app.sh builds the app the server serves).
// A phone can't (the server only listens on the Mac itself); set EXPO_PUBLIC_SOLOYOLO_URL once
// there's a private route to the Mac (Tailscale), until then a phone shows the demo.
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { demo } from './demo'
import type { ReasonKey } from './reasons'
import type { Item, Mark } from './types'

// In a browser the app is served by soloyolo itself (spike/server.py), so the server is wherever the page came from.
const here = typeof window !== 'undefined' && window.location?.origin?.startsWith('http') ? window.location.origin : null
const BASE = (process.env.EXPO_PUBLIC_SOLOYOLO_URL ?? here ?? 'http://127.0.0.1:8765').replace(/\/$/, '')

export type Mode = 'checking' | 'live' | 'demo'

let mode: Mode = 'checking'
let version = 0
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

async function probe(): Promise<void> {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), 1500)
  try {
    const r = await fetch(`${BASE}/api/today`, { signal: ctl.signal })
    mode = r.ok && (r.headers.get('content-type') ?? '').includes('json') ? 'live' : 'demo'
  } catch {
    mode = 'demo'
  } finally {
    clearTimeout(timer)
  }
  emit()
}
const ready = probe()

async function get<T>(path: string): Promise<T> {
  await ready
  if (mode !== 'live') return demo.get<T>(path)
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return (await r.json()) as T
}

async function post<T = unknown>(path: string, body: object): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(await r.text())
  return (await r.json()) as T
}

/** `reason` only after Not needed; `days` only for a snooze (1 to 60, default 3). */
export async function mark(c: Item, state: Mark, reason?: ReasonKey, days = 3): Promise<void> {
  await ready
  if (mode === 'live') {
    const body: Record<string, unknown> = { person_id: c.person_id, source_message_id: c.source_message_id, owner: c.owner, state }
    if (state === 'snoozed') body.days = days
    if (reason) body.reason = reason
    await post('/api/mark', body)
  } else {
    await demo.mark(c, reason === 'off_chat' ? 'done' : state)
  }
  version++
  emit()
}

export async function mute(personId: number, on: boolean): Promise<void> {
  await ready
  if (mode === 'live') await post('/api/mute', { person_id: personId, mute: on })
  else await demo.mute(personId, on)
  version++
  emit()
}

/** Your answer to "same person?". A yes returns the merge's id, which `undoMerge` takes back. */
export async function decideMerge(a: number, b: number, same: boolean): Promise<number | null> {
  await ready
  const id = mode === 'live' ? (await post<{ log_id?: number }>('/api/merge', { a, b, same })).log_id ?? null : await demo.merge(a, b, same)
  version++
  emit()
  return id
}

export async function undoMerge(logId: number): Promise<void> {
  await ready
  if (mode === 'live') await post('/api/merge/undo', { log_id: logId })
  else await demo.undoMerge(logId)
  version++
  emit()
}

/** Setting up from the app: ask WhatsApp for a pairing code, start syncing, or read an export from Downloads.
 *  Each returns at once; the progress is in /api/setup, which the screen reloads while something is running. */
export async function setupAct(what: 'whatsapp' | 'sync' | 'import' | 'read', body: { phone?: string; file?: string; extractor?: string } = {}): Promise<void> {
  await ready
  if (mode === 'live') await post(`/api/setup/${what}`, body)
  else demo.setup(what, body)
  version++
  emit()
}

export function refresh(): void {
  version++
  emit()
}

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function useMode(): Mode {
  return useSyncExternalStore(subscribe, () => mode)
}

/** Load a path; reloads after any mark, mute or refresh. */
export function useData<T>(path: string) {
  const v = useSyncExternalStore(subscribe, () => version)
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true })
  const load = useCallback(() => {
    let live = true
    get<T>(path)
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((e: Error) => live && setState((s) => ({ ...s, error: e.message, loading: false })))
    return () => { live = false }
  }, [path])
  useEffect(load, [load, v])
  return state
}

export const serverUrl = BASE
