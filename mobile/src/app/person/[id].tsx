// A person, Mesh-style: a sheet with their name and orb, a strip of actions, and three views.
import {
  BottomSheet, Button, ConfirmDialog, IconButton, InlineError, KeyValueList, NavList, NETWORK_NAME, NetworkIcon, OptionList, PersonHeader,
  PromiseRow, RowSkeleton, SectionCard, SectionLabel, Skeleton, StatRow, StatTile, Tabs, Text, TimelineEvent, TopBar, Wash, statusOf, useScrollChrome, useTheme, useToast, type Option,
} from '@soloyolo/design-system'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useState } from 'react'
import { Linking, View } from 'react-native'
import Animated from 'react-native-reanimated'
import { mute, refresh, useData } from '../../lib/api'
import { useMarks } from '../../lib/marks'
import { ago, isOpen, keyOf, type Item, type Message, type Person } from '../../lib/types'

type View_ = 'promises' | 'timeline' | 'about'
type Days = '1' | '3' | '7' | '30'

const day = (n: number) => new Date(Date.now() + n * 86400e3).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

// A promise with a due date is better snoozed past it; one without comes back in three days, like the nudge.
function snoozeOptions(it: Item): Option<Days>[] {
  const pick: Days = it.due ? '7' : '3'
  const why = it.due ? `It’s due ${it.due}, so a week clears it.` : 'The nudge looks again after three quiet days.'
  return ([['1', 'Tomorrow', 'Back on Today first thing.'], ['3', 'In 3 days', undefined], ['7', 'Next week', undefined], ['30', 'In a month', 'For things that can wait.']] as const)
    .map(([value, label, description]) => ({ value, label, description, trailing: day(Number(value)), suggested: value === pick ? why : undefined }))
}

