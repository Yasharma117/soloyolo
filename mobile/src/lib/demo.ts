// Made-up people, shaped like the real store, for when no soloyolo is reachable
// (Expo Go on a phone away from the Mac, or the web preview). Marks change it in memory.
import type { Edge, ImportJob, Insight, Item, Mark, MergePair, Message, Person, PersonSummary, SetupStatus, Status, TodaySummary, Week } from './types'
import { isOpen } from './types'

const now = () => Date.now() / 1000
const H = 3600
const D = 86400

type P = { id: number; name: string; networks: string[]; score: number; lastAgo: number; attrs: [string, string][]; muted?: boolean }

let PEOPLE: P[] = [
  { id: 1, name: 'Rohan Mehta', networks: ['whatsapp'], score: 64, lastAgo: 3 * H, attrs: [['city', 'Gurugram']] },
  { id: 2, name: 'Ma', networks: ['whatsapp'], score: 120, lastAgo: 40 * 60, attrs: [] },
  { id: 3, name: 'Priya Nair', networks: ['linkedin', 'whatsapp'], score: 18, lastAgo: 26 * H, attrs: [['company', 'Northwind Labs'], ['position', 'Design Lead']] },
  { id: 4, name: 'Kabir Anand', networks: ['whatsapp', 'instagram'], score: 31, lastAgo: 2 * D, attrs: [] },
  { id: 5, name: 'Arjun Sethi', networks: ['linkedin'], score: 4, lastAgo: 6 * D, attrs: [['company', 'Quill'], ['position', 'Founder']] },
  { id: 6, name: 'Meera Iyer', networks: ['instagram'], score: 9, lastAgo: 4 * D, attrs: [] },
  { id: 7, name: 'Tanvi Rao', networks: ['x'], score: 3, lastAgo: 9 * D, attrs: [['x', '@tanvibuilds']] },
  { id: 8, name: 'Sector 72 flat owner', networks: ['whatsapp'], score: 6, lastAgo: 12 * D, attrs: [] },
  { id: 9, name: 'Nova (AI assistant)', networks: ['whatsapp'], score: 40, lastAgo: H, attrs: [], muted: true },
  // two chats that look like people above: the review queue at /merges
  { id: 10, name: 'Priya N', networks: ['instagram'], score: 2, lastAgo: 11 * D, attrs: [['company', 'Northwind Labs']] },
  { id: 11, name: 'Kabir trek', networks: ['x'], score: 1, lastAgo: 20 * D, attrs: [] },
]

let pairs: { a: number; b: number; score: number; reasons: string[] }[] = [
  { a: 3, b: 10, score: 0.86, reasons: ['name: initial', 'context: northwind labs'] },
  { a: 4, b: 11, score: 0.62, reasons: ['name: first name', 'context: weekend trek'] },
]
const merged: { id: number; gone: P; pair: (typeof pairs)[number] }[] = []
const MESSAGES: Record<number, number> = { 3: 312, 4: 890, 10: 14, 11: 6 }

const EDGES: Omit<Edge, 'src_name' | 'dst_name' | 'ts'>[] = [
  { id: 1, src: 3, dst: 5, kind: 'referred', note: 'forwarding your profile to Arjun at Quill', quote: 'Sent your profile to Arjun too, he runs Quill and is hiring designers' },
  { id: 2, src: 4, dst: 6, kind: 'knows', note: 'treks with Meera', quote: 'Meera bhi aa rahi hai trek pe, usse cafe list le lena' },
]

// what the last week closed, for /week: two by you, one by a bank SMS
const CLOSED: [number, 'me' | 'them', string, string, number, string][] = [
  [1, 'me', 'Send Rohan the broker’s number', 'Broker ka number bhej de', 5 * D, 'you'],
  [6, 'them', 'Send the Goa photos', 'photos kal bhejti hoon pakka', 6 * D, 'you'],
  [8, 'me', 'Pay ₹2,000 for the society maintenance', 'Maintenance 2000 this month', 4 * D, 'sms'],
]

