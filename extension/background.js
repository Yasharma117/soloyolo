// Keeps soloyolo in sync with your LinkedIn, Instagram and X messages while Chrome is open, the way Kondo's
// extension does for LinkedIn: through the session already in this browser, at a person's pace, reading only.
// New messages go to soloyolo's server on your Mac (python -m spike serve) and nowhere else.
import * as linkedin from './linkedin.js'
import * as instagram from './instagram.js'
import * as x from './x.js'
import { retryAfter, runNetwork } from './sync.js'

const NETWORKS = [linkedin, instagram, x]
const ALARM = 'sync'
const EVERY_MIN = 20
const DEFAULTS = { server: 'http://127.0.0.1:8765', token: '' }
const ENABLED = { linkedin: true, instagram: false, x: false } // Instagram and X are opt-in

// Each site checks where a request comes from; ours come from the extension, so present them as the site's own
// messages page. Scoped to this extension's requests only.
async function installHeaderRules() {
  await chrome.declarativeNetRequest.updateSessionRules({
    removeRuleIds: NETWORKS.map((_, i) => i + 1),
    addRules: NETWORKS.map((n, i) => ({
      id: i + 1,
      priority: 1,
      action: {
        type: 'modifyHeaders',
        requestHeaders: [
          { header: 'origin', operation: 'set', value: n.rule.origin },
          { header: 'referer', operation: 'set', value: n.rule.referer },
        ],
      },
      condition: { urlFilter: n.rule.urlFilter, initiatorDomains: [chrome.runtime.id], resourceTypes: ['xmlhttprequest'] },
    })),
  })
}

// The first version kept LinkedIn's state under `state` and one status for everything.
async function migrate() {
  const { state, status } = await chrome.storage.local.get(['state', 'status'])
  if (state && !(await chrome.storage.local.get('state_linkedin')).state_linkedin) {
    await chrome.storage.local.set({ state_linkedin: { cursor: state.token || '', seen: state.seen || {}, me: state.me } })
  }
  if (status && !status.linkedin) await chrome.storage.local.set({ status: { linkedin: status } })
  if (state) await chrome.storage.local.remove('state')
}

async function setup() {
  await migrate()
  await installHeaderRules()
  await chrome.alarms.create(ALARM, { delayInMinutes: 1, periodInMinutes: EVERY_MIN })
}

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  await setup()
  if (reason === 'install') chrome.runtime.openOptionsPage()
})
chrome.runtime.onStartup.addListener(setup)
chrome.alarms.onAlarm.addListener((a) => { if (a.name === ALARM) sync(false) })
chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage())
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === 'sync') {
    sync(true).then(() => reply(true))
    return true
  }
  if (msg?.type === 'toggle') {
    toggle(msg.network, !!msg.on).then(() => reply(true))
    return true
  }
})

let running = null
function sync(now) {
  running ??= run(now).finally(() => { running = null })
  return running
}

async function setStatus(network, patch) {
  const { status = {} } = await chrome.storage.local.get('status')
  status[network] = { ...status[network], ...patch }
  await chrome.storage.local.set({ status })
  const bad = Object.values(status).some((s) => s?.error)
  await chrome.action.setBadgeText({ text: bad ? '!' : '' })
  await chrome.action.setBadgeBackgroundColor({ color: '#e8a317' })
  return status[network]
}

async function call(config, path, body) {
  let res
  try {
    res = await fetch(`${config.server}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${config.token}` },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error(`can't reach soloyolo at ${config.server}: is python -m spike serve running?`)
  }
  if (res.status === 401) throw new Error('soloyolo refused the token: run python -m spike linkedin-token and paste it again')
  if (!res.ok) throw new Error(`soloyolo answered ${res.status}: ${await res.text()}`)
  return res.json()
}

/** Tells soloyolo how a network's sync stands, so the app can show it. Best effort: a missed report costs nothing. */
const report = (config, body) => call(config, '/api/live/status', body).catch(() => {})

async function toggle(network, on) {
  const { enabled = {} } = await chrome.storage.local.get('enabled')
  await chrome.storage.local.set({ enabled: { ...ENABLED, ...enabled, [network]: on } })
  const config = { ...DEFAULTS, ...(await chrome.storage.local.get(['server', 'token'])) }
  if (config.token) await report(config, { network, enabled: on })
}

async function run(now) {
  const config = { ...DEFAULTS, ...(await chrome.storage.local.get(['server', 'token'])) }
  const { enabled: saved = {}, status = {} } = await chrome.storage.local.get(['enabled', 'status'])
  const enabled = { ...ENABLED, ...saved }
  const due = NETWORKS.filter((n) => enabled[n.id] && (now || !(status[n.id]?.retryAt > Date.now())))
  if (!due.length) return
  try {
    if (!config.token) throw new Error('not paired: paste the token from python -m spike linkedin-token')
    await call(config, '/api/live/sync', { ping: true }) // don't spend a network's requests on a sync nobody receives
  } catch (e) {
    for (const n of due) await setStatus(n.id, { running: false, error: String(e.message || e), failed: Date.now() })
    return
  }
  // One network at a time, so the requests to each stay spaced out and never overlap.
  for (const n of due) {
    const key = `state_${n.id}`
    await setStatus(n.id, { running: true, started: Date.now() })
    try {
      const out = await runNetwork(n, {
        state: (await chrome.storage.local.get(key))[key],
        post: (body) => call(config, '/api/live/sync', body),
        save: (st) => chrome.storage.local.set({ [key]: st }),
      })
      await setStatus(n.id, { running: false, error: null, ok: Date.now(), failures: 0, retryAt: 0, ...out })
      await report(config, { network: n.id, enabled: true, error: null, you: out.you })
    } catch (e) {
      // Stop this network and wait: an hour, doubling to a day. Never retry fast against a site that said no.
      const failures = (status[n.id]?.failures || 0) + 1
      const error = String(e.message || e)
      await setStatus(n.id, { running: false, error, failed: Date.now(), failures, retryAt: retryAfter(failures) })
      await report(config, { network: n.id, enabled: true, error })
    }
  }
}
