// node --test  (offline: answers built by hand from instagrapi's shapes, see fixtures/; never a signed-in account)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as ig from './instagram.js'
import { browser, fixture, opts } from './testing.js'

const ME = '17840000000000001'
const KABIR = '17840000000000002'
const COOKIES = { csrftoken: 'tok', ds_user_id: ME }

test('session reads who you are from the cookies, and stops when signed out', async () => {
  browser(COOKIES, () => 500)
  assert.deepEqual((await ig.session()).me, { id: ME, name: '', username: '' })
  browser({ csrftoken: 'tok' }, () => 500)
  await assert.rejects(ig.session(), /not signed in to Instagram/)
})

test('changed lists threads, names you from the viewer, and remembers the newest activity', async () => {
  const calls = browser(COOKIES, () => fixture('instagram-inbox.json'))
  const ctx = await ig.session()
  const out = await ig.changed(ctx, { cursor: String(1793050000000) }, opts)
  assert.deepEqual(out.conversations.map((c) => [c.id.slice(-1), c.at]), [['1', 1793100004000], ['2', 1793000000000]])
  assert.equal(out.cursor, '1793100004000')
  assert.equal(ctx.me.name, 'Anaya Iyer')
  assert.equal(calls.length, 1, 'stops paging once it reaches a thread it has seen')
  assert.match(calls[0].url, /^https:\/\/www\.instagram\.com\/api\/v1\/direct_v2\/inbox\//)
  assert.equal(calls[0].headers['x-csrftoken'], 'tok')
  assert.ok(calls.every((c) => c.method === 'GET'), 'reads only')
})

test('fetch keeps only newer items and normalises them for spike/live.py', async () => {
  const calls = browser(COOKIES, () => fixture('instagram-thread.json'))
  const ctx = await ig.session()
  const conv = await ig.fetch(ctx, { id: '340282366841710300949128100000000001', at: 1793100004000, raw: {} }, 1793010000000, opts)
  assert.equal(calls.length, 1, 'stops at the first page that reaches older items')
  assert.deepEqual(conv, {
    id: '340282366841710300949128100000000001', key: '1784512345678901', title: 'Kabir Sharma', group: false,
    participants: [{ id: KABIR, name: 'Kabir Sharma', username: 'kabirsharma' }, { id: ME, name: '', username: '' }],
    messages: [
      { id: 'i9', ts: 1793100004000, sender: KABIR, text: 'see you then', media: [] },
      { id: 'i8', ts: 1793100003000, sender: ME, text: '', media: ['call'] },
      { id: 'i6', ts: 1793100002000, sender: KABIR, text: '', media: ['voice'] },
      { id: 'i5', ts: 1793100001500, sender: KABIR, text: '', media: [], link: 'https://www.instagram.com/p/Cabc123/' },
      { id: 'i4', ts: 1793100001000, sender: KABIR, text: 'look https://example.com/menu', media: [], link: 'https://example.com/menu' },
      { id: 'i3', ts: 1793100000000, sender: KABIR, text: '', media: ['photo'] },
      { id: 'i2', ts: 1793014400000, sender: ME, text: '❤️', media: [] },
    ],
  })
})

test('an answer in another shape stops the sync with a clear error', async () => {
  browser(COOKIES, () => ({ status: 'ok', something: 'else' }))
  await assert.rejects(ig.changed(await ig.session(), {}, opts), /Instagram's answer has no inbox in it/)
  browser(COOKIES, () => ({ status: 'fail', message: 'checkpoint_required' }))
  await assert.rejects(ig.changed(await ig.session(), {}, opts), /checkpoint_required/)
  browser(COOKIES, () => 401)
  await assert.rejects(ig.fetch(await ig.session(), { id: '1', raw: {} }, 0, opts), /session expired/)
})
