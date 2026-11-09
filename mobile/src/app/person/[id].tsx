// A person, Mesh-style: a sheet with their name and orb, a strip of actions, and three views.
import { IconButton, ListRow, PersonHeader, PromiseRow, SectionLabel, Tabs, Text, TimelineEvent, useTheme, useToast, NETWORK_NAME, NetworkIcon, Row, type PromiseState } from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useState } from 'react'
import { Linking, ScrollView, View } from 'react-native'
import { mute, useData } from '../../lib/api'
import { useMarks } from '../../lib/marks'
import { ago, isOpen, keyOf, type Item, type Message, type Person } from '../../lib/types'

type View_ = 'promises' | 'timeline' | 'about'

function stateOf(i: Item): PromiseState {
  if (i.dismissed) return 'not needed'
  if (i.snoozed) return 'later'
  if (i.status === 'done') return 'done'
  return i.live ? 'today' : 'quiet'
}

export default function PersonScreen() {
  const t = useTheme()
  const toast = useToast()
  const router = useRouter()
  const marks = useMarks()
  const { id, focus } = useLocalSearchParams<{ id: string; focus?: string }>()
  const [view, setView] = useState<View_>('promises')
  const p = useData<Person>(`/api/person/${id}`)
  const thread = useData<Message[]>(`/api/thread/${id}`)
  const person = p.data
  if (!person) return <View style={{ flex: 1, backgroundColor: t.color.background }} />
  const items: Item[] = person.commitments.map((x) => ({ ...x, person_id: person.id, name: person.name, networks: person.networks }))
  const first = person.name.split(' ')[0]!
  const sources = new Set(items.map((x) => x.source_message_id))
  const phone = person.handles.find((h) => h.network === 'whatsapp')?.address.split('@')[0]?.replace(/\D/g, '')
  const row = (it: Item) => {
    const st = stateOf(it)
    const open = isOpen(it)
    return (
      <PromiseRow key={keyOf(it)} item={it} state={st} showPerson={false} highlighted={String(it.source_message_id) === focus}
                  trailing={!open ? { label: 'Undo', icon: 'arrow-undo', tone: 'neutralAction', onAction: () => marks.undo(it) }
                    : st === 'quiet' ? { label: 'Still on', icon: 'refresh', tone: 'later', onAction: () => marks.keep(it) }
                    : { label: 'Done', icon: 'checkmark', tone: 'success', onAction: () => marks.done(it) }}
                  leading={open ? { label: 'Not needed', icon: 'close', tone: 'neutralAction', onAction: () => marks.dismiss(it) } : undefined} />
    )
  }
  const none = <Text variant="small" tone="tertiary" style={{ paddingHorizontal: t.space.xl }}>Nothing.</Text>
  return (
    <ScrollView style={{ backgroundColor: t.color.background }} contentContainerStyle={{ paddingBottom: 60 }}>
      <View style={{ paddingHorizontal: t.space.lg, paddingTop: t.space.md + 2 }}>
        <IconButton icon="chevron-down" label="Close" onPress={() => (router.canGoBack() ? router.back() : router.replace('/people'))} />
      </View>
      <PersonHeader
        name={person.name} network={person.networks[0]} subtitle={`last talked ${ago(person.last)} ago${person.muted ? ' · muted' : ''}`}
        actions={[
          { icon: 'chatbubble-outline', label: 'Open chat', disabled: !phone || phone.length < 8, onPress: () => phone && Linking.openURL(`https://wa.me/${phone}`) },
          { icon: person.muted ? 'notifications-outline' : 'notifications-off-outline', label: person.muted ? 'Unmute' : 'Mute',
            onPress: async () => { await mute(person.id, !person.muted); toast.show(person.muted ? 'Unmuted' : 'Muted: its items are hidden') } },
        ]}
      />
      <View style={{ marginTop: t.space.md + 2 }}>
        <Tabs value={view} onChange={setView} items={[{ key: 'promises', label: 'Promises' }, { key: 'timeline', label: 'Timeline' }, { key: 'about', label: 'About' }]} />
      </View>
      {view === 'promises' && (
        <>
          <SectionLabel>You owe</SectionLabel>
          {items.filter((x) => x.owner === 'me').map(row)}
          {!items.some((x) => x.owner === 'me') && none}
          <SectionLabel>{`${first} owes you`}</SectionLabel>
          {items.filter((x) => x.owner === 'them').map(row)}
          {!items.some((x) => x.owner === 'them') && none}
        </>
      )}
      {view === 'timeline' && (
        <View style={{ paddingTop: t.space.sm }}>
          {(thread.data ?? []).slice(-60).reverse().map((m) => (
            <TimelineEvent key={m.id} who={first} text={m.text} ts={m.ts} fromMe={!!m.from_me} call={m.text === '[call]'} isSource={sources.has(m.id)} />
          ))}
          {!thread.data?.length && <Text variant="small" tone="tertiary" style={{ padding: t.space.xl }}>No messages loaded.</Text>}
        </View>
      )}
      {view === 'about' && (
        <>
          <SectionLabel>Summary</SectionLabel>
          <Text variant="body" style={{ paddingHorizontal: t.space.xl }}>
            You last talked {ago(person.last)} ago{person.networks[0] ? ` on ${NETWORK_NAME[person.networks[0]] ?? person.networks[0]}` : ''}.
            You owe {first} {items.filter((x) => x.owner === 'me' && isOpen(x)).length || 'nothing'}, and {first} owes you {items.filter((x) => x.owner === 'them' && isOpen(x)).length || 'nothing'}.
          </Text>
          {person.attributes.length ? <SectionLabel>Properties</SectionLabel> : null}
          {person.attributes.map((a) => (
            <ListRow key={`${a.key}${a.value}`} title={<Text variant="label" tone="tertiary">{a.key}</Text>} trailing={<Text variant="body">{a.value}</Text>} />
          ))}
          <SectionLabel>Sources</SectionLabel>
          {person.handles.map((h) => (
            <ListRow key={`${h.network}${h.address}`} title={<Row gap="sm"><NetworkIcon network={h.network} size="sm" /><Text variant="body">{h.address}</Text></Row>}
                     trailing={<Text variant="label" tone="tertiary">{NETWORK_NAME[h.network] ?? h.network}</Text>} />
          ))}
        </>
      )}
    </ScrollView>
  )
}
