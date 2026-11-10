// node --test  (offline: LinkedIn's answer shapes, after mautrix-linkedin's types, into what spike/linkedin_live.py reads)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { conversation } from './linkedin.js'

const member = (slug, first, last) => ({
  entityUrn: `urn:li:msg_messagingParticipant:urn:li:fsd_profile:${slug}`,
  participantType: { member: { profileUrl: `https://www.linkedin.com/in/${slug}`, firstName: { text: first }, lastName: { text: last } } },
})

test('a 1:1 conversation in soloyolo shape', () => {
  const c = {
    entityUrn: 'urn:li:msg_conversation:(urn:li:fsd_profile:me,2-abc)', title: '', groupChat: false, lastActivityAt: 3,
    conversationParticipants: [member('alex', 'Alex', 'Rivera'), member('priya', 'Priya', 'N'),
                               { participantType: { organization: { name: { text: 'Acme' } } } }],
  }
  const msgs = [
    { entityUrn: 'urn:li:msg_message:1', deliveredAt: 1, body: { text: 'I will send the deck' }, sender: member('alex'), messageBodyRenderFormat: 'DEFAULT' },
    { entityUrn: 'urn:li:msg_message:2', deliveredAt: 2, body: { text: '' }, renderContent: [{ file: {} }], sender: member('priya') },
    { entityUrn: 'urn:li:msg_message:3', deliveredAt: 3, body: { text: 'Priya joined' }, messageBodyRenderFormat: 'SYSTEM' },
    { entityUrn: 'urn:li:msg_message:4', deliveredAt: 4, body: { text: 'oops' }, messageBodyRenderFormat: 'RECALLED' },
    { deliveredAt: 5, body: { text: 'no id' } },
  ]
  assert.deepEqual(conversation(c, msgs), {
    id: c.entityUrn, title: '', group: false,
    participants: [
      { url: 'https://www.linkedin.com/in/alex', name: 'Alex Rivera', member: 'urn:li:msg_messagingParticipant:urn:li:fsd_profile:alex' },
      { url: 'https://www.linkedin.com/in/priya', name: 'Priya N', member: 'urn:li:msg_messagingParticipant:urn:li:fsd_profile:priya' },
    ],
    messages: [
      { id: 'urn:li:msg_message:1', ts: 1, sender: 'https://www.linkedin.com/in/alex', text: 'I will send the deck', subject: '', attachment: false },
      { id: 'urn:li:msg_message:2', ts: 2, sender: 'https://www.linkedin.com/in/priya', text: '', subject: '', attachment: true },
    ],
  })
})