let seq = 100
function it(pid: number, owner: 'me' | 'them', action: string, src: string, agoS: number, live: boolean, reasons: string[],
            kind: 'promise' | 'ask' = 'promise', suggestion: string | null = null): Item {
  const p = PEOPLE.find((x) => x.id === pid)!
  return {
    person_id: pid, name: p.name, networks: p.networks, source_message_id: ++seq, owner, kind, action, due: null,
    status: 'open', source_ts: now() - agoS, source_text: src, resolved_by: null, snoozed: false, dismissed: false, live, reasons, suggestion,
  }
}

function fresh(): Item[] {
  seq = 100
  return [
    it(1, 'me', 'Send Rohan the rent agreement scan', 'Agreement ka scan bhej dena kal tak, broker maang raha hai', 2 * D, true, ['asked again 3h ago', 'due tomorrow']),
    it(2, 'me', 'Book Ma’s train ticket for the 21st', '21 ki ticket kara dena beta, Rajdhani mil jaye toh', D, true, ['said yesterday', 'close']),
    it(3, 'them', 'Share the hiring manager’s email', 'I’ll dig out Anand’s email and send it over this week', 3 * D, true, ['overdue 1d']),
    it(4, 'me', 'Return Kabir’s tripod', 'Tripod Sunday tak wapas kar dena', 9 * D, false, ['9 days'], 'promise',
       'In Weekend trek group, Kabir said “tripod mil gaya, thanks” 2 days ago'),
    it(5, 'me', 'Send Arjun your portfolio link', 'Would love to see your work, can you share a link?', 6 * D, false, ['6 days'], 'ask'),
    it(6, 'them', 'Send the list of cafes in Hauz Khas', 'will send you the list tonight!!', 4 * D, false, ['4 days']),
    it(7, 'me', 'Reply to Tanvi about the beta invite', 'any chance you could take a look at the beta this week?', 9 * D, false, ['9 days'], 'ask'),
    it(8, 'me', 'Pay ₹14,500 rent for November', 'Rent 14,500 by 5th please', 12 * D, false, ['12 days', 'money'], 'promise',
       'Bank SMS: ₹14,500 sent to landlord@ybl on Nov 4'),
    it(2, 'me', 'Call Mausi about the wedding dates', 'Mausi ko phone kar lena, dates confirm karni hai', 16 * D, false, ['16 days', 'close']),
  ]
}

// the demo's dated ones carry the date the way the store does, not only in their reasons
const dated = (list: Item[]) => list.map((c) => (c.action.startsWith('Send Rohan') ? { ...c, due: 'tomorrow' } : c))
let items = dated(fresh())
const original = new Map(items.map((c) => [c.source_message_id, { ...c }]))

const THREADS: Record<number, [number, boolean, string][]> = {
  1: [[3 * D, false, 'Bhai flat wale ne agreement maanga hai'], [2 * D, false, 'Agreement ka scan bhej dena kal tak, broker maang raha hai'],
      [2 * D - 600, true, 'haan bhejta hoon'], [3 * H, false, 'bhai scan??']],
  2: [[16 * D, false, 'Mausi ko phone kar lena, dates confirm karni hai'], [D + 400, false, 'Diwali ke baad aa rahe ho na?'],
      [D, false, '21 ki ticket kara dena beta, Rajdhani mil jaye toh'], [D - 300, true, 'ok ma, aaj dekhta hoon'], [40 * 60, false, '[call]']],
  3: [[4 * D, true, 'Hi Priya! Saw the Design Lead opening at Northwind, would love an intro to whoever is hiring'],
      [3 * D, false, 'Of course! I’ll dig out Anand’s email and send it over this week'], [3 * D - 900, true, 'Thank you so much 🙏']],
}

