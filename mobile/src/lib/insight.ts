// Turns /api/insight's numbers into the one thing worth saying this week. The server counts; the words live here.
// Nothing is said until there's enough to say it honestly: five closed and three reasons at least.
import type { Insight } from './types'

export type Said = { label: string; headline: string; body: string }

export function sayInsight(i: Insight | null | undefined): Said | null {
  if (!i) return null
  const closed = i.closed.by_you + i.closed.by_signal
  const answered = i.why.off_chat + i.why.not_needed + i.why.let_go + i.why.misread
  if (closed < 5) return null
  if (answered >= 3 && i.why.off_chat * 2 >= answered)
    return { label: 'What closes your promises', headline: 'Most close off the chat',
             body: `${i.why.off_chat} of the ${answered} you told us about were done somewhere soloyolo can’t read. That’s why quiet ones count as done.` }
  if (answered >= 3 && i.why.misread * 3 >= answered)
    return { label: 'How soloyolo is reading', headline: 'Some weren’t promises',
             body: `${i.why.misread} of the ${answered} you dismissed were never real promises. Each one you mark teaches the next read.` }
  if (i.closed.by_signal >= 2)
    return { label: `The last ${i.days} days`, headline: 'Closed without asking you',
             body: `${i.closed.by_signal} settled from a bank SMS or a group chat, and you confirmed each. ${i.closed.by_you} you closed yourself.` }
  return { label: `The last ${i.days} days`, headline: `${closed} kept`, body: 'Everything you said you’d do and did, counted whether or not the chat said so.' }
}
