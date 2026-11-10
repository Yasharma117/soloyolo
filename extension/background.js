// Keeps soloyolo in sync with your LinkedIn inbox while Chrome is open, the way Kondo's extension does: through
// the LinkedIn session already in this browser, at a person's pace, reading only. New messages go to soloyolo's
// server on your Mac (python -m spike serve) and nowhere else.
import * as li from './linkedin.js'

const ALARM = 'sync'
const EVERY_MIN = 20
const FIRST_SYNC_DAYS = 90 // how far back the first sync reads
const MAX_PAGES = 5 // per conversation and for the first sync's conversation list: 100 of each at most
const BATCH = 25 // conversations per post to the server
const DEFAULTS = { server: 'http://127.0.0.1:8765', token: '' }

const pause = () => new Promise((r) => setTimeout(r, 1500 + Math.random() * 2500))

// LinkedIn checks where a request comes from; ours come from the extension, so present them as the messaging page.
async function installHeaderRules() {
  await chrome.declarativeNetRequest.updateSessionRules({
    removeRuleIds: [1],
    addRules: [{
      id: 1,
      priority: 1,
      action: {
        type: 'modifyHeaders',
        requestHeaders: [
          { header: 'origin', operation: 'set', value: li.BASE },
          { header: 'referer', operation: 'set', value: `${li.BASE}/messaging/` },
        ],
      },
      condition: { urlFilter: '||www.linkedin.com/voyager/', initiatorDomains: [chrome.runtime.id], resourceTypes: ['xmlhttprequest'] },
    }],
  })
}

async function setup() {
  await installHeaderRules()
  await chrome.alarms.create(ALARM, { delayInMinutes: 1, periodInMinutes: EVERY_MIN })
}

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  await setup()
  if (reason === 'install') chrome.runtime.openOptionsPage()
})
chrome.runtime.onStartup.addListener(setup)
chrome.alarms.onAlarm.addListener((a) => { if (a.name === ALARM) sync() })
chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage())
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === 'sync') {
    sync().then(() => reply(true))
    return true
  }
})

let running = null
function sync() {
  running ??= run().finally(() => { running = null })
  return running
}

async function status(patch) {
  const { status: prev = {} } = await chrome.storage.local.get('status')
  await chrome.storage.local.set({ status: { ...prev, ...patch } })
  const bad = patch.error !== undefined ? patch.error : prev.error
  await chrome.action.setBadgeText({ text: bad ? '!' : '' })
  await chrome.action.setBadgeBackgroundColor({ color: '#e8a317' })
}

async function post(config, body) {
  const res = await fetch(`${config.server}/api/linkedin/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${config.token}` },
    body: JSON.stringify(body),
  })
  if (res.status === 401) throw new Error('soloyolo refused the token: run python -m spike linkedin-token and paste it again')
  if (!res.ok) throw new Error(`soloyolo answered ${res.status}: ${await res.text()}`)
  return res.json()
}

async function run() {
  const config = { ...DEFAULTS, ...(await chrome.storage.local.get(['server', 'token'])) }
  await status({ running: true, started: Date.now() })
  try {
    if (!config.token) throw new Error('not paired: paste the token from python -m spike linkedin-token')
    // Is soloyolo listening? Don't spend LinkedIn requests on a sync nobody will receive.
    await post(config, { ping: true }).catch((e) => {
      // fetch throws a TypeError when nothing is listening; a refused token keeps its own message.
      throw e instanceof TypeError ? new Error(`can't reach soloyolo at ${config.server}: is python -m spike serve running?`) : e
    })
    const csrf = await li.csrfToken()
    const state = { token: '', seen: {}, ...(await chrome.storage.local.get('state')).state }
    const you = await li.me(csrf)
    if (state.me && state.me !== you.url) Object.assign(state, { token: '', seen: {} }) // a different account
    state.me = you.url

    let changed
    try {
      await pause()
      const r = await li.conversationsSince(csrf, you.mailbox, state.token)
      changed = r.conversations
      state.nextToken = r.token
    } catch (e) {
      if (!state.token || e.status === 401 || e.status === 403) throw e
      state.token = '' // an expired sync token: start over from the latest page
      const r = await li.conversationsSince(csrf, you.mailbox, '')
      changed = r.conversations
      state.nextToken = r.token
    }
    if (!state.token) changed = await backfill(csrf, you.mailbox, changed)

    const since = Date.now() - FIRST_SYNC_DAYS * 86400e3
    const fresh = changed.filter((c) => c.entityUrn && (c.lastActivityAt || 0) > (state.seen[c.entityUrn] || since))
    let sent = 0
    let summary = ''
    for (let i = 0; i < fresh.length; i += BATCH) {
      const batch = []
      for (const c of fresh.slice(i, i + BATCH)) {
        batch.push(li.conversation(c, await messages(csrf, c, state.seen[c.entityUrn] || since)))
      }
      const out = await post(config, { me: { url: you.url, name: you.name }, conversations: batch })
      summary = out.summary
      // Only now is it safe to remember these as read: soloyolo has them.
      for (const c of fresh.slice(i, i + BATCH)) state.seen[c.entityUrn] = c.lastActivityAt
      sent += batch.length
      await chrome.storage.local.set({ state })
    }
    state.token = state.nextToken
    delete state.nextToken
    await chrome.storage.local.set({ state })
    await status({ running: false, error: null, ok: Date.now(), you: you.name, conversations: sent,
                   summary: sent ? summary : 'nothing new' })
  } catch (e) {
    await status({ running: false, error: String(e.message || e), failed: Date.now() })
  }
}

// First sync: the sync token answers only the latest page, so walk back through the inbox for older threads.
async function backfill(csrf, mailbox, first) {
  const all = new Map(first.map((c) => [c.entityUrn, c]))
  const since = Date.now() - FIRST_SYNC_DAYS * 86400e3
  let oldest = Math.min(...first.map((c) => c.lastActivityAt || Date.now()), Date.now())
  for (let page = 0; page < MAX_PAGES && oldest > since; page++) {
    await pause()
    const older = await li.conversationsBefore(csrf, mailbox, oldest)
    if (!older.length) break
    for (const c of older) all.set(c.entityUrn, c)
    oldest = Math.min(...older.map((c) => c.lastActivityAt || oldest))
  }
  return [...all.values()]
}

// A conversation's messages newer than `after`, newest page first, paging back until it reaches them.
async function messages(csrf, c, after) {
  const out = []
  let before = (c.lastActivityAt || Date.now()) + 1
  for (let page = 0; page < MAX_PAGES; page++) {
    await pause()
    const got = await li.messagesBefore(csrf, c.entityUrn, before)
    const newer = got.filter((m) => (m.deliveredAt || 0) > after)
    out.push(...newer)
    if (got.length < 20 || newer.length < got.length) break
    before = Math.min(...got.map((m) => m.deliveredAt || before))
  }
  return out
}
