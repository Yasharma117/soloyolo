import { Stack, useLocalSearchParams } from 'expo-router'
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { ItemRow } from '../../components/SwipeItem'
import { useToast } from '../../components/Toast'
import { Apps, Avatar, NET_NAME, SectionTitle } from '../../components/ui'
import { mute, useData } from '../../lib/api'
import { usePalette } from '../../lib/theme'
import { ago, keyOf, type Item, type Message, type Person } from '../../lib/types'

export default function PersonScreen() {
  const c = usePalette()
  const toast = useToast()
  const { id, focus } = useLocalSearchParams<{ id: string; focus?: string }>()
  const p = useData<Person>(`/api/person/${id}`)
  const t = useData<Message[]>(`/api/thread/${id}`)
  if (!p.data) return <View style={{ flex: 1, backgroundColor: c.ground }}><Stack.Screen options={{ title: '' }} /></View>
  const person = p.data
  const items: Item[] = person.commitments.map((x) => ({ ...x, person_id: person.id, name: person.name }))
  const mine = items.filter((x) => x.owner === 'me'), theirs = items.filter((x) => x.owner === 'them')
  const sources = new Set(items.map((x) => x.source_message_id))
  const first = person.name.split(' ')[0]!
  const group = (list: Item[]) => list.length
    ? <View style={[styles.group, { backgroundColor: c.card }]}>{list.map((it, i) => (
        <View key={keyOf(it)} style={String(it.source_message_id) === focus ? { backgroundColor: c.hotSoft } : undefined}>
          <ItemRow item={it} last={i === list.length - 1} />
        </View>))}</View>
    : <Text style={{ color: c.ink3, paddingHorizontal: 20 }}>Nothing.</Text>
  let lastDay = ''
  return (
    <ScrollView style={{ backgroundColor: c.ground }} contentContainerStyle={{ paddingBottom: 48 }}>
      <Stack.Screen options={{ title: person.name }} />
      <View style={styles.head}>
        <Avatar name={person.name} size={64} />
        <Text style={[styles.name, { color: c.ink }]}>{person.name}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Apps networks={person.networks} />
          <Text style={{ color: c.ink2, fontSize: 14 }}>last talked {ago(person.last)} ago{person.muted ? ' · muted' : ''}</Text>
        </View>
        <View style={styles.facts}>
          {person.attributes.map((a) => (
            <View key={`${a.key}${a.value}`} style={[styles.fact, { backgroundColor: c.raised }]}>
              <Text style={{ color: c.ink2, fontSize: 13 }}>{a.key} <Text style={{ color: c.ink, fontWeight: '500' }}>{a.value}</Text></Text>
            </View>
          ))}
          {person.handles.map((h) => (
            <View key={`${h.network}${h.address}`} style={[styles.fact, { backgroundColor: c.raised }]}>
              <Text style={{ color: c.ink2, fontSize: 13 }}>{NET_NAME[h.network] ?? h.network} <Text style={{ color: c.ink, fontWeight: '500' }}>{h.address}</Text></Text>
            </View>
          ))}
        </View>
      </View>
      <SectionTitle>You owe</SectionTitle>
      {group(mine)}
      <SectionTitle>{`${first} owes you`}</SectionTitle>
      {group(theirs)}
      {t.data?.length ? (
        <>
          <SectionTitle>Recent messages</SectionTitle>
          <View style={{ paddingHorizontal: 16, gap: 4 }}>
            {t.data.slice(-40).map((m) => {
              const day = new Date(m.ts * 1000).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
              const sep = day !== lastDay ? <Text style={[styles.day, { color: c.ink3 }]}>{day}</Text> : null
              lastDay = day
              if (m.text === '[call]') return <View key={m.id}>{sep}<Text style={[styles.day, { color: c.ink3 }]}>Call</Text></View>
              const me = !!m.from_me
              return (
                <View key={m.id}>
                  {sep}
                  <View style={[styles.bubble, me ? { alignSelf: 'flex-end', backgroundColor: '#0a84ff' } : { alignSelf: 'flex-start', backgroundColor: c.card },
                                sources.has(m.id) && { borderWidth: 2, borderColor: c.accent }]}>
                    <Text style={{ color: me ? '#fff' : c.ink, fontSize: 16, lineHeight: 21 }}>{m.text}</Text>
                  </View>
                </View>
              )
            })}
          </View>
        </>
      ) : null}
      <SectionTitle>This chat</SectionTitle>
      <Pressable onPress={async () => { await mute(person.id, !person.muted); toast.show(person.muted ? 'Unmuted' : 'Muted: its items are hidden') }}
                 style={[styles.group, { backgroundColor: c.card, padding: 14 }]}>
        <Text style={{ color: person.muted ? c.accent : '#ff453a', fontSize: 17 }}>
          {person.muted ? 'Unmute this chat' : 'Mute: it’s a bot or a service, not a person'}
        </Text>
      </Pressable>
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  head: { alignItems: 'center', paddingTop: 8, paddingHorizontal: 20, gap: 6 },
  name: { fontSize: 26, fontWeight: '700', marginTop: 6 },
  facts: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 6, marginTop: 8 },
  fact: { borderRadius: 8, paddingHorizontal: 9, paddingVertical: 5 },
  group: { marginHorizontal: 16, borderRadius: 14, overflow: 'hidden' },
  day: { alignSelf: 'center', fontSize: 12, marginVertical: 8 },
  bubble: { maxWidth: '80%', borderRadius: 18, paddingHorizontal: 12, paddingVertical: 8 },
})
