// One way to show numbers, money and time everywhere (UX writing: "Apr 11, 2025", "2 hours ago"
// under a day, "1.2K"). Screens never format by hand.

const locale = 'en-IN'

export function formatINR(amount: number): string {
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'INR', maximumFractionDigits: amount % 1 ? 2 : 0 }).format(amount)
}

export function formatCount(n: number): string {
  return n.toLocaleString(locale)
}

/** 1.2K, 15.4M. */
export function formatCompact(n: number): string {
  if (n < 1000) return String(n)
  const [d, s] = n < 1e6 ? [1e3, 'K'] : n < 1e9 ? [1e6, 'M'] : [1e9, 'B']
  const v = n / d
  return `${v >= 100 ? Math.round(v) : Math.round(v * 10) / 10}${s}`
}

/** "Apr 11, 2025", or "Apr 11" this year. */
export function formatDate(ts: number, now = Date.now() / 1000): string {
  const d = new Date(ts * 1000), y = new Date(now * 1000).getFullYear()
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', ...(d.getFullYear() !== y && { year: 'numeric' }) })
}

/** "4 min ago", "2 hours ago" under a day; the date after that. */
export function formatRelative(ts: number, now = Date.now() / 1000): string {
  const s = Math.max(0, now - ts)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) { const h = Math.round(s / 3600); return `${h} ${h === 1 ? 'hour' : 'hours'} ago` }
  return formatDate(ts, now)
}
