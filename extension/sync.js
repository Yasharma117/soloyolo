// What every network shares: the error type, the pacing, and the one loop that reads a network and hands what's
// new to soloyolo. A network is a module (linkedin.js, instagram.js, x.js) with the same shape:
//
//   id, label, BASE, rule, limits { days, pages }
//   session()                       -> ctx { account, me: { id, name, username }, ... }; throws when signed out
//   changed(ctx, state, opts)       -> { conversations: [{ id, at, raw }], cursor }: what moved since state.cursor
//   fetch(ctx, conv, after, opts)   -> one conversation in soloyolo's shape (spike/live.py), messages newer than `after`
//
// Modules only read. Nothing here or there sends, reacts, types or marks anything read.

export class NetworkError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.status = status
  }
}

/** An answer that isn't shaped the way the module expects. The sync stops; it never guesses or retries. */
export const shape = (label, what) => new NetworkError(`${label}'s answer has no ${what} in it: the site may have changed, and extension/README.md says what to update`)

/** 1.5 to 4 seconds, a person's pace. Every request to a network waits this long first. */
export const pause = () => new Promise((r) => setTimeout(r, 1500 + Math.random() * 2500))

export const BATCH = 25 // conversations per post to the server

/** After a network's sync stops, when it may run by itself again: 1 hour, doubling to a day. Sync now ignores it. */
export const retryAfter = (failures, now = Date.now()) => now + Math.min(24, 2 ** Math.max(0, failures - 1)) * 3600e3

/**
 * One sync of one network. `post` sends a batch to soloyolo and throws if it wasn't stored; `save` persists state.
 * A conversation is remembered as synced, and the network's cursor moved on, only after soloyolo stored it, so a
 * run that stops halfway is picked up by the next one.
 */
export async function runNetwork(mod, { state, post, save, wait = pause, now = Date.now }) {
  const ctx = await mod.session()
  let st = { cursor: '', seen: {}, ...state }
  if (st.me && st.me !== ctx.account) st = { cursor: '', seen: {} } // a different account
  st.me = ctx.account
  const since = now() - mod.limits.days * 86400e3
  const opts = { since, maxPages: mod.limits.pages, pause: wait }
  await wait()
  const { conversations, cursor } = await mod.changed(ctx, st, opts)
  const fresh = conversations.filter((c) => c.id && c.at > (st.seen[c.id] || since))
  let sent = 0
  let summary = ''
  for (let i = 0; i < fresh.length; i += BATCH) {
    const slice = fresh.slice(i, i + BATCH)
    const batch = []
    for (const c of slice) batch.push(await mod.fetch(ctx, c, st.seen[c.id] || since, opts))
    if (!ctx.me?.id) throw shape(mod.label, 'account')
    const out = await post({ network: mod.id, me: ctx.me, conversations: batch })
    summary = out.summary
    // Only now is it safe to remember these as read: soloyolo has them.
    for (const c of slice) st.seen[c.id] = c.at
    sent += batch.length
    await save(st)
  }
  st.cursor = cursor
  await save(st)
  return { you: ctx.me?.name || ctx.me?.username || '', conversations: sent, summary: sent ? summary : 'nothing new' }
}
