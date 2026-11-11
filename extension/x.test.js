// node --test  (offline: answers built by hand from mautrix-twitter's types, see fixtures/; never a signed-in account)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as x from './x.js'
import { browser, fixture, opts } from './testing.js'

const ME = '1500000000000000001'
const RIYA = '1600000000000000002'
const COOKIES = { ct0: 'csrf', twid: 'u%3D' + ME }
const ONE = `${ME}-${RIYA}`

test('session reads your user id from twid, and stops when signed out', async () => {
  browser(COOKIES, () => 500)
  assert.equal((await x.session()).me.id, ME)
  browser({ twid: 'u%3D1' }, () => 500)
  await assert.rejects(x.session(), /not signed in to X/)
})

test('the first sync reads the inbox, skips message requests and keeps X\'s cursor', async () => {
  const calls = browser(COOKIES, () => fixture('x-inbox-initial-state.json'))
  const ctx = await x.session()
  const out = await x.changed(ctx, {}, opts)
  assert.deepEqual(out.conversations.map((c) => [c.id, c.at]), [[ONE, 1793200000000], ['1800000000000000777', 1793150000000]])
  assert.equal(out.cursor, 'GRwmgICx1aCDpN0uFoCAseaVgaTdLiUAAAA')
  assert.deepEqual(ctx.me, { id: ME, name: 'Anaya Iyer', username: 'anaya_iyer' })
  assert.equal(calls.length, 1)
  assert.match(calls[0].url, /^https:\/\/x\.com\/i\/api\/1\.1\/dm\/inbox_initial_state\.json\?/)
  assert.equal(calls[0].headers['x-csrf-token'], 'csrf')
  assert.ok(calls.every((c) => c.method === 'GET'), 'reads only')
})

test('later syncs ask only for what changed since the cursor', async () => {
  const calls = browser(COOKIES, () => fixture('x-user-updates.json'))
  const out = await x.changed(await x.session(), { cursor: 'old' }, opts)
  assert.match(calls[0].url, /user_updates\.json\?.*cursor=old/)
  assert.deepEqual(out.conversations.map((c) => [c.id, c.at]), [[ONE, 1793300000000]])
  assert.equal(out.cursor, 'GRwmgICx1aCDpN0uFoCAseaVgaTdLiUAAAB')
})

test('fetch keeps newer DMs, expands links and marks media, for spike/live.py', async () => {
  browser(COOKIES, () => fixture('x-conversation.json'))
  const conv = await x.fetch(await x.session(), { id: ONE, raw: { conversation_id: ONE } }, 1793125000000, opts)
  assert.deepEqual(conv, {
    id: ONE, title: '', group: false,
    participants: [{ id: ME, name: 'Anaya Iyer', username: 'anaya_iyer' }, { id: RIYA, name: 'Riya Kapoor', username: 'riya_k' }],
    messages: [
      { id: '1990000000000000001', ts: 1793200000000, sender: ME, text: 'Q&amp;A deck is at https://example.com/deck', media: [] },
      { id: '1940000000000000002', ts: 1793140000000, sender: RIYA, text: '', media: ['voice'] },
      { id: '1930000000000000003', ts: 1793130000000, sender: RIYA, text: 'this one https://x.com/riya_k/status/1', media: [] },
    ],
  })
})

test('a 1:1 conversation known only by its id still names both people', () => {
  assert.deepEqual(x.conversation({ conversation_id: ONE }, []).participants.map((p) => p.id), [ME, RIYA])
})

test('an answer in another shape stops the sync with a clear error', async () => {
  browser(COOKIES, () => ({ errors: [{ code: 88 }] }))
  await assert.rejects(x.changed(await x.session(), {}, opts), /X's answer has no inbox_initial_state in it/)
  browser(COOKIES, () => 429)
  await assert.rejects(x.changed(await x.session(), { cursor: 'c' }, opts), /X answered 429/)
})
