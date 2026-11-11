// X's own web API for direct messages, read through the session already open in this browser. Endpoints, headers
// and response shapes follow mautrix-twitter (pkg/twittermeow: data/endpoints/endpoints.go, headers.go,
// data/types/messaging.go, read 2026-11-11). Never run against a signed-in account: see README.md.
//
// Only the older, unencrypted DMs come through here. mautrix-twitter reads encrypted XChat conversations over a
// separate protocol and uses these REST endpoints for "unencrypted/untrusted conversations"; this module does not
// read XChat at all.
import { NetworkError, shape } from './sync.js'

export const id = 'x'
export const label = 'X'
export const BASE = 'https://x.com'
export const rule = { urlFilter: '||x.com/i/api/', origin: BASE, referer: `${BASE}/messages` }
export const limits = { days: 90, pages: 5 } // first sync: 90 days back, 5 pages of the inbox and of each conversation

const DM = `${BASE}/i/api/1.1/dm`
// The web app's own public bearer token, the same for every visitor (mautrix-twitter headers.go).
const BEARER = 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'
const PARAMS = 'include_groups=true&dm_users=true&include_conversation_info=true&supports_reactions=true'

async function cookie(name) {
  const c = await chrome.cookies.get({ url: BASE, name })
  return c ? decodeURIComponent(c.value) : ''
}

async function get(url, csrf) {
  const res = await fetch(url, {
    credentials: 'include',
    headers: {
      authorization: BEARER,
      'x-csrf-token': csrf,
      'x-twitter-auth-type': 'OAuth2Session',
      'x-twitter-active-user': 'yes',
      'x-twitter-client-language': 'en',
    },
  })
  if (res.status === 401 || res.status === 403) throw new NetworkError('X session expired: sign in to x.com again', res.status)
  if (!res.ok) throw new NetworkError(`X answered ${res.status}`, res.status)
  return res.json()
}

/** You: the user id from the twid cookie ("u=123"), and the csrf token from ct0. Your name arrives with the inbox. */
export async function session() {
  const csrf = await cookie('ct0')
  const uid = (await cookie('twid')).replace(/^u=/, '')
  if (!csrf || !/^\d+$/.test(uid)) throw new NetworkError('not signed in to X in this browser', 401)
  return { csrf, account: uid, me: { id: uid, name: '', username: '' }, users: {} }
}

const num = (v) => Number(v) || 0

/** Takes in the users and conversations one answer carries; returns its conversations as { id, at, raw }. */
function absorb(ctx, page) {
  Object.assign(ctx.users, page.users || {})
  const you = ctx.users[ctx.me.id]
  if (you) ctx.me = { id: ctx.me.id, name: you.name || '', username: you.screen_name || '' }
  const convs = new Map()
  for (const c of Object.values(page.conversations || {})) {
    if (c?.conversation_id && c.trusted !== false) convs.set(c.conversation_id, { id: c.conversation_id, at: num(c.sort_timestamp), raw: c })
  }
  // A message whose conversation isn't in the map still marks it as changed; fetch() fills in the rest.
  for (const e of page.entries || []) {
    const m = e?.message
    if (!m?.conversation_id || convs.has(m.conversation_id) || m.trusted === false) continue
    convs.set(m.conversation_id, { id: m.conversation_id, at: num(m.time), raw: { conversation_id: m.conversation_id } })
  }
  return [...convs.values()]
}

