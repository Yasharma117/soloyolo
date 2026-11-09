import { PageTitle, PersonRow, SearchField, SectionLabel, useTheme } from '@soloyolo/design-system'
import { useRouter } from 'expo-router'
import { useMemo, useState } from 'react'
import { FlatList, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'
import { useData } from '../../lib/api'
import { isOpen, type PersonSummary } from '../../lib/types'

export default function People() {
  const t = useTheme()
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
      style={{ backgroundColor: t.color.background }}
      contentContainerStyle={{ paddingTop: insets.top, paddingBottom: 130 }}
      data={list}
      keyExtractor={(p) => String(p.id)}
      keyboardDismissMode="on-drag"
      ListHeaderComponent={
        <View>
          <PageTitle title="People" subtitle="Everyone you talk to, closest first, with what you owe each other." />
          <View style={{ paddingHorizontal: t.space.lg, marginTop: t.space.md + 2 }}><SearchField value={q} onChangeText={setQ} /></View>
          <SectionLabel>{q ? 'Matches' : 'Closest first'}</SectionLabel>
        </View>
      }
      renderItem={({ item: p }) => (
        <PersonRow name={p.name} networks={p.networks} last={p.last}
                   youOwe={p.commitments.filter((x) => x.owner === 'me' && isOpen(x)).length}
                   theyOwe={p.commitments.filter((x) => x.owner === 'them' && isOpen(x)).length}
                   onPress={() => router.push({ pathname: '/person/[id]', params: { id: String(p.id) } })} />
      )}
    />
  )
}
