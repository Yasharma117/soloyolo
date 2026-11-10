const $ = (id) => document.getElementById(id)
const ago = (ms) => {
  const min = Math.round((Date.now() - ms) / 60000)
  return min < 1 ? 'just now' : min < 60 ? `${min} min ago` : new Date(ms).toLocaleString()
}

function show(s = {}) {
  const el = $('status')
  el.classList.toggle('bad', !!s.error)
  if (s.running) el.textContent = 'Syncing...'
  else if (s.error) el.textContent = `Stopped ${ago(s.failed)}: ${s.error}`
  else if (s.ok) el.textContent = `${ago(s.ok)} as ${s.you}\n${s.summary}`
  else el.textContent = 'Not synced yet'
  $('sync').disabled = !!s.running
}

const { server = 'http://127.0.0.1:8765', token = '', status } = await chrome.storage.local.get(['server', 'token', 'status'])
$('server').value = server
$('token').value = token
show(status)

chrome.storage.onChanged.addListener((changes) => { if (changes.status) show(changes.status.newValue) })

$('save').addEventListener('click', async () => {
  await chrome.storage.local.set({ server: $('server').value.trim().replace(/\/$/, '') || 'http://127.0.0.1:8765', token: $('token').value.trim() })
  $('save').textContent = 'Saved'
  setTimeout(() => { $('save').textContent = 'Save' }, 1200)
})

$('sync').addEventListener('click', () => chrome.runtime.sendMessage({ type: 'sync' }))
