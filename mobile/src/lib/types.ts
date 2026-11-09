// The shapes `python -m spike serve` returns (spike/server.py). The demo returns the same.

export type Owner = 'me' | 'them'

export type Item = {
  person_id: number
  name: string
  networks?: string[]
  source_message_id: number
  owner: Owner
  kind: 'promise' | 'ask'
  action: string
  due: string | null
  status: 'open' | 'done'
  source_ts: number
  source_text: string | null
  resolved_by: string | null
  snoozed: boolean
  dismissed: boolean
  suggestion?: string | null
  live?: boolean
  reasons?: string[]
}

export type TodaySummary = { today: Item[]; live: number; quiet: number; open: number }

export type PersonSummary = {
  id: number
  name: string
  score: number
  last: number
  networks: string[]
  muted?: boolean
  commitments: Item[]
}

export type Person = PersonSummary & {
  handles: { network: string; address: string }[]
  attributes: { key: string; value: string; source: string }[]
}

export type Message = { id: number; ts: number; from_me: number | boolean; text: string }

export type Status = {
  networks: { network: string; messages: number; last: number }[]
  groups: { source: string; lines: number; last: number }[]
  telegram: boolean
  last_read: number | null
  disclosures: string[]
  muted: { id: number; name: string }[]
}

export type Mark = 'done' | 'dismissed' | 'open' | 'snoozed' | 'clear'

export const isOpen = (c: Item) => c.status === 'open' && !c.snoozed && !c.dismissed
export const keyOf = (c: Item) => `${c.person_id}:${c.source_message_id}:${c.owner}`

export function ago(ts: number): string {
  const s = Date.now() / 1000 - ts
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m`
  if (s < 86400) return `${Math.round(s / 3600)}h`
  if (s < 86400 * 30) return `${Math.round(s / 86400)}d`
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export const HOT = /^(due|overdue)|again|chased/i