// Setting up in the demo: nothing is linked or read, it only walks through the states on a timer so the
// screens can be seen. The real thing is spike/setup.py.
const DEMO_EXPORT = 'Complete_LinkedInDataExport_11-02-2026.zip'
const setupState: { wa: SetupStatus['whatsapp']; at: number; job: (ImportJob & { at: number }) | null } = {
  wa: { state: 'idle', code: null, message: null, linked: false, syncing: false }, at: 0, job: null,
}
function setupNow(): SetupStatus {
  const s = setupState, t = now()
  if (s.wa.state === 'starting' && t - s.at > 1.5) s.wa = { ...s.wa, state: 'code', code: 'K7QM-2XPD' }
  if (s.wa.state === 'code' && t - s.at > 9) s.wa = { state: 'linked', code: null, message: null, linked: true, syncing: true }
  if (s.job && s.job.state === 'reading' && t - s.job.at > 2) Object.assign(s.job, { state: 'saving', found: '64 people', notes: ['messages.csv: 780 rows'] })
  if (s.job && s.job.state === 'saving' && t - s.job.at > 4.5)
    Object.assign(s.job, { state: 'done', summary: '312 new messages from 64 threads, 0 new group lines, 210 connections (640 new attributes)' })
  return { ready: true, whatsapp: s.wa, exports: [{ file: DEMO_EXPORT, network: 'linkedin', size: 4_200_000, modified: t - 3600, job: s.job }] }
}

const named = (id: number) => PEOPLE.find((p) => p.id === id)?.name
const visible = () => items.filter((c) => !PEOPLE.find((p) => p.id === c.person_id)!.muted)