export default function PersonScreen() {
  const t = useTheme()
  const toast = useToast()
  const router = useRouter()
  const marks = useMarks()
  const { id, focus } = useLocalSearchParams<{ id: string; focus?: string }>()
  const [view, setView] = useState<View_>('promises')
  const [asking, setAsking] = useState(false)
  const [snoozing, setSnoozing] = useState<{ item: Item; days: Days } | null>(null)
  const p = useData<Person>(`/api/person/${id}`)
  const thread = useData<Message[]>(`/api/thread/${id}`)
  const person = p.data
  const chrome = useScrollChrome()
  // pinned in the top bar, so it never scrolls away on a long timeline (Markon's inline header: back stays put)
  const close = <IconButton icon="chevron-down" label="Close" onPress={() => (router.canGoBack() ? router.back() : router.replace('/people'))} />
  if (!person) {
    return (
      <View style={{ flex: 1, backgroundColor: t.color.background }}>
        <View style={{ paddingTop: 64, gap: t.space.xl }}>
          {p.error ? <InlineError title="We couldn’t load this person." body="soloyolo on your Mac didn’t answer. Check it’s running, then try again." onRetry={refresh} />
            : <View style={{ gap: t.space.md, paddingHorizontal: t.space.xl }}><Skeleton width="55%" height={28} /><Skeleton width="35%" height={12} />
                <View style={{ marginHorizontal: -t.space.xl, marginTop: t.space.xl }}>{[0, 1, 2].map((i) => <RowSkeleton key={i} />)}</View></View>}
        </View>
        <TopBar y={chrome.y} leading={close} />
      </View>
    )
  }
  const items: Item[] = person.commitments.map((x) => ({ ...x, person_id: person.id, name: person.name, networks: person.networks }))
  const first = person.name.split(' ')[0]!
  const sources = new Set(items.map((x) => x.source_message_id))
  const phone = person.handles.find((h) => h.network === 'whatsapp')?.address.split('@')[0]?.replace(/\D/g, '')
  const youOwe = items.filter((x) => x.owner === 'me' && isOpen(x)).length
  const theyOwe = items.filter((x) => x.owner === 'them' && isOpen(x)).length
  const closed = items.filter((x) => x.status === 'done' || x.dismissed).length
  const row = (it: Item) => {
    const st = statusOf(it)
    const open = isOpen(it)
    return (
      <PromiseRow key={keyOf(it)} item={it} state={st} showPerson={false} highlighted={String(it.source_message_id) === focus}
                  onPress={open ? () => setSnoozing({ item: it, days: it.due ? '7' : '3' }) : undefined}
                  onSettle={() => marks.done(it)}
                  trailing={!open ? { label: 'Undo', icon: 'arrow-undo', tone: 'neutralAction', onAction: () => marks.undo(it) }
                    : st === 'quiet' ? { label: 'Still on', icon: 'refresh', tone: 'later', onAction: () => marks.keep(it) }
                    : { label: 'Done', icon: 'checkmark', tone: 'success', onAction: () => marks.done(it) }}
                  leading={open ? { label: 'Not needed', icon: 'close', tone: 'neutralAction', onAction: () => marks.dismiss(it) } : undefined} />
    )
  }
  const none = <Text variant="small" tone="tertiary" style={{ paddingHorizontal: t.space.xl }}>Nothing.</Text>
  const messages = (thread.data ?? []).slice(-60).reverse()
  return (
    <View style={{ flex: 1, backgroundColor: t.color.background }}>
    <Animated.ScrollView onScroll={chrome.onScroll} scrollEventThrottle={16} contentContainerStyle={{ paddingTop: 52, paddingBottom: 60 }}>
      <Wash />
      <PersonHeader
        name={person.name} network={person.networks[0]} subtitle={`last talked ${ago(person.last)} ago${person.muted ? ' · muted' : ''}`}
        actions={[
          { icon: 'chatbubble-outline', label: 'Open chat', disabled: !phone || phone.length < 8, onPress: () => phone && Linking.openURL(`https://wa.me/${phone}`) },
          { icon: person.muted ? 'notifications-outline' : 'notifications-off-outline', label: person.muted ? 'Unmute' : 'Mute',
            onPress: async () => {
              if (!person.muted) return setAsking(true)
              await mute(person.id, false); toast.show('Chat unmuted')
            } },
        ]}
      />
      <ConfirmDialog open={asking} destructive title={`Mute ${first}?`}
                     body={`${first}’s promises leave Today and soloyolo stops reading this chat. You can unmute it anytime.`}
                     confirmLabel="Mute chat" onCancel={() => setAsking(false)}
                     onConfirm={async () => { setAsking(false); await mute(person.id, true); toast.show('Chat muted') }} />
      <BottomSheet open={!!snoozing} onClose={() => setSnoozing(null)} title="Snooze until" subtitle={snoozing?.item.action}
                   footer={<Button label="Snooze" variant="primary" onPress={() => {
                     if (snoozing) void marks.snooze(snoozing.item, Number(snoozing.days))
                     setSnoozing(null)
                   }} />}>
        {snoozing ? <OptionList label="Snooze until" options={snoozeOptions(snoozing.item)} value={snoozing.days}
                                onChange={(days) => setSnoozing({ ...snoozing, days })} /> : null}
      </BottomSheet>
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
          <Text variant="caption" tone="tertiary" style={{ paddingHorizontal: t.space.xl, paddingTop: t.space.lg }}>
            Tap an open one to snooze it. Swipe left when it’s done, right if it’s not needed.
          </Text>
        </>
      )}
      {view === 'timeline' && (
        <View style={{ paddingTop: t.space.lg }}>
          {thread.error ? <InlineError title="We couldn’t load the chat." body="soloyolo on your Mac didn’t answer. Check it’s running, then try again." onRetry={refresh} /> : null}
          {messages.map((m, i) => (
            <TimelineEvent key={m.id} who={first} text={m.text} ts={m.ts} fromMe={!!m.from_me} call={m.text === '[call]'} isSource={sources.has(m.id)}
                           last={i === messages.length - 1} />
          ))}
          {!thread.error && !messages.length && <Text variant="small" tone="tertiary" style={{ padding: t.space.xl }}>No messages loaded.</Text>}
        </View>
      )}
      {view === 'about' && (
        <View style={{ gap: t.space.lg, paddingTop: t.space.lg }}>
          <StatRow>
            <StatTile label="You owe" value={String(youOwe)} tone={youOwe ? 'accent' : 'primary'} />
            <StatTile label={`${first} owes`} value={String(theyOwe)} />
            <StatTile label="Closed" value={String(closed)} tone={closed ? 'success' : 'primary'} />
          </StatRow>
          <Text variant="body" tone="secondary" style={{ paddingHorizontal: t.space.xl }}>
            You last talked {ago(person.last)} ago{person.networks[0] ? ` on ${NETWORK_NAME[person.networks[0]] ?? person.networks[0]}` : ''}.
          </Text>
          {person.attributes.length ? (
            <SectionCard title="Properties">
              <KeyValueList items={person.attributes.map((a) => ({ label: a.key[0]!.toUpperCase() + a.key.slice(1), value: a.value }))} />
            </SectionCard>
          ) : null}
          <SectionCard title="Sources">
            <NavList rows={person.handles.map((h) => ({ key: `${h.network}${h.address}`, lead: <NetworkIcon network={h.network} size="md" />,
                                                         label: NETWORK_NAME[h.network] ?? h.network, description: h.address }))} />
          </SectionCard>
        </View>
      )}
    </Animated.ScrollView>
    <TopBar y={chrome.y} title={person.name} at={70} leading={close} />
    </View>
  )
}
