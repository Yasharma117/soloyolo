// node --test  (the loop every network shares: pacing, state, and synced only once soloyolo stored it)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { retryAfter, runNetwork } from './sync.js'

const fake = (convs) => ({
  id: 'x', label: 'Fake', limits: { days: 90, pages: 1 },
  session: async () => ({ account: 'a', me: { id: '1', name: 'You' } }),
  changed: async () => ({ conversations: convs, cursor: 'next' }),
  fetch: async (_ctx, c) => ({ id: c.id, messages: [] }),
})
const NOW = 100 * 86400e3
const conv = (id, at) => ({ id, at, raw: {} })

test('a conversation is remembered only after the server stored it', async () => {
  const saved = []
  let posts = 0
  const mod = fake(Array.from({ length: 30 }, (_, i) => conv(`c${i}`, NOW - i)))
  const post = async () => { if (++posts === 2) throw new Error('server down'); return { summary: 'ok' } }
  await assert.rejects(runNetwork(mod, { state: {}, post, save: async (s) => saved.push(structuredClone(s)), wait: async () => {}, now: () => NOW }), /server down/)
  const last = saved.at(-1)
  assert.equal(Object.keys(last.seen).length, 25, 'the first batch of 25 only')
  assert.equal(last.cursor, '', 'the cursor moves on only when everything was stored')
})

test('nothing new is not sent, and a different account starts over', async () => {
  let sent = 0
  const state = { me: 'someone else', cursor: 'old', seen: { c0: NOW } }
  const out = await runNetwork(fake([conv('c0', NOW), conv('old', 1)]), {
    state, post: async (b) => { sent += b.conversations.length; return { summary: 's' } }, save: async () => {}, wait: async () => {}, now: () => NOW,
  })
  assert.equal(sent, 1, 'c0 again, since the account changed; the one older than 90 days is left out')
  assert.equal(out.conversations, 1)
})

test('after a failure it waits an hour, doubling up to a day', () => {
  assert.deepEqual([1, 2, 3, 6, 9].map((n) => retryAfter(n, 0) / 3600e3), [1, 2, 4, 24, 24])
})