export const demo = {
  async get<T>(path: string): Promise<T> {
    const open = visible().filter(isOpen)
    if (path === '/api/today') {
      const live = open.filter((c) => c.live)
      return { today: live.slice(0, 3), live: live.length, quiet: open.length - live.length, open: open.length } satisfies TodaySummary as T
    }
    if (path === '/api/all') return [...open.filter((c) => c.live), ...open.filter((c) => !c.live)] as T
    if (path === '/api/people')
      return PEOPLE.map((p) => ({ id: p.id, name: p.name, score: p.score, last: now() - p.lastAgo, networks: p.networks, muted: !!p.muted,
                                  commitments: items.filter((c) => c.person_id === p.id) })) satisfies PersonSummary[] as T
    let m = path.match(/^\/api\/person\/(\d+)$/)
    if (m) {
      const p = PEOPLE.find((x) => x.id === Number(m![1]))
      if (!p) throw new Error('No such person')
      return { id: p.id, name: p.name, score: p.score, last: now() - p.lastAgo, networks: p.networks, muted: !!p.muted,
               handles: p.networks.map((n) => ({ network: n, address: n === 'whatsapp' ? `+91 98xxx xx${40 + p.id}` : 'from export' })),
               attributes: p.attrs.map(([key, value]) => ({ key, value, source: 'demo' })),
               edges: EDGES.filter((e) => e.src === p.id || e.dst === p.id).filter((e) => named(e.src) && named(e.dst))
                 .map((e) => ({ ...e, src_name: named(e.src)!, dst_name: named(e.dst)!, ts: now() - 3 * D })),
               commitments: items.filter((c) => c.person_id === p.id) } satisfies Person as T
    }
    if (path === '/api/setup') return setupNow() as T
    if (path === '/api/merges') {
      const who = (id: number) => {
        const p = PEOPLE.find((x) => x.id === id)!
        return { id, name: p.name, networks: p.networks, messages: MESSAGES[id] ?? 0, detail: p.attrs[0]?.[1] ?? null }
      }
      return pairs.map((x) => ({ a: who(x.a), b: who(x.b), score: x.score, reasons: x.reasons })) satisfies MergePair[] as T
    }
    if (path === '/api/week') {
      const closed = CLOSED.map(([pid, owner, action, src, agoS, by], i): Item & { by: string } => ({
        person_id: pid, name: named(pid) ?? '', networks: PEOPLE.find((x) => x.id === pid)?.networks, source_message_id: 200 + i, owner, kind: 'promise',
        action, due: null, status: 'done', source_ts: now() - agoS, source_text: src, resolved_by: by, snoozed: false, dismissed: false, by }))
      const yours = visible().filter((c) => c.status === 'done' && c.resolved_by === 'you')
      return { since: now() - 7 * D, done: [...yours, ...closed.filter((c) => c.by === 'you')], settled: closed.filter((c) => c.by !== 'you'),
               quiet: open.filter((c) => !c.live) } satisfies Week as T
    }
    m = path.match(/^\/api\/thread\/(\d+)$/)
    if (m) {
      const mine = items.filter((c) => c.person_id === Number(m![1]))
      return (THREADS[Number(m[1])] ?? []).map(([a, me, text], i) => ({
        id: mine.find((c) => c.source_text === text)?.source_message_id ?? 9000 + i, ts: now() - a, from_me: me, text,
      })) satisfies Message[] as T
    }
    if (path === '/api/insight')
      return { days: 30, closed: { by_you: 9, by_signal: 3 }, why: { off_chat: 6, not_needed: 2, let_go: 1, misread: 0 } } satisfies Insight as T
    if (path === '/api/status')
      return {
        networks: [{ network: 'whatsapp', messages: 5602, last: now() - 240 }, { network: 'linkedin', messages: 312, last: now() - 2 * D }],
        groups: [{ source: 'whatsapp-group', lines: 5403, last: now() - 600 }],
        telegram: true, last_read: now() - 18 * 60,
        disclosures: ['claude (claude code)', 'telegram (morning message)'],
        muted: PEOPLE.filter((p) => p.muted).map((p) => ({ id: p.id, name: p.name })),
      } satisfies Status as T
    throw new Error(`Not in the demo: ${path}`)
  },

  async mark(c: Item, state: Mark): Promise<void> {
    const it = items.find((x) => x.source_message_id === c.source_message_id && x.owner === c.owner)
    if (!it) return
    if (state === 'clear') return void Object.assign(it, original.get(it.source_message_id))
    Object.assign(it, {
      suggestion: null,
      resolved_by: 'you', status: state === 'done' ? 'done' : 'open', dismissed: state === 'dismissed', snoozed: state === 'snoozed',
      live: state === 'open' ? true : it.live,
      reasons: state === 'open' && !it.reasons?.includes('you kept it on') ? ['you kept it on', ...(it.reasons ?? [])] : it.reasons,
    })
  },

  setup(what: 'whatsapp' | 'sync' | 'import', body: { phone?: string; file?: string }): void {
    if (what === 'whatsapp') {
      if (!/^\d{8,15}$/.test((body.phone ?? '').replace(/[\s+()-]/g, ''))) throw new Error('Enter your number with the country code, digits only, like 919800000000.')
      Object.assign(setupState, { wa: { state: 'starting', code: null, message: null, linked: false, syncing: false }, at: now() })
    } else if (what === 'import') {
      setupState.job = { file: DEMO_EXPORT, network: 'linkedin', state: 'reading', found: null, summary: null, notes: [], error: null, at: now() }
    }
  },

  /** Same: the smaller chat folds into the bigger one. Different: the pair is never asked again. */
  async merge(a: number, b: number, same: boolean): Promise<number | null> {
    const pair = pairs.find((x) => (x.a === a && x.b === b) || (x.a === b && x.b === a))
    if (!pair) throw new Error('No such suggestion')
    pairs = pairs.filter((x) => x !== pair)
    if (!same) return null
    const gone = PEOPLE.find((p) => p.id === pair.b)!
    PEOPLE = PEOPLE.filter((p) => p !== gone)
    merged.push({ id: merged.length + 1, gone, pair })
    return merged.length
  },

  async undoMerge(id: number): Promise<void> {
    const m = merged.find((x) => x.id === id)
    if (m && !PEOPLE.includes(m.gone)) PEOPLE = [...PEOPLE, m.gone] // split apart again, and not asked again
  },

  async mute(personId: number, on: boolean): Promise<void> {
    const p = PEOPLE.find((x) => x.id === personId)
    if (p) p.muted = on
  },
}
