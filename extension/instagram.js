// Instagram's web API for direct messages (www.instagram.com/api/v1/direct_v2/...), read through the session
// already open in this browser. Paths, parameters and response shapes follow instagrapi (mixins/direct.py and
// extractors.py, read 2026-11-11), which reads the same endpoints with the mobile app's id; the web app id is the
// one instaloader sends. Never run against a signed-in account, and Instagram's own web client may have moved its
// inbox to another protocol (mautrix-meta reads it over Lightspeed): see README.md.
import { NetworkError, shape } from './sync.js'

export const id = 'instagram'
export const label = 'Instagram'
export const BASE = 'https://www.instagram.com'
export const rule = { urlFilter: '||www.instagram.com/api/v1/direct_v2/', origin: BASE, referer: `${BASE}/direct/inbox/` }
export const limits = { days: 90, pages: 5 } // first sync: 90 days back, 5 pages of 20 threads, 5 pages of 20 messages each

const API = `${BASE}/api/v1/direct_v2`
const APP_ID = '936619743392459' // Instagram's web app

async function cookie(name) {
  const c = await chrome.cookies.get({ url: BASE, name })
  return c ? c.value : ''
}

async function get(url, csrf) {
  const res = await fetch(url, {
    credentials: 'include',
    headers: { accept: '*/*', 'x-ig-app-id': APP_ID, 'x-csrftoken': csrf, 'x-requested-with': 'XMLHttpRequest' },
  })
  if (res.status === 401 || res.status === 403) throw new NetworkError('Instagram session expired: sign in to instagram.com again', res.status)
  if (!res.ok) throw new NetworkError(`Instagram answered ${res.status}`, res.status)
  const r = await res.json()
  // A checkpoint or login_required arrives as a 200 with status "fail". Stop; never try to answer it.
  if (r?.status === 'fail') throw new NetworkError(`Instagram stopped the sync (${r.message || 'no reason given'}): open instagram.com and check the account`, 403)
  return r
}

/** You: your user id from the ds_user_id cookie and the csrf token. Your name arrives with the inbox. */
export async function session() {
  const csrf = await cookie('csrftoken')
  const uid = await cookie('ds_user_id')
  if (!csrf || !/^\d+$/.test(uid)) throw new NetworkError('not signed in to Instagram in this browser', 401)
  return { csrf, account: uid, me: { id: uid, name: '', username: '' } }
}

// Times come in microseconds; soloyolo's are milliseconds.
const ms = (us) => Math.floor(Number(us) / 1000) || 0

/** Threads active since the last sync, newest first, paging back until it reaches the last one seen. */
export async function changed(ctx, state, { since, maxPages, pause }) {
  const stop = Math.max(Number(state.cursor) || 0, since)
  const out = []
  let cursor = ''
  for (let page = 0; page < maxPages; page++) {
    if (page) await pause()
    const r = await get(`${API}/inbox/?persistentBadging=true&limit=20&thread_message_limit=1${cursor ? `&cursor=${encodeURIComponent(cursor)}&direction=older` : ''}`, ctx.csrf)
    const inbox = r?.inbox
    if (!inbox || !Array.isArray(inbox.threads)) throw shape(label, 'inbox')
    const v = r.viewer
    if (v && String(v.pk_id ?? v.pk) === ctx.me.id) ctx.me = { id: ctx.me.id, name: v.full_name || '', username: v.username || '' }
    const threads = inbox.threads.filter((t) => t?.thread_id).map((t) => ({ id: t.thread_id, at: ms(t.last_activity_at), raw: t }))
    out.push(...threads)
    if (!inbox.has_older || !inbox.oldest_cursor || threads.some((t) => t.at <= stop)) break
    cursor = inbox.oldest_cursor
  }
  const newest = Math.max(Number(state.cursor) || 0, ...out.map((t) => t.at))
  return { conversations: out, cursor: newest ? String(newest) : '' }
}

/** A thread's messages newer than `after`, newest page first, paging back until it reaches them. */
export async function fetch_(ctx, conv, after, { maxPages, pause }) {
  const out = []
  let raw = conv.raw
  let cursor = ''
  for (let page = 0; page < maxPages; page++) {
    await pause()
    const r = await get(`${API}/threads/${encodeURIComponent(conv.id)}/?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}&direction=older` : ''}`, ctx.csrf)
    const t = r?.thread
    if (!t || !Array.isArray(t.items)) throw shape(label, 'thread')
    raw = { ...raw, ...t, items: undefined }
    const newer = t.items.filter((i) => ms(i?.timestamp) > after)
    out.push(...newer)
    if (!t.has_older || !t.oldest_cursor || newer.length < t.items.length) break
    cursor = t.oldest_cursor
  }
  return conversation(raw, out, ctx.me.id)
}
export { fetch_ as fetch }

// --- into soloyolo's shape (spike/live.py) ------------------------------------------------------------------

const KIND = { 1: 'photo', 2: 'video' } // media_type
const post = (m) => (m?.code ? `${BASE}/p/${m.code}/` : '')
const SKIP = new Set(['action_log', 'placeholder', 'expired_placeholder', 'reaction'])

/** One item as { id, ts, sender, text, media, link }, or null for joins, renames and other system lines. */
export function message(i) {
  if (!i?.item_id || SKIP.has(i.item_type)) return null
  const out = { id: i.item_id, ts: ms(i.timestamp), sender: String(i.user_id ?? ''), text: typeof i.text === 'string' ? i.text : '', media: [] }
  switch (i.item_type) {
    case 'link':
      out.text = i.link?.text || out.text
      out.link = i.link?.link_context?.link_url || ''
      break
    case 'media':
      out.media.push(KIND[i.media?.media_type] || 'photo')
      break
    case 'raven_media': // a photo or video sent to be viewed once
      out.media.push(KIND[i.visual_media?.media?.media_type] || 'photo')
      break
    case 'voice_media':
      out.media.push('voice')
      break
    case 'video_call_event':
      out.media.push('call')
      break
    case 'like':
      out.text = i.like || out.text
      break
    case 'media_share':
      out.link = post(i.media_share)
      break
    case 'clip':
      out.link = post(i.clip?.clip || i.clip)
      break
    case 'story_share':
      out.text = out.text || i.story_share?.message || ''
      break
    default: // text, and kinds this doesn't know: whatever was typed
  }
  return out
}

export function conversation(t, items, me = '') {
  // pk_id is the id as a string. pk and an item's user_id are JSON numbers, and ids past 2^53 lose their last digits
  // when parsed, so a sender is matched to a user by the same rounding and then named by the exact id.
  const users = (t.users || []).map((u) => ({ id: String(u.pk_id ?? u.pk ?? ''), name: u.full_name || '', username: u.username || '' }))
  if (me && !users.some((u) => u.id === me)) users.push({ id: me, name: '', username: '' }) // users lists the others only
  const exact = new Map(users.map((u) => [String(Number(u.id)), u.id]))
  const messages = items.map(message).filter(Boolean).map((m) => ({ ...m, sender: exact.get(String(Number(m.sender))) || m.sender }))
  return {
    id: t.thread_id,
    key: t.thread_v2_id || t.thread_id,
    title: t.thread_title || '',
    group: !!t.is_group,
    participants: users.filter((u) => u.id),
    messages,
  }
}
