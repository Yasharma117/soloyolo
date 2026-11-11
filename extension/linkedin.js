// LinkedIn's own web API, read through the session already open in this browser. Endpoints and query ids follow
// mautrix-linkedin (pkg/linkedingo/constants.go, read 2026-11-10); LinkedIn changes them, so they live in one place.
import { NetworkError, shape } from './sync.js'

export const id = 'linkedin'
export const label = 'LinkedIn'
export const BASE = 'https://www.linkedin.com'
// LinkedIn checks where a request comes from; ours come from the extension, so present them as the messaging page.
export const rule = { urlFilter: '||www.linkedin.com/voyager/', origin: BASE, referer: `${BASE}/messaging/` }
export const limits = { days: 90, pages: 5 } // first sync: 90 days back, 100 conversations and 100 messages each at most

const GRAPHQL = `${BASE}/voyager/api/voyagerMessagingGraphQL/graphql`
const ME = `${BASE}/voyager/api/me`
export const QUERY = {
  conversations: 'messengerConversations.0d5e6781bbee71c3e51c8843c6519f48',
  conversationsSince: 'messengerConversations.74c17e85611b60b7ba2700481151a316',
  conversationsBefore: 'messengerConversations.9501074288a12f3ae9e3c7ea243bccbf',
  messagesBefore: 'messengerMessages.d8ea76885a52fd5dc5c317078ab7c977',
}

