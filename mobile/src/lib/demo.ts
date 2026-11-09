// Made-up people, shaped like the real store, for when no soloyolo is reachable
// (Expo Go on a phone away from the Mac, or the web preview). Marks change it in memory.
import type { Item, Mark, Message, Person, PersonSummary, Status, TodaySummary } from './types'
import { isOpen } from './types'

const now = () => Date.now() / 1000
const H = 3600
const D = 86400

type P = { id: number; name: string; networks: string[]; score: number; lastAgo: number; attrs: [string, string][]; muted?: boolean }

const PEOPLE: P[] = [
  { id: 1, name: 'Rohan Mehta', networks: ['whatsapp'], score: 64, lastAgo: 3 * H, attrs: [['city', 'Gurugram']] },
  { id: 2, name: 'Ma', networks: ['whatsapp'], score: 120, lastAgo: 40 * 60, attrs: [] },
  { id: 3, name: 'Priya Nair', networks: ['linkedin', 'whatsapp'], score: 18, lastAgo: 26 * H, attrs: [['company', 'Northwind Labs'], ['position', 'Design Lead']] },
  { id: 4, name: 'Kabir Anand', networks: ['whatsapp', 'instagram'], score: 31, lastAgo: 2 * D, attrs: [] },
  { id: 5, name: 'Arjun Sethi', networks: ['linkedin'], score: 4, lastAgo: 6 * D, attrs: [['company', 'Quill'], ['position', 'Founder']] },
  { id: 6, name: 'Meera Iyer', networks: ['instagram'], score: 9, lastAgo: 4 * D, attrs: [] },
  { id: 7, name: 'Tanvi Rao', networks: ['x'], score: 3, lastAgo: 9 * D, attrs: [['x', '@tanvibuilds']] },
  { id: 8, name: 'Sector 72 flat owner', networks: ['whatsapp'], score: 6, lastAgo: 12 * D, attrs: [] },
  { id: 9, name: 'Nova (AI assistant)', networks: ['whatsapp'], score: 40, lastAgo: H, attrs: [], muted: true },
]

let seq = 100
function it(pid: number, owner: 'me' | 'them', action: string, src: string, agoS: number, live: boolean, reasons: string[],
            kind: 'promise' | 'ask' = 'promise'): Item {
  const p = PEOPLE.find((x) => x.id === pid)!
  return {
    person_id: pid, name: p.name, networks: p.networks, source_message_id: ++seq, owner, kind, action, due: null,
    status: 'open', source_ts: now() - agoS, source_text: src, resolved_by: null, snoozed: false, dismissed: false, live, reasons,
  }
}

function fresh(): Item[] {
  seq = 100
  return [
    it(1, 'me', 'Send Rohan the rent agreement scan', 'Agreement ka scan bhej dena kal tak, broker maang raha hai', 2 * D, true, ['asked again 3h ago', 'due tomorrow']),
    it(2, 'me', 'Book Ma’s train ticket for the 21st', '21 ki ticket kara dena beta, Rajdhani mil jaye toh', D, true, ['said yesterday', 'close']),
    it(3, 'them', 'Share the hiring manager’s email', 'I’ll dig out Anand’s email and send it over this week', 3 * D, true, ['overdue 1d']),
    it(4, 'me', 'Return Kabir’s tripod', 'Tripod Sunday tak wapas kar dena', 9 * D, false, ['9 days']),
    it(5, 'me', 'Send Arjun your portfolio link', 'Would love to see your work, can you share a link?', 6 * D, false, ['6 days'], 'ask'),
    it(6, 'them', 'Send the list of cafes in Hauz Khas', 'will send you the list tonight!!', 4 * D, false, ['4 days']),
    it(7, 'me', 'Reply to Tanvi about the beta invite', 'any chance you could take a look at the beta this week?', 9 * D, false, ['9 days'], 'ask'),
    it(8, 'me', 'Pay ₹14,500 rent for November', 'Rent 14,500 by 5th please', 12 * D, false, ['12 days', 'money']),
    it(2, 'me', 'Call Mausi about the wedding dates', 'Mausi ko phone kar lena, dates confirm karni hai', 16 * D, false, ['16 days', 'close']),
  ]
}

let items = fresh()
const original = new Map(items.map((c) => [c.source_message_id, { ...c }]))

const THREADS: Record<number, [number, boolean, string][]> = {
  1: [[3 * D, false, 'Bhai flat wale ne agreement maanga hai'], [2 * D, false, 'Agreement ka scan bhej dena kal tak, broker maang raha hai'],
      [2 * D - 600, true, 'haan bhejta hoon'], [3 * H, false, 'bhai scan??']],
  2: [[16 * D, false, 'Mausi ko phone kar lena, dates confirm karni hai'], [D + 400, false, 'Diwali ke baad aa rahe ho na?'],
      [D, false, '21 ki ticket kara dena beta, Rajdhani mil jaye toh'], [D - 300, true, 'ok ma, aaj dekhta hoon'], [40 * 60, false, '[call]']],
  3: [[4 * D, true, 'Hi Priya! Saw the Design Lead opening at Northwind, would love an intro to whoever is hiring'],
      [3 * D, false, 'Of course! I’ll dig out Anand’s email and send it over this week'], [3 * D - 900, true, 'Thank you so much 🙏']],
}

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
               commitments: items.filter((c) => c.person_id === p.id) } satisfies Person as T
    }
    m = path.match(/^\/api\/thread\/(\d+)$/)
    if (m) {
      const mine = items.filter((c) => c.person_id === Number(m![1]))
      return (THREADS[Number(m[1])] ?? []).map(([a, me, text], i) => ({
        id: mine.find((c) => c.source_text === text)?.source_message_id ?? 9000 + i, ts: now() - a, from_me: me, text,
      })) satisfies Message[] as T
    }
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
      resolved_by: 'you', status: state === 'done' ? 'done' : 'open', dismissed: state === 'dismissed', snoozed: state === 'snoozed',
      live: state === 'open' ? true : it.live,
      reasons: state === 'open' && !it.reasons?.includes('you kept it on') ? ['you kept it on', ...(it.reasons ?? [])] : it.reasons,
    })
  },

  async mute(personId: number, on: boolean): Promise<void> {
    const p = PEOPLE.find((x) => x.id === personId)
    if (p) p.muted = on
  },
}