/** Conversations that changed since the last sync, by X's own cursor; the first time, the inbox back 90 days. */
export async function changed(ctx, state, { since, maxPages, pause }) {
  if (state.cursor) {
    const r = await get(`${DM}/user_updates.json?${PARAMS}&cursor=${encodeURIComponent(state.cursor)}`, ctx.csrf)
    const u = r?.user_events
    if (!u || !Array.isArray(u.entries || [])) throw shape(label, 'user_events')
    return { conversations: absorb(ctx, u), cursor: u.cursor || state.cursor }
  }
  const r = await get(`${DM}/inbox_initial_state.json?${PARAMS}`, ctx.csrf)
  const s = r?.inbox_initial_state
  if (!s || typeof s.conversations !== 'object') throw shape(label, 'inbox_initial_state')
  const all = new Map(absorb(ctx, s).map((c) => [c.id, c]))
  let timeline = s.inbox_timelines?.trusted || {}
  for (let page = 0; page < maxPages && timeline.status === 'HAS_MORE' && timeline.min_entry_id; page++) {
    if (Math.min(...[...all.values()].map((c) => c.at)) <= since) break
    await pause()
    const older = await get(`${DM}/inbox_timeline/trusted.json?${PARAMS}&max_id=${timeline.min_entry_id}`, ctx.csrf)
    timeline = older?.inbox_timeline
    if (!timeline) throw shape(label, 'inbox_timeline')
    for (const c of absorb(ctx, timeline)) all.set(c.id, c)
  }
  if (!s.cursor) throw shape(label, 'cursor')
  return { conversations: [...all.values()], cursor: s.cursor }
}

/** A conversation's messages newer than `after`, newest page first, paging back until it reaches them. */
export async function fetch_(ctx, conv, after, { maxPages, pause }) {
  const out = []
  let raw = conv.raw
  let maxId = ''
  for (let page = 0; page < maxPages; page++) {
    await pause()
    const r = await get(`${DM}/conversation/${encodeURIComponent(conv.id)}.json?${PARAMS}&context=FETCH_DM_CONVERSATION${maxId ? `&max_id=${maxId}` : ''}`, ctx.csrf)
    const t = r?.conversation_timeline
    if (!t || !Array.isArray(t.entries)) throw shape(label, 'conversation_timeline')
    Object.assign(ctx.users, t.users || {})
    if (t.conversations?.[conv.id]) raw = t.conversations[conv.id]
    const got = t.entries.filter((e) => e?.message)
    const newer = got.filter((e) => num(e.message.message_data?.time || e.message.time) > after)
    out.push(...newer)
    if (t.status !== 'HAS_MORE' || !t.min_entry_id || newer.length < got.length) break
    maxId = t.min_entry_id
  }
  return conversation(raw, out, ctx.users)
}
export { fetch_ as fetch }

// --- into soloyolo's shape (spike/live.py) ------------------------------------------------------------------

/** The DM's text with t.co links expanded, the attachment's own t.co link removed, and a shared post's link kept. */
export function message(entry) {
  const m = entry?.message
  const d = m?.message_data
  if (!d) return null
  const id = d.id || m.id
  const ts = num(d.time || m.time)
  if (!id || !ts || !d.sender_id) return null
  const a = d.attachment || {}
  let text = d.text || ''
  const media = []
  if (a.photo) media.push('photo')
  if (a.video) media.push(a.video.audio_only ? 'voice' : 'video')
  for (const item of [a.photo, a.video, a.animated_gif]) if (item?.url) text = text.replace(item.url, '')
  for (const u of d.entities?.urls || []) if (u?.url && u.expanded_url) text = text.split(u.url).join(u.expanded_url)
  const shared = a.tweet?.expanded_url || a.card?.url || ''
  if (shared && !text.includes(shared)) text = `${text} ${shared}`
  return { id, ts, sender: d.sender_id, text: text.trim(), media }
}

export function conversation(c, entries, users = {}) {
  // A 1:1 conversation's id is the two user ids joined by a dash, which names them when nothing else does.
  const ids = c.participants?.length ? c.participants.map((p) => p?.user_id) : /^\d+-\d+$/.test(c.conversation_id) ? c.conversation_id.split('-') : []
  return {
    id: c.conversation_id,
    title: c.name || '',
    group: c.type === 'GROUP_DM',
    participants: ids.filter(Boolean).map((uid) => ({
      id: uid, name: users[uid]?.name || '', username: users[uid]?.screen_name || '',
    })),
    messages: entries.map(message).filter(Boolean),
  }
}
