const $ = (id) => document.getElementById(id)
const ENABLED = { linkedin: true, instagram: false, x: false } // as in background.js: Instagram and X are opt-in
const ago = (ms) => {
  const min = Math.round((Date.now() - ms) / 60000)
  return min < 1 ? 'just now' : min < 60 ? `${min} min ago` : new Date(ms).toLocaleString()
}

function show(enabled, status = {}) {
  let busy = false
  for (const el of document.querySelectorAll('.net')) {
    const n = el.dataset.network
    const s = status[n] || {}
    const on = !!enabled[n]
    el.querySelector('input').checked = on
    const out = el.querySelector('.status')
    out.classList.toggle('bad', on && !!s.error)
    busy ||= on && !!s.running
    if (!on) out.textContent = 'Off'
    else if (s.running) out.textContent = 'Syncing...'
    else if (s.error) out.textContent = `Stopped ${ago(s.failed)}: ${s.error}${s.retryAt ? `\nTries again by itself after ${new Date(s.retryAt).toLocaleString()}, or use Sync now.` : ''}`
    else if (s.ok) out.textContent = `${ago(s.ok)}${s.you ? ` as ${s.you}` : ''}\n${s.summary}`
    else out.textContent = 'Not synced yet'
  }
  $('sync').disabled = busy
}

const stored = await chrome.storage.local.get(['server', 'token', 'status', 'enabled'])
let enabled = { ...ENABLED, ...stored.enabled }
let status = stored.status || {}
$('server').value = stored.server || 'http://127.0.0.1:8765'
$('token').value = stored.token || ''
show(enabled, status)

chrome.storage.onChanged.addListener((changes) => {
  if (changes.status) status = changes.status.newValue || {}
  if (changes.enabled) enabled = { ...ENABLED, ...changes.enabled.newValue }
  if (changes.status || changes.enabled) show(enabled, status)
})

for (const el of document.querySelectorAll('.net')) {
  el.querySelector('input').addEventListener('change', (e) =>
    chrome.runtime.sendMessage({ type: 'toggle', network: el.dataset.network, on: e.target.checked }))
}

$('save').addEventListener('click', async () => {
  await chrome.storage.local.set({ server: $('server').value.trim().replace(/\/$/, '') || 'http://127.0.0.1:8765', token: $('token').value.trim() })
  $('save').textContent = 'Saved'
  setTimeout(() => { $('save').textContent = 'Save' }, 1200)
})

$('sync').addEventListener('click', () => chrome.runtime.sendMessage({ type: 'sync' }))
