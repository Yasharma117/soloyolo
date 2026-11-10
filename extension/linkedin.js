// LinkedIn's own web API, read through the session already open in this browser. Endpoints and query ids follow
// mautrix-linkedin (pkg/linkedingo/constants.go, read 2026-11-10); LinkedIn changes them, so they live in one place.

export const BASE = 'https://www.linkedin.com'
const GRAPHQL = `${BASE}/voyager/api/voyagerMessagingGraphQL/graphql`
const ME = `${BASE}/voyager/api/me`
export const QUERY = {
  conversations: 'messengerConversations.0d5e6781bbee71c3e51c8843c6519f48',
  conversationsSince: 'messengerConversations.74c17e85611b60b7ba2700481151a316',
  conversationsBefore: 'messengerConversations.9501074288a12f3ae9e3c7ea243bccbf',
  messagesBefore: 'messengerMessages.d8ea76885a52fd5dc5c317078ab7c977',
}

export class LinkedInError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

/** The csrf token LinkedIn expects is the JSESSIONID cookie's value, without its quotes. */
export async function csrfToken() {
  const c = await chrome.cookies.get({ url: BASE, name: 'JSESSIONID' })
  if (!c) throw new LinkedInError('not signed in to LinkedIn in this browser', 401)
  return c.value.replace(/"/g, '')
}

async function get(url, csrf, accept = 'application/graphql') {
  const res = await fetch(url, {
    credentials: 'include',
    headers: { accept, 'csrf-token': csrf, 'x-restli-protocol-version': '2.0.0', 'accept-language': 'en-US,en;q=0.9' },
  })
  if (res.status === 401 || res.status === 403) throw new LinkedInError('LinkedIn session expired: sign in again', res.status)
  if (!res.ok) throw new LinkedInError(`LinkedIn answered ${res.status}`, res.status)
  return res.json()
}

// variables=(key:value,...) with urns escaped, as the web app sends them.
const graphql = (queryId, vars) =>
  `${GRAPHQL}?queryId=${queryId}&variables=(${Object.entries(vars).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${k}:${v}`).join(',')})`

/** You: { url, name, mailbox }. mailbox is the fsd_profile urn the messaging queries are addressed to. */
export async function me(csrf) {
  const r = await get(ME, csrf, 'application/json')
  const p = r.miniProfile || {}
  const id = (p.dashEntityUrn || '').split(':').pop()
  if (!p.publicIdentifier || !id) throw new LinkedInError('could not read your profile', 0)
  return {
    url: `${BASE}/in/${p.publicIdentifier}`,
    name: `${p.firstName || ''} ${p.lastName || ''}`.trim(),
    mailbox: `urn:li:fsd_profile:${id}`,
  }
}

/** Changed conversations since `token` (or the latest page when there's none) and the token to use next time. */
export async function conversationsSince(csrf, mailbox, token) {
  const vars = { mailboxUrn: encodeURIComponent(mailbox) }
  if (token) vars.syncToken = token
  const r = await get(graphql(token ? QUERY.conversationsSince : QUERY.conversations, vars), csrf)
  const data = r?.data?.messengerConversationsBySyncToken
  if (!data) throw new LinkedInError('no conversations in the answer (the sync token may have expired)', 0)
  return { conversations: data.elements || [], token: data.metadata?.newSyncToken || token }
}

/** Up to 20 inbox conversations last active before `beforeMs`, newest first. For the first sync's backfill. */
export async function conversationsBefore(csrf, mailbox, beforeMs) {
  const r = await get(graphql(QUERY.conversationsBefore, {
    mailboxUrn: encodeURIComponent(mailbox),
    lastUpdatedBefore: String(beforeMs),
    count: '20',
    query: '(predicateUnions:List((conversationCategoryPredicate:(category:PRIMARY_INBOX))))',
  }), csrf)
  return r?.data?.messengerConversationsByCategoryQuery?.elements || []
}

/** Up to `count` messages delivered before `beforeMs` in one conversation. */
export async function messagesBefore(csrf, conversationUrn, beforeMs, count = 20) {
  const r = await get(graphql(QUERY.messagesBefore, {
    deliveredAt: String(beforeMs),
    conversationUrn: encodeURIComponent(conversationUrn),
    countBefore: String(count),
    countAfter: '0',
  }), csrf)
  return r?.data?.messengerMessagesByAnchorTimestamp?.elements || []
}

// --- into soloyolo's shape (spike/linkedin_live.py) ---------------------------------------------------------

const text = (t) => (t && typeof t.text === 'string' ? t.text : '')

/** A participant as { url, name, member }, or null for a company page, a bot or anything without a profile. */
export function participant(p) {
  const m = p?.participantType?.member
  if (!m || !m.profileUrl) return null
  return { url: m.profileUrl, name: `${text(m.firstName)} ${text(m.lastName)}`.trim(), member: p.entityUrn || '' }
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
    attachment: Array.isArray(m.renderContent) && m.renderContent.length > 0,
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
