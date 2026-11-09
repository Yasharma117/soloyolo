import { useRouter } from 'expo-router'
import { useMemo, useState } from 'react'
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { Apps, Avatar, LargeTitle } from '../../components/ui'
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
      contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 40 }}
      data={list}
      keyExtractor={(p) => String(p.id)}
      keyboardDismissMode="on-drag"
      ListHeaderComponent={
        <View>
          <LargeTitle title="People" subtitle="Ranked by how much you two talk lately" />
          <TextInput value={q} onChangeText={setQ} placeholder="Search" placeholderTextColor={c.ink3} clearButtonMode="while-editing"
                     style={[styles.search, { backgroundColor: c.raised, color: c.ink }]} />
        </View>
      }
      renderItem={({ item: p, index }) => {
        const mine = p.commitments.filter((x) => x.owner === 'me' && isOpen(x)).length
        const theirs = p.commitments.filter((x) => x.owner === 'them' && isOpen(x)).length
        const first = index === 0, last = index === list.length - 1
        return (
          <Pressable onPress={() => router.push({ pathname: '/person/[id]', params: { id: String(p.id) } })}
                     style={[styles.row, { backgroundColor: c.card }, first && styles.top, last && styles.bottom]}>
            <Avatar name={p.name} size={38} />
            <View style={[styles.rowBody, !last && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.line }]}>
              <View style={{ flex: 1, gap: 2 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Text style={{ color: c.ink, fontSize: 17, fontWeight: '500', flexShrink: 1 }} numberOfLines={1}>{p.name}</Text>
                  <Apps networks={p.networks} />
                </View>
                <Text style={{ color: c.ink2, fontSize: 14 }}>last talked {ago(p.last)} ago</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                {mine ? <Text style={{ color: c.hot, fontSize: 13, fontWeight: '600' }}>you owe {mine}</Text> : null}
                {theirs ? <Text style={{ color: c.ink2, fontSize: 13 }}>owes you {theirs}</Text> : null}
              </View>
            </View>
          </Pressable>
        )
      }}
    />
  )
}

const styles = StyleSheet.create({
  search: { marginHorizontal: 16, marginTop: 8, marginBottom: 14, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, fontSize: 17 },
  row: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 16, paddingLeft: 14, gap: 12 },
  rowBody: { flex: 1, flexDirection: 'row', alignItems: 'center', paddingVertical: 11, paddingRight: 14, gap: 8 },
  top: { borderTopLeftRadius: 14, borderTopRightRadius: 14 },
  bottom: { borderBottomLeftRadius: 14, borderBottomRightRadius: 14 },
})
