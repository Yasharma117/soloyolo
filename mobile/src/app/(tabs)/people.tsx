import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'
import { useMemo, useState } from 'react'
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Label, NetIcon, Orb, Title } from '../../components/ui'
import { useData } from '../../lib/api'
import { usePalette } from '../../lib/theme'
import { ago, isOpen, type PersonSummary } from '../../lib/types'

export default function People() {
  const c = usePalette()
  const insets = useSafeAreaInsets()
  const router = useRouter()
  const [q, setQ] = useState('')
  const { data } = useData<PersonSummary[]>('/api/people')
  const list = useMemo(() => (data ?? [])
    .filter((p) => !p.muted && (!q || p.name.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => b.score - a.score)
    .slice(0, 150), [data, q])
  return (
    <FlatList
      style={{ backgroundColor: c.ground }}
      contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}
      data={list}
      keyExtractor={(p) => String(p.id)}
      keyboardDismissMode="on-drag"
      ListHeaderComponent={
        <View>
          <Title title="People" subtitle="Everyone you talk to, closest first, with what you owe each other." />
          <View style={[styles.search, { backgroundColor: c.raised }]}>
            <Ionicons name="search" size={16} color={c.ink3} />
            <TextInput value={q} onChangeText={setQ} placeholder="Search" placeholderTextColor={c.ink3}
                       style={{ flex: 1, color: c.ink, fontSize: 16, paddingVertical: 0 }} />
          </View>
          <Label>{q ? 'Matches' : 'Closest first'}</Label>
        </View>
      }
      renderItem={({ item: p }) => {
        const mine = p.commitments.filter((x) => x.owner === 'me' && isOpen(x)).length
        const theirs = p.commitments.filter((x) => x.owner === 'them' && isOpen(x)).length
        return (
          <Pressable onPress={() => router.push({ pathname: '/person/[id]', params: { id: String(p.id) } })}
                     style={[styles.row, { borderBottomColor: c.line }]}>
            <Orb name={p.name} size={40} />
            <View style={{ flex: 1, gap: 2 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Text style={{ color: c.ink, fontSize: 16, fontWeight: '600', flexShrink: 1 }} numberOfLines={1}>{p.name}</Text>
                {p.networks.slice(0, 2).map((n) => <NetIcon key={n} network={n} size={12} />)}
              </View>
              <Text style={{ color: c.ink3, fontSize: 13 }}>
                {mine ? <Text style={{ color: c.hot, fontWeight: '600' }}>you owe {mine}</Text> : null}
                {mine && theirs ? ' · ' : ''}
                {theirs ? `owes you ${theirs}` : ''}
                {!mine && !theirs ? 'nothing open' : ''}
              </Text>
            </View>
            <Text style={{ color: c.ink3, fontSize: 12 }}>{ago(p.last)}</Text>
          </Pressable>
        )
      }}
    />
  )
}

const styles = StyleSheet.create({
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginTop: 14, borderRadius: 12, paddingHorizontal: 12, height: 40 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
})
