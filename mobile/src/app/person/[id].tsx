// A person, Mesh-style: a sheet with their name and orb, a strip of actions, and three views:
// what you owe each other, the conversation as a timeline, and what we know about them.
import Ionicons from '@expo/vector-icons/Ionicons'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useState } from 'react'
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { ItemRow } from '../../components/SwipeItem'
import { useToast } from '../../components/Toast'
import { Label, NET_NAME, NetIcon, Orb } from '../../components/ui'
import { mute, useData } from '../../lib/api'
import { usePalette } from '../../lib/theme'
import { ago, keyOf, type Item, type Message, type Person } from '../../lib/types'

type Tab = 'promises' | 'timeline' | 'about'

export default function PersonScreen() {
  const c = usePalette()
  const toast = useToast()
  const router = useRouter()
  const { id, focus } = useLocalSearchParams<{ id: string; focus?: string }>()
  const [tab, setTab] = useState<Tab>('promises')
  const p = useData<Person>(`/api/person/${id}`)
  const t = useData<Message[]>(`/api/thread/${id}`)
  const person = p.data
  if (!person) return <View style={{ flex: 1, backgroundColor: c.ground }} />
  const items: Item[] = person.commitments.map((x) => ({ ...x, person_id: person.id, name: person.name, networks: person.networks }))
  const mine = items.filter((x) => x.owner === 'me'), theirs = items.filter((x) => x.owner === 'them')
  const sources = new Set(items.map((x) => x.source_message_id))
  const first = person.name.split(' ')[0]!
  const wa = person.handles.find((h) => h.network === 'whatsapp')
  const phone = wa?.address.split('@')[0]?.replace(/\D/g, '')
  const actions: { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void; off?: boolean }[] = [
    { icon: 'chatbubble-outline', label: 'Open chat', off: !phone || phone.length < 8, onPress: () => phone && Linking.openURL(`https://wa.me/${phone}`) },
    { icon: person.muted ? 'notifications-outline' : 'notifications-off-outline', label: person.muted ? 'Unmute' : 'Mute',
      onPress: async () => { await mute(person.id, !person.muted); toast.show(person.muted ? 'Unmuted' : 'Muted: its items are hidden') } },
  ]
  const msgs = (t.data ?? []).slice(-60).reverse()
  const lastNet = person.networks[0]
  return (
    <ScrollView style={{ backgroundColor: c.ground }} contentContainerStyle={{ paddingBottom: 60 }}>
      <View style={styles.bar}>
        <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace('/people'))} hitSlop={10}
                   style={[styles.round, { backgroundColor: c.card, borderColor: c.line }]}>
          <Ionicons name="chevron-down" size={20} color={c.ink} />
        </Pressable>
      </View>
      <View style={styles.head}>
        <View style={{ flex: 1, gap: 6 }}>
          <Text style={[styles.name, { color: c.ink }]}>{person.name}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            {lastNet ? <NetIcon network={lastNet} size={13} /> : null}
            <Text style={{ color: c.ink2, fontSize: 14 }}>last talked {ago(person.last)} ago{person.muted ? ' · muted' : ''}</Text>
          </View>
        </View>
        <Orb name={person.name} size={76} />
      </View>

      <View style={[styles.strip, { borderColor: c.line }]}>
        {actions.map((a, i) => (
          <Pressable key={a.label} disabled={a.off} onPress={a.onPress}
                     style={[styles.act, i > 0 && { borderLeftWidth: StyleSheet.hairlineWidth, borderLeftColor: c.line }, a.off && { opacity: 0.35 }]}>
            <Ionicons name={a.icon} size={20} color={c.ink} />
            <Text style={[styles.actLabel, { color: c.ink2 }]}>{a.label.toUpperCase()}</Text>
          </Pressable>
        ))}
      </View>

      <View style={[styles.tabs, { borderBottomColor: c.line }]}>
        {(['promises', 'timeline', 'about'] as Tab[]).map((k) => (
          <Pressable key={k} onPress={() => setTab(k)} style={[styles.tab, tab === k && { borderBottomColor: c.accent }]}>
            <Text style={{ color: tab === k ? c.ink : c.ink3, fontSize: 15, fontWeight: tab === k ? '600' : '500' }}>
              {k === 'promises' ? 'Promises' : k === 'timeline' ? 'Timeline' : 'About'}
            </Text>
          </Pressable>
        ))}
      </View>

      {tab === 'promises' && (
        <>
          <Label>You owe</Label>
          {mine.length ? mine.map((it) => <ItemRow key={keyOf(it)} item={it} showName={false} focus={String(it.source_message_id) === focus} />)
            : <Text style={[styles.none, { color: c.ink3 }]}>Nothing.</Text>}
          <Label>{`${first} owes you`}</Label>
          {theirs.length ? theirs.map((it) => <ItemRow key={keyOf(it)} item={it} showName={false} focus={String(it.source_message_id) === focus} />)
            : <Text style={[styles.none, { color: c.ink3 }]}>Nothing.</Text>}
        </>
      )}

      {tab === 'timeline' && (
        <View style={{ paddingTop: 8 }}>
          {msgs.length ? msgs.map((m) => {
            const src = sources.has(m.id)
            const call = m.text === '[call]'
            return (
              <View key={m.id} style={[styles.event, { borderBottomColor: c.line }, src && { backgroundColor: c.hotSoft }]}>
                <View style={[styles.eventIcon, { backgroundColor: c.raised }]}>
                  <Ionicons name={call ? 'call' : m.from_me ? 'arrow-up' : 'arrow-down'} size={12} color={c.ink2} />
                </View>
                <Text style={{ flex: 1, color: c.ink2, fontSize: 14, lineHeight: 20 }}>
                  <Text style={{ color: c.ink3 }}>{call ? 'A call' : m.from_me ? 'You: ' : `${first}: `}</Text>
                  {call ? '' : <Text style={{ color: c.ink }}>{m.text}</Text>}
                  {src ? <Text style={{ color: c.hot, fontWeight: '600' }}>{'  · the promise'}</Text> : null}
                </Text>
                <Text style={{ color: c.ink3, fontSize: 12 }}>{ago(m.ts)}</Text>
              </View>
            )
          }) : <Text style={[styles.none, { color: c.ink3, marginTop: 16 }]}>No messages loaded.</Text>}
        </View>
      )}

      {tab === 'about' && (
        <>
          <Label>Summary</Label>
          <Text style={[styles.para, { color: c.ink }]}>
            You last talked {ago(person.last)} ago{lastNet ? ` on ${NET_NAME[lastNet] ?? lastNet}` : ''}. You owe {first} {mine.filter((x) => x.status === 'open').length || 'nothing'}
            {', and '}{first} owes you {theirs.filter((x) => x.status === 'open').length || 'nothing'}.
          </Text>
          {person.attributes.length ? <Label>Properties</Label> : null}
          {person.attributes.map((a) => (
            <View key={`${a.key}${a.value}`} style={[styles.prop, { borderBottomColor: c.line }]}>
              <Text style={{ color: c.ink3, fontSize: 12, fontWeight: '600', letterSpacing: 1 }}>{a.key.toUpperCase()}</Text>
              <Text style={{ color: c.ink, fontSize: 15 }}>{a.value}</Text>
            </View>
          ))}
          <Label>Sources</Label>
          {person.handles.map((h) => (
            <View key={`${h.network}${h.address}`} style={[styles.prop, { borderBottomColor: c.line }]}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <NetIcon network={h.network} size={14} />
                <Text style={{ color: c.ink, fontSize: 15 }}>{h.address}</Text>
              </View>
              <Text style={{ color: c.ink3, fontSize: 12, fontWeight: '600', letterSpacing: 1 }}>{(NET_NAME[h.network] ?? h.network).toUpperCase()}</Text>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', paddingHorizontal: 16, paddingTop: 14 },
  round: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', borderWidth: StyleSheet.hairlineWidth },
  head: { flexDirection: 'row', alignItems: 'center', gap: 16, paddingHorizontal: 20, paddingTop: 14, paddingBottom: 18 },
  name: { fontSize: 28, fontWeight: '800', letterSpacing: -0.5 },
  strip: { flexDirection: 'row', borderTopWidth: StyleSheet.hairlineWidth, borderBottomWidth: StyleSheet.hairlineWidth },
  act: { flex: 1, alignItems: 'center', gap: 6, paddingVertical: 12 },
  actLabel: { fontSize: 10, fontWeight: '600', letterSpacing: 1 },
  tabs: { flexDirection: 'row', gap: 22, paddingHorizontal: 20, marginTop: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  tab: { paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: 'transparent', marginBottom: -StyleSheet.hairlineWidth },
  none: { paddingHorizontal: 20, fontSize: 14 },
  event: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingHorizontal: 20, paddingVertical: 11, borderBottomWidth: StyleSheet.hairlineWidth },
  eventIcon: { width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center', marginTop: 1 },
  para: { paddingHorizontal: 20, fontSize: 15, lineHeight: 22 },
  prop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
})