/** The csrf token LinkedIn expects is the JSESSIONID cookie's value, without its quotes. */
async function csrfToken() {
  const c = await chrome.cookies.get({ url: BASE, name: 'JSESSIONID' })
  if (!c) throw new NetworkError('not signed in to LinkedIn in this browser', 401)
  return c.value.replace(/"/g, '')
}

async function get(url, csrf, accept = 'application/graphql') {
  const res = await fetch(url, {
    credentials: 'include',
    headers: { accept, 'csrf-token': csrf, 'x-restli-protocol-version': '2.0.0', 'accept-language': 'en-US,en;q=0.9' },
  })
  if (res.status === 401 || res.status === 403) throw new NetworkError('LinkedIn session expired: sign in again', res.status)
  if (!res.ok) throw new NetworkError(`LinkedIn answered ${res.status}`, res.status)
  return res.json()
}

// variables=(key:value,...) with urns escaped, as the web app sends them.
const graphql = (queryId, vars) =>
  `${GRAPHQL}?queryId=${queryId}&variables=(${Object.entries(vars).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${k}:${v}`).join(',')})`

/** You, and what the messaging queries need: the csrf token and the fsd_profile urn they're addressed to. */
export async function session() {
  const csrf = await csrfToken()
  const r = await get(ME, csrf, 'application/json')
  const p = r.miniProfile || {}
  const member = (p.dashEntityUrn || '').split(':').pop()
  if (!p.publicIdentifier || !member) throw shape(label, 'profile')
  const url = `${BASE}/in/${p.publicIdentifier}`
  return {
    csrf,
    account: url,
    me: { id: url, name: `${p.firstName || ''} ${p.lastName || ''}`.trim(), username: p.publicIdentifier },
    mailbox: `urn:li:fsd_profile:${member}`,
  }
}

/** Changed conversations since `token` (or the latest page when there's none) and the token to use next time. */
async function conversationsSince(csrf, mailbox, token) {
  const vars = { mailboxUrn: encodeURIComponent(mailbox) }
  if (token) vars.syncToken = token
  const r = await get(graphql(token ? QUERY.conversationsSince : QUERY.conversations, vars), csrf)
  const data = r?.data?.messengerConversationsBySyncToken
  if (!data) throw new NetworkError('no conversations in LinkedIn\'s answer (the sync token may have expired)', 0)
  return { conversations: data.elements || [], token: data.metadata?.newSyncToken || token }
}

/** Up to 20 inbox conversations last active before `beforeMs`, newest first. For the first sync's backfill. */
async function conversationsBefore(csrf, mailbox, beforeMs) {
  const r = await get(graphql(QUERY.conversationsBefore, {
    mailboxUrn: encodeURIComponent(mailbox),
    lastUpdatedBefore: String(beforeMs),
    count: '20',
    query: '(predicateUnions:List((conversationCategoryPredicate:(category:PRIMARY_INBOX))))',
  }), csrf)
  return r?.data?.messengerConversationsByCategoryQuery?.elements || []
}

/** Up to `count` messages delivered before `beforeMs` in one conversation. */
async function messagesBefore(csrf, conversationUrn, beforeMs, count = 20) {
  const r = await get(graphql(QUERY.messagesBefore, {
    deliveredAt: String(beforeMs),
    conversationUrn: encodeURIComponent(conversationUrn),
    countBefore: String(count),
    countAfter: '0',
  }), csrf)
  return r?.data?.messengerMessagesByAnchorTimestamp?.elements || []
}

/** Conversations that changed since the last sync, by LinkedIn's sync token; the first time, the last 90 days. */
export async function changed(ctx, state, { since, maxPages, pause }) {
  let token = state.cursor
  let r
  try {
    r = await conversationsSince(ctx.csrf, ctx.mailbox, token)
  } catch (e) {
    if (!token || e.status === 401 || e.status === 403 || e.status === 429) throw e
    token = '' // an expired sync token: start over from the latest page, once
    await pause()
    r = await conversationsSince(ctx.csrf, ctx.mailbox, '')
  }
  let list = r.conversations
  if (!token) {
    // First sync: the sync token answers only the latest page, so walk back through the inbox for older threads.
    const all = new Map(list.map((c) => [c.entityUrn, c]))
    let oldest = Math.min(...list.map((c) => c.lastActivityAt || Date.now()), Date.now())
    for (let page = 0; page < maxPages && oldest > since; page++) {
      await pause()
      const older = await conversationsBefore(ctx.csrf, ctx.mailbox, oldest)
      if (!older.length) break
      for (const c of older) all.set(c.entityUrn, c)
      oldest = Math.min(...older.map((c) => c.lastActivityAt || oldest))
    }
    list = [...all.values()]
  }
  return { conversations: list.filter((c) => c.entityUrn).map((c) => ({ id: c.entityUrn, at: c.lastActivityAt || 0, raw: c })), cursor: r.token }
}

/** A conversation's messages newer than `after`, newest page first, paging back until it reaches them. */
export async function fetch_(ctx, conv, after, { maxPages, pause }) {
  const out = []
  let before = (conv.at || Date.now()) + 1
  for (let page = 0; page < maxPages; page++) {
    await pause()
    const got = await messagesBefore(ctx.csrf, conv.id, before)
    const newer = got.filter((m) => (m.deliveredAt || 0) > after)
    out.push(...newer)
    if (got.length < 20 || newer.length < got.length) break
    before = Math.min(...got.map((m) => m.deliveredAt || before))
  }
  return conversation(conv.raw, out)
}
export { fetch_ as fetch }

// --- into soloyolo's shape (spike/live.py) ------------------------------------------------------------------

const text = (t) => (t && typeof t.text === 'string' ? t.text : '')

/** A participant as { id, name, member }, or null for a company page, a bot or anything without a profile. The id is the profile URL. */
export function participant(p) {
  const m = p?.participantType?.member
  if (!m || !m.profileUrl) return null
  return { id: m.profileUrl, name: `${text(m.firstName)} ${text(m.lastName)}`.trim(), member: p.entityUrn || '' }
}

const SKIP_FORMATS = new Set(['SYSTEM', 'RECALLED'])

export function message(m) {
  if (!m?.entityUrn || SKIP_FORMATS.has(m.messageBodyRenderFormat)) return null
  return {
    id: m.entityUrn,
    ts: Number(m.deliveredAt) || 0,
    sender: m.sender?.participantType?.member?.profileUrl || '',
    text: text(m.body),
    subject: m.subject || '',
    media: Array.isArray(m.renderContent) && m.renderContent.length > 0 ? ['attachment'] : [],
  }
}

export function conversation(c, messages) {
  return {
    id: c.entityUrn,
    title: c.title || '',
    group: !!c.groupChat,
    participants: (c.conversationParticipants || []).map(participant).filter(Boolean),
    messages: messages.map(message).filter(Boolean),
  }
}
