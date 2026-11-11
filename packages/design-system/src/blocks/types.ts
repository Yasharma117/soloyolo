/** What a block needs to draw a promise. The app's own item type is a superset of this. */
export type PromiseItem = {
  name: string
  owner: 'me' | 'them'
  kind: 'promise' | 'ask'
  action: string
  source_text?: string | null
  source_ts: number
  networks?: string[]
  reasons?: string[]
  due?: string | null
  /** What a bank SMS or a group chat says about it being settled. Shown, never acted on without you. */
  suggestion?: string | null
}

export function ago(ts: number, now = Date.now() / 1000): string {
  const s = now - ts
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m`
  if (s < 86400) return `${Math.round(s / 3600)}h`
  if (s < 86400 * 30) return `${Math.round(s / 86400)}d`
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}
